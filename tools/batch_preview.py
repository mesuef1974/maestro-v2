#!/usr/bin/env python3
"""جدولُ المعاينة الدفعيّة — قراءةٌ فقط: كلُّ البطاقات الواجهيّة «جاهزٌ للمعاينة» في جدولٍ واحد (W-20261015-014).

لكلّ بطاقةٍ: رأسُها (آخرُ إيداعٍ يحمل رمزَها خارج main) ورابطُها والدورُ والرقمُ التجريبيّ من ملاحظاتها، ثمّ ما إن كان يدخل الدفعةَ
أو يُستبعد بسببه: متعارضٌ مع main أو مع بطاقةٍ سبقته في الدفعة، أو خاملٌ، أو لا رأسَ له. التركيبُ بمحاكاة `git merge-tree` فلا يمسّ شجرةً
ولا فرعاً ولا يدفع، ولا خادمَ مقيمٌ هنا؛ والتثبيتُ الفعليّ لـ8500 يبقى بـ`scripts/preview.sh` عند 0501.

الاعتماد بعدها صريحٌ من المالك لكلّ رأسٍ مطابقٍ للمعروض هنا (D-146م)؛ الأداةُ لا تعتمد ولا تحذف ولا تراسل.

    python batch_preview.py [--repo D:/shschool_mvp] [--base origin/main] [--max-age-h 48] [--cards W-1 W-2] [--html out.html] [--json]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402

CARD_RE = re.compile(r"W-\d{8}-\d{3}")
LINK_RE = re.compile(r"https?://localhost:8500/\S*")
UI_PATHS = ("templates/", "static/")
UI_TYPES = {"ui", "feature", "ux", "design"}
REGISTRY = Path(__file__).resolve().parent / "preview_accounts_registry.json"
DEFAULT_REPO = "D:/shschool_mvp"


def git(repo: str, *args: str) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, encoding="utf-8", errors="replace", check=False)
    return p.returncode, p.stdout.strip()


def is_ui(item: dict) -> bool:
    files = " ".join(item.get("files") or [])
    return item.get("type") in UI_TYPES or any(p in files for p in UI_PATHS)


def head_of(repo: str, base: str, card: str) -> tuple[str, str, int] | None:
    """(الرأس، الفرع/المرجع، وقتُ آخر إيداعٍ جديد) لأحدث إيداعٍ يحمل رمزَ البطاقة ولا يوجد في base."""
    rc, out = git(repo, "log", "--all", "--no-merges", "-1", "--format=%H|%ct|%D", f"--grep={card}", f"^{base}")
    if rc != 0 or not out:
        return None
    sha, ct, refs = (out.split("|", 2) + ["", ""])[:3]
    ref = next((r.strip().replace("HEAD -> ", "") for r in refs.split(",") if r.strip() and "tag:" not in r), "")
    return sha, ref or sha[:8], int(ct or 0)


def merges_clean(repo: str, left: str, right: str) -> tuple[bool, str]:
    rc, out = git(repo, "merge-tree", "--write-tree", "--name-only", "--no-messages", left, right)
    if rc == 0:
        return True, out.splitlines()[0] if out else ""
    return False, " ".join(out.splitlines()[1:4])


def role_and_account(item: dict, registry: list[dict]) -> tuple[str, str]:
    text = " ".join(n.get("text", "") for n in item.get("notes", []))
    for acct in registry:
        if acct["role"] in text:
            return acct["role"], acct["national_id"]
    m = re.search(r"الدور[:：]?\s*([^\s،؛.]+)", text)
    return (m.group(1) if m else "—"), "—"


def card_link(item: dict) -> str:
    for n in reversed(item.get("notes", [])):
        m = LINK_RE.search(n.get("text", ""))
        if m:
            return m.group(0)
    return "—"


def plan(items: dict[str, dict], repo: str, base: str, max_age_h: int, now: float | None = None,
         only: list[str] | None = None, registry: list[dict] | None = None) -> dict:
    now = now or time.time()
    registry = registry or []
    all_ready = [i for i in items.values() if i["state"] == "ready_for_review"]
    ready = [i for i in all_ready if is_ui(i) and (not only or i["id"] in only)]
    skipped = [i["id"] for i in all_ready if i not in ready]
    rows = []
    for it in sorted(ready, key=lambda i: i["id"]):
        h = head_of(repo, base, it["id"])
        role, acct = role_and_account(it, registry)
        row = {"id": it["id"], "held_by": it.get("held_by") or "—", "problem": it.get("problem", "")[:80],
               "link": card_link(it), "role": role, "account": acct, "head": "", "ref": "", "ct": 0}
        if h:
            row.update(head=h[0], ref=h[1], ct=h[2])
        rows.append(row)
    # الأقدمُ عملاً أوّلاً: له الأولويّةُ إن تعارض اثنان (كما plan_integration)
    rows.sort(key=lambda r: (r["ct"] or 1 << 62, r["id"]))
    cur, included, excluded = base, [], []
    for r in rows:
        if not r["head"]:
            excluded.append({**r, "why": "لا إيداعَ يحمل رمزَ البطاقة خارج main — لا رأسَ يُعرض"})
            continue
        if max_age_h and now - r["ct"] > max_age_h * 3600:
            excluded.append({**r, "why": f"خاملٌ: آخرُ إيداعٍ منذ {int((now - r['ct']) // 3600)} ساعة (السقف {max_age_h})"})
            continue
        ok_main, files = merges_clean(repo, base, r["head"])
        if not ok_main:
            excluded.append({**r, "why": "يتعارض مع main — يحتاج إعادةَ أساس: " + (files or "؟")})
            continue
        ok, files = merges_clean(repo, cur, r["head"])
        if not ok:
            excluded.append({**r, "why": "يتعارض مع بطاقةٍ سبقته في الدفعة: " + (files or "؟")})
            continue
        # الدمجُ المحاكى يلزمه إيداعٌ كي يُقابَل به ما بعده: إيداعٌ معلَّقٌ بلا فرعٍ ولا مرجع (لا يمسّ مرجعاً ولا شجرة)
        rc, merged = git(repo, "-c", "user.name=batch", "-c", "user.email=batch@local", "commit-tree", files, "-p", cur, "-p", r["head"], "-m", "batch")
        cur = merged if rc == 0 and merged else cur
        included.append(r)
    return {"base": base, "included": included, "excluded": excluded,
            "considered": {"cards": len(items), "ready": len(all_ready), "ui": len(ready), "not_ui_or_filtered": skipped}}


def render_text(rep: dict) -> str:
    c = rep["considered"]
    out = [f"الدفعة على {rep['base']}: تدخل {len(rep['included'])} وتُستبعد {len(rep['excluded'])}",
           f"المقروء من الدفتر: {c['cards']} بطاقة، منها «جاهز للمعاينة» {c['ready']}، والواجهية المعتبرة {c['ui']}"
           + (f"؛ خارج الاعتبار (غير واجهية أو خارج --cards): {'، '.join(c['not_ui_or_filtered'])}" if c["not_ui_or_filtered"] else "")]
    if not rep["included"]:
        out.append("الدفعة فارغة" + (": كلُّ ما قُرئ مستبعدٌ بسببه أدناه" if rep["excluded"] else ": لا بطاقةَ واجهيّةً جاهزةً في الدفتر"))
    for r in rep["included"]:
        out.append(f"✔ {r['id']} [{r['held_by']}] رأس {r['head'][:8]} ({r['ref']}) · {r['role']} {r['account']} · {r['link']}")
    for r in rep["excluded"]:
        out.append(f"✗ {r['id']} [{r['held_by']}] — {r['why']}")
    return "\n".join(out)


def render_html(rep: dict) -> str:
    def row(r, why=""):
        cells = [r["id"], r["held_by"], r["head"][:8] or "—", r["ref"], r["role"], r["account"], r["link"], why or "يدخل الدفعة"]
        return "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in cells) + "</tr>"
    head = "<tr><th>البطاقة</th><th>الحاملة</th><th>الرأس</th><th>الفرع</th><th>الدور</th><th>الرقم التجريبي</th><th>الرابط</th><th>الحالة</th></tr>"
    body = "".join(row(r) for r in rep["included"]) + "".join(row(r, r["why"]) for r in rep["excluded"])
    return ("<!doctype html><html lang='ar' dir='rtl'><meta charset='utf-8'><title>جدول المعاينة الدفعية</title><body>"
            f"<h1>الدفعة على {html.escape(rep['base'])}: تدخل {len(rep['included'])} وتُستبعد {len(rep['excluded'])}</h1>"
            f"<p>المقروء من الدفتر: {rep['considered']['cards']} بطاقة، «جاهز للمعاينة» {rep['considered']['ready']}، واجهية {rep['considered']['ui']}.</p>"
            "<p>الاعتمادُ صريحٌ من المالك لكلّ رأسٍ مطابقٍ للمعروض هنا؛ هذا الجدولُ لا يعتمد ولا يدفع.</p>"
            f"<table border='1' cellpadding='4'>{head}{body}</table></body></html>")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--max-age-h", type=int, default=48)
    ap.add_argument("--cards", nargs="*")
    ap.add_argument("--html")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    path = ledger.ledger_path()
    if not path.is_file():
        # دفترٌ غائبٌ (شجرةٌ نظيفةٌ بلا ledger/events.jsonl غير المتتبَّع) لا يُقرأ فارغاً بصمت فيُظنّ أن لا جاهزَ
        print(f"✗ لا دفترَ في {path} — شغّل الأداةَ من مجلّد المايسترو أو اضبط LEDGER_PATH", file=sys.stderr)
        return 2
    registry = json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.is_file() else []
    rep = plan(ledger.reduce_state(ledger.load_events()), a.repo, a.base, a.max_age_h, only=a.cards, registry=registry)
    if a.html:
        Path(a.html).write_text(render_html(rep), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1) if a.json else render_text(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
