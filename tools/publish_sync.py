#!/usr/bin/env python3
"""«منشور» آلياً (W-20261014-013): بطاقاتٌ صار دمجُها داخل الإنتاج — يطبع أوامر published ونص الإبلاغ، ولا ينفّذ.

    python publish_sync.py                 # يقرأ commit الإنتاج من /health/ ويفحص البطاقات
    python publish_sync.py --commit 25cef9a --limit 80
    python publish_sync.py --json

الخطوات: (١) commit الإنتاج من حقل `commit` في /health/. (٢) كلُّ بطاقةٍ حالتها approved أو pushed أو merged
ولها رأسٌ (head أو approved_head) يُقابَل بطلبٍ MERGED في GitHub بالرأس نفسه. (٣) دمجُ الطلب (mergeCommit) سلفٌ
لـcommit الإنتاج عبر `gh api compare` (الحالة identical أو ahead). ما تحقق يُطبع أمرُ نقله إلى published
بالتسلسل المسموح (pushed ثم merged ثم published) ونصُّ إبلاغ صاحب الطلب و0701.

لا move ولا إرسال: التنفيذُ والإبلاغ لجلسة الدمج (0601) وحدها (D-88م). فشلُ gh أو /health/ يُعلَن ولا يُخمَّن.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request

import ledger

SLUG = "sh-school/shschool_mvp"
HEALTH = "https://shschoolmvp-production.up.railway.app/health/"
PENDING = ("approved", "pushed", "merged")
CHAIN = ("pushed", "merged", "published")


class SyncError(RuntimeError):
    pass


def parse_health(text: str) -> str:
    """commit الإنتاج من نص /health/؛ يرفع SyncError إن غاب أو كان الإنتاج غير سليم."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise SyncError("ردُّ /health/ ليس JSON") from exc
    commit = str(data.get("commit") or "").strip()
    if data.get("status") != "ok":
        raise SyncError(f"الإنتاج غير سليم: status={data.get('status')!r}")
    if len(commit) < 7:
        raise SyncError("حقل commit غائب أو قصير في /health/")
    return commit


def fetch_health() -> str:
    try:
        with urllib.request.urlopen(HEALTH, timeout=15) as resp:  # noqa: S310 — رابطٌ ثابت
            return parse_health(resp.read().decode("utf-8"))
    except OSError as exc:
        raise SyncError(f"تعذّر قراءة /health/: {exc}") from exc


def _gh(args: list[str]) -> str:
    out = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if out.returncode:
        raise SyncError("فشل gh: " + (out.stderr or "").strip()[:200])
    return out.stdout


def merged_prs(limit: int) -> dict[str, dict]:
    """رأس الطلب (8 أحرف) → {number, merge, at} للطلبات المدموجة."""
    rows = json.loads(
        _gh([
            "pr", "list", "--repo", SLUG, "--state", "merged", "--limit", str(limit),
            "--json", "number,headRefOid,mergeCommit,mergedAt",
        ])
    )
    return {
        r["headRefOid"][:8]: {"number": r["number"], "merge": (r.get("mergeCommit") or {}).get("oid", ""), "at": r["mergedAt"]}
        for r in rows
    }


def in_production(merge_oid: str, prod: str) -> bool:
    """دمجُ الطلب سلفٌ لـcommit الإنتاج: identical أو ahead (الإنتاج أمامه)."""
    if not merge_oid:
        return False
    status = _gh(["api", f"repos/{SLUG}/compare/{merge_oid}...{prod}", "-q", ".status"]).strip()
    return status in {"identical", "ahead"}


def card_head(data: dict) -> str:
    return (data.get("head") or data.get("approved_head") or "")[:8]


def due(states: dict[str, dict], prs: dict[str, dict], prod: str, check=in_production) -> list[dict]:
    """البطاقات المستحقة: حالتها قبل published ورأسها مدموجٌ وداخل الإنتاج."""
    rows = []
    for cid, st in sorted(states.items()):
        if st.get("state") not in PENDING:
            continue
        head = card_head(st)
        pr = prs.get(head)
        if not head or not pr:
            continue
        if check(pr["merge"], prod):
            rows.append({"id": cid, "state": st["state"], "head": head, "pr": pr["number"], "merge": pr["merge"][:9]})
    return rows


def commands(row: dict) -> list[str]:
    """أوامر النقل بالتسلسل المسموح انطلاقاً من حالة البطاقة الحاليّة."""
    start = CHAIN.index(row["state"]) + 1 if row["state"] in CHAIN else 0
    why = f"#{row['pr']} مدموج {row['merge']} ومنشور {row['prod']}"
    return [
        f'python tools/ledger.py move {row["id"]} {s} --waive-remote-check "{why}"' for s in CHAIN[start:]
    ]


def report_text(rows: list[dict], prod: str) -> str:
    cards = "، ".join(f"{r['id']} (#{r['pr']})" for r in rows)
    return f"منشور على الإنتاج {prod} (فحص /health/ سليم): {cards}. الدفتر published."


def digest_note(row: dict, rows: list[dict], prod: str) -> str:
    """ملاحظةُ الدفتر المجمَّعة بالرأس: كلُّ بطاقةٍ تحمل الدفعةَ نفسَها (رأس الإنتاج وبطاقاتُها) بدل رسالةٍ لكلّ جلسة."""
    batch = "، ".join(f"{r['id']} (#{r['pr']})" for r in rows)
    return f"نُشر #{row['pr']} على الإنتاج {prod}؛ دفعةُ هذا الرأس: {batch}."


def messages_by_owner(rows: list[dict], states: dict[str, dict], prod: str) -> dict[str, str]:
    """رسالةٌ واحدةٌ لكلّ صاحبِ بطاقة (held_by) بكلِّ بطاقاته في الدفعة؛ بلا صاحبٍ تذهب إلى 0701."""
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        grouped.setdefault(states.get(r["id"], {}).get("held_by") or "0701", []).append(r)
    return {
        owner: f"منشور على الإنتاج {prod}: " + "، ".join(f"{r['id']} (#{r['pr']})" for r in rs) + "."
        for owner, rs in sorted(grouped.items())
    }


def write_notes(rows: list[dict], prod: str, by: str, add_note=None) -> list[str]:
    """يكتب الملاحظةَ المجمَّعة على كلّ بطاقةٍ مستحقّة (ملاحظةٌ فقط، لا نقلَ حالة: النقلُ لـ0601 وحدها)."""
    add_note = add_note or ledger.add_note
    done = []
    for r in rows:
        add_note(r["id"], digest_note(r, rows, prod), by)
        done.append(r["id"])
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", help="بدل قراءة /health/ (للاختبار أو الفحص اليدويّ)")
    ap.add_argument("--limit", type=int, default=80, help="عدد الطلبات المدموجة المفحوصة")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--digest", action="store_true", help="يطبع الملاحظةَ المجمَّعة بالرأس ورسالةً واحدةً لكلّ صاحب بطاقة")
    ap.add_argument("--write-notes", action="store_true", help="يكتب الملاحظةَ المجمَّعة في الدفتر (يلزم --by)")
    ap.add_argument("--by", help="رقمُ جلسةِ كاتب الملاحظة مع --write-notes")
    a = ap.parse_args(argv)
    if a.write_notes and not a.by:
        print("✘ --write-notes يلزمه --by <رقم جلستك>", file=sys.stderr)
        return 2
    try:
        prod = a.commit or fetch_health()
        states = ledger.reduce_state(ledger.load_events())
        # reduce_state يعيد حقول الحالة مسطّحةً بالمعرّف
        prs = merged_prs(a.limit)
        rows = due(states, prs, prod)
    except SyncError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 2
    for r in rows:
        r["prod"] = prod[:7]
    if a.json:
        print(json.dumps({"prod": prod, "due": rows}, ensure_ascii=False, indent=2))
        return 0
    print(f"الإنتاج {prod[:7]} — {len(rows)} بطاقة دُمجت وصارت داخله ولم تُنقل إلى published")
    for r in rows:
        print(f"  {r['id']} ({r['state']}) #{r['pr']} رأس {r['head']}")
        for c in commands(r):
            print(f"    {c}")
    if rows:
        print("\nنصُّ الإبلاغ (لصاحب كلِّ بطاقة و0701 في الدقيقة نفسها):")
        print("  " + report_text(rows, prod[:7]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
