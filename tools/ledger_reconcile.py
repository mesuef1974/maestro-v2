#!/usr/bin/env python3
"""مصالحةُ الدفتر مع GitHub (وضع الظلّ) — W-20261016-022 (المكوّن C): تقترح نقلَ pushed/merged بدليلٍ يسمّي رمزَ البطاقة.

    python ledger_reconcile.py [--repo sh-school/shschool_mvp] [--limit 400] [--json]

للقراءة فقط: لا يكتب في الدفتر أبداً (فرقُ الدفتر قبل/بعد صفر). المطابقةُ بالرمز W-… في **اسم الفرع أو عنوان الطلب أو سطرٍ
صريحٍ «بطاقةُ الدفتر: W-…» في أوّل الوصف** وحدها؛ فرمزٌ يُذكر عَرَضاً في متن الوصف («مستقلّة عنه W-…» كطلب #913) لا يطابق.
ولا اقتراحَ لـpublished (لا دليلَ نشرٍ هنا) فيُعرض «غير مؤكد». وغيابُ gh يطبع «غير مقيس» ولا يقترح شيئاً.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ledger  # noqa: E402
import stale_policy  # noqa: E402

CODE = re.compile(r"W-(\d{8})-(\d{3})")
BRANCH_CODE = re.compile(r"w(\d{8})-(\d{3})", re.I)
BODY_LINE = re.compile(
    r"^\s*(?:بطاقةُ?\s+الدفتر|البطاقةُ?)\s*[:：]\s*(W-\d{8}-\d{3})", re.M
)
RANK = {
    "captured": 0,
    "routed": 1,
    "in_progress": 2,
    "ready_for_review": 3,
    "approved": 4,
    "pushed": 5,
    "merged": 6,
    "published": 7,
}


def codes_of(pr: dict) -> list[tuple[str, str]]:
    """(الرمز، موضعُ الدليل) من الفرع والعنوان وسطر الوصف الصريح؛ بلا تكرار."""
    out: dict[str, str] = {}
    for m in BRANCH_CODE.finditer(pr.get("headRefName") or ""):
        out.setdefault(f"W-{m.group(1)}-{m.group(2)}", "الفرع")
    for m in CODE.finditer(pr.get("title") or ""):
        out.setdefault(m.group(0), "العنوان")
    for m in BODY_LINE.finditer(pr.get("body") or ""):
        out.setdefault(m.group(1), "سطر الوصف")
    return list(out.items())


def _head_matches(approved: str | None, head_oid: str | None) -> bool:
    """الرأسُ المعتمَدُ بادئةٌ لرأس الطلب المدموج (8 أحرف على الأقل)، لا تطابقٌ جزئيٌّ عشوائيّ."""
    a, h = (approved or "").strip().lower(), (head_oid or "").strip().lower()
    return len(a) >= 8 and bool(h) and h.startswith(a)


def write_candidates(items: dict[str, dict], prs: list[dict], ancestor=None) -> list[dict]:
    """(W-20261028-030) بطاقاتٌ يُكتب لها merged: approved أو pushed، ورمزُها في **العنوان أو الفرع** (لا متنُ الوصف)،
    وطلبُها MERGED، ورأسُ الطلب المدموج يطابق الرأسَ المعتمَد. الأبوّةُ لا تُفحص هنا فيبقى ما عداه عرضاً."""
    out = []
    for pr in sorted(prs, key=lambda p: p["number"]):
        if pr.get("state") != "MERGED":
            continue
        marks = [m.group(0) for m in CODE.finditer(pr.get("title") or "")]
        marks += [f"W-{m.group(1)}-{m.group(2)}" for m in BRANCH_CODE.finditer(pr.get("headRefName") or "")]
        for code in dict.fromkeys(marks):
            item = items.get(code)
            if not item or item.get("state") not in ("approved", "pushed"):
                continue
            approved = item.get("approved_head")
            exact = _head_matches(approved, pr.get("headRefOid"))
            # الرأسُ المعتمَد أحدُ آباء رأس الطلب (دمجُ main فوقه بعد الاعتماد): يُقبل بدليلٍ من المصدر، وغيابُ الفحص يبقى عرضاً
            parent = (not exact) and ancestor is not None and len((approved or "").strip()) >= 8 and ancestor(pr, approved) is True
            if exact or parent:
                out.append({"card": code, "from": item["state"], "pr": pr["number"], "approved_head": approved, "ancestor": parent})
    return out


def apply_candidates(cands: list[dict], move=None, by: str = "reconcile") -> dict:
    """يكتب merged للمرشّحين (وضع الكتابة): approved تمرّ بـpushed أولاً كما يشترط الدفتر؛ فشلُ بطاقةٍ لا يوقف الباقي ويُبلَّغ."""
    move = move or ledger.move
    done, failed = [], []
    for c in cands:
        why = f"مدموج #{c['pr']}" + (" (الرأس المعتمَد أحدُ آباء رأس الطلب)" if c.get("ancestor") else "")
        try:
            if c["from"] == "approved":
                move(c["card"], "pushed", head=c.get("approved_head"), by=by, waive_remote_check=why, note=f"مصالحة: {why}")
            move(c["card"], "merged", by=by, note=f"مصالحة: {why}")
            done.append(c["card"])
        except Exception as exc:  # noqa: BLE001 — بوّابةُ الدفتر قد ترفض؛ تبقى البطاقةُ عرضاً
            failed.append({"card": c["card"], "why": f"{type(exc).__name__}: {exc}"})
    return {"written": done, "failed": failed}


def reconcile(
    items: dict[str, dict],
    prs: list[dict],
    published=None,
    branches: list[str] | None = None,
) -> dict:
    """{suggestions, ahead, unconfirmed}؛ كلُّ اقتراحٍ يحمل الدليلَ (رقمُ الطلب وموضعُ الرمز).

    `published(pr) -> (bool|None, evidence)`: هل رأسُ دمج الطلب محتوًى في آخر نشر production ناجح؟ None = غير مقيس.
    `branches`: أسماءُ فروع origin؛ فرعٌ يحمل رمزَ بطاقةٍ دون pushed يقترح pushed (الاعتماد approved لا يُمسّ أبداً)."""
    suggestions, unconfirmed = [], []
    for pr in sorted(prs, key=lambda p: p["number"]):
        for code, where in codes_of(pr):
            item = items.get(code)
            if item is None or item["state"] not in RANK:
                continue
            cur = RANK[item["state"]]
            target = {"MERGED": "merged", "OPEN": "pushed"}.get(pr["state"])
            if target is None:
                unconfirmed.append(
                    {
                        "card": code,
                        "state": item["state"],
                        "pr": pr["number"],
                        "why": "طلبٌ مغلقٌ بلا دمج",
                    }
                )
                continue
            if RANK[target] > cur:
                suggestions.append(
                    {
                        "card": code,
                        "from": item["state"],
                        "to": target,
                        "pr": pr["number"],
                        "evidence": f"الرمز في {where} من #{pr['number']}",
                    }
                )
    suggested = {x["card"] for x in suggestions}
    for name in branches or []:
        for m in BRANCH_CODE.finditer(name):
            code = f"W-{m.group(1)}-{m.group(2)}"
            item = items.get(code)
            if item and code not in suggested and RANK.get(item["state"], 99) < RANK["pushed"]:
                suggestions.append(
                    {
                        "card": code,
                        "from": item["state"],
                        "to": "pushed",
                        "pr": None,
                        "evidence": f"الفرع {name} على origin",
                    }
                )
                suggested.add(code)
    by_card: dict[str, list[dict]] = {}
    for pr in prs:
        for code, _ in codes_of(pr):
            by_card.setdefault(code, []).append(pr)
    ahead = []
    for code, item in items.items():
        found = by_card.get(code, [])
        if (
            RANK.get(item["state"], -1) >= RANK["merged"]
            and found
            and not any(p["state"] == "MERGED" for p in found)
        ):
            ahead.append(
                {
                    "card": code,
                    "state": item["state"],
                    "prs": [p["number"] for p in found],
                    "why": "الدفتر متقدّمٌ على GitHub: لا طلبَ مدموجاً بهذا الرمز",
                }
            )
    merged_prs = {c: [p for p in ps if p["state"] == "MERGED"] for c, ps in by_card.items()}
    for code, item in items.items():
        if item["state"] != "merged":
            continue
        verdict, evidence = (None, "غير مقيس: لا فحصَ نشر")
        for pr in merged_prs.get(code, []):
            if published is not None:
                verdict, evidence = published(pr)
                break
        if verdict is True:
            suggestions.append(
                {"card": code, "from": "merged", "to": "published", "pr": None, "evidence": evidence}
            )
        else:
            unconfirmed.append({"card": code, "state": "merged", "why": f"published غير مؤكد — {evidence}"})
    return {"suggestions": suggestions, "ahead": ahead, "unconfirmed": unconfirmed}


def fetch_prs(repo: str, limit: int) -> list[dict] | None:
    try:
        p = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "all",
                "--limit",
                str(limit),
                "--json",
                "number,title,headRefName,headRefOid,state,body,mergeCommit",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError:
        return None
    return json.loads(p.stdout) if p.returncode == 0 else None


def make_ancestor_check(repo: str):
    """`ancestor(pr, approved) -> True|False|None`: هل الرأسُ المعتمَد في تاريخ رأس الطلب؟ (compare API؛ None = غير مقيس)."""
    def check(pr: dict, approved: str):
        head = pr.get("headRefOid")
        if not head:
            return None
        data = _gh_json(["api", f"repos/{repo}/compare/{approved}...{head}"])
        if not isinstance(data, dict):
            return None
        return data.get("status") in ("ahead", "identical")

    return check


def _gh_json(args: list[str]):
    try:
        p = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:
        return None
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout)
    except ValueError:
        return None


def branch_last_commit(repo: str, branch: str) -> dt.datetime | None:
    b = _gh_json(["api", f"repos/{repo}/branches/{branch}", "--jq", "{d: .commit.commit.committer.date}"])
    try:
        return dt.datetime.fromisoformat(b["d"].replace("Z", "+00:00")) if b else None
    except (KeyError, ValueError, TypeError):
        return None


def fetch_branches(repo: str) -> list[str] | None:
    refs = _gh_json(["api", f"repos/{repo}/git/matching-refs/heads/claude", "--paginate", "--jq", "[.[].ref]"])
    return [r.removeprefix("refs/heads/") for r in refs] if isinstance(refs, list) else None


def latest_prod_deploy(repo: str) -> str | None:
    """رأسُ آخر نشر production بحالة success؛ None إن لم يُقَس."""
    deps = _gh_json(["api", f"repos/{repo}/deployments?per_page=15"])
    for d in deps or []:
        if "production" not in (d.get("environment") or ""):
            continue
        sts = _gh_json(["api", f"repos/{repo}/deployments/{d['id']}/statuses?per_page=1"])
        if sts and sts[0].get("state") == "success":
            return d["sha"]
    return None


def make_published_check(repo: str, deploy_sha: str | None):
    def check(pr: dict):
        mc = (pr.get("mergeCommit") or {}).get("oid")
        if not mc or not deploy_sha:
            return None, "غير مقيس: لا رأسُ دمجٍ أو لا نشرٌ ناجح"
        cmp_ = _gh_json(["api", f"repos/{repo}/compare/{mc}...{deploy_sha}", "--jq", "{status: .status}"])
        if not cmp_:
            return None, "غير مقيس: تعذّرت المقارنة"
        ok = cmp_.get("status") in ("ahead", "identical")
        return ok, f"رأس الدمج {mc[:8]} {'محتوًى في' if ok else 'غير محتوًى في'} آخر نشر production {deploy_sha[:8]}"

    return check


def write_report(res: dict, root: Path | None = None) -> Path:
    """تقريرُ العرض اليوميّ: لا يكتب في الدفتر؛ ملفّان خارج events.jsonl."""
    import datetime

    root = root or HERE.parent
    (root / "ledger").mkdir(exist_ok=True)
    (root / "ledger" / "reconcile_latest.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (root / "reports").mkdir(exist_ok=True)
    day = root / "reports" / f"reconcile_{datetime.date.today().isoformat()}.md"
    lines = ["# مصالحة الدفتر مع GitHub — عرضٌ فقط (لا كتابة)", ""]
    lines.append(f"اقتراحات: {len(res['suggestions'])}")
    lines += [f"- {x['card']}: {x['from']} ← {x['to']} — {x['evidence']}" for x in res["suggestions"]]
    lines.append(f"الدفتر متقدّم على GitHub: {len(res['ahead'])}")
    lines += [f"- {x['card']}: {x['state']} — الطلبات {x['prs']}" for x in res["ahead"]]
    lines.append(f"غير مؤكد: {len(res['unconfirmed'])}")
    st = res.get("stale") or {}
    lines.append(f"راكدة تُعاد لطابور 0101 (عرض): {len(st.get('return_to_queue', []))}")
    lines += [f"- {x['card']} ({x['holder']}): {x['state']} بلا نشاطٍ {x['idle_h']} س" for x in st.get("return_to_queue", [])]
    lines.append(f"معتمَدة بلا دفع تُنبَّه (عرض): {len(st.get('nudge', []))}")
    lines += [f"- {x['card']} ({x['holder']}): تنتظر {x['waiting_h']} س" for x in st.get("nudge", [])]
    if res.get("unmeasured"):
        lines.append("غير مقيس: " + "، ".join(res["unmeasured"]))
    day.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    return day


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default="sh-school/shschool_mvp")
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write", action="store_true", help="يكتب merged للمرشّحين المؤكَّدين فقط (رمزٌ في العنوان/الفرع + رأسٌ معتمَد أو أحدُ آباء رأس الطلب)؛ بدونه عرضٌ فقط")
    ap.add_argument("--report", action="store_true", help="يكتب ledger/reconcile_latest.json وتقريرَ اليوم reports/reconcile_YYYY-MM-DD.md (عرضٌ فقط)")
    a = ap.parse_args()
    prs = fetch_prs(a.repo, a.limit)
    if prs is None:
        print("غير مقيس: gh غير متاح — لا اقتراح")
        return 0
    branches = fetch_branches(a.repo)
    check = make_published_check(a.repo, latest_prod_deploy(a.repo))
    state = ledger.reduce_state(ledger.load_events())
    res = reconcile(state, prs, check, branches)
    res["stale"] = stale_policy.plan(
        state, dt.datetime.now(dt.timezone.utc).astimezone(), branches, lambda b: branch_last_commit(a.repo, b)
    )
    res["unmeasured"] = [n for n, v in (("branches", branches),) if v is None]
    if a.write:
        cands = write_candidates(state, prs, make_ancestor_check(a.repo))
        res["write"] = apply_candidates(cands)
        print(f"كُتب merged: {len(res['write']['written'])}؛ رُفض: {len(res['write']['failed'])}", file=sys.stderr)
    if a.report:
        write_report(res)
    if a.json:
        print(json.dumps(res, ensure_ascii=False))
        return 0
    print(f"اقتراحات (ظلّ، لا كتابة): {len(res['suggestions'])}")
    for s in res["suggestions"]:
        print(f"  {s['card']}: {s['from']} ← {s['to']} — {s['evidence']}")
    print(f"الدفتر متقدّم على GitHub: {len(res['ahead'])}")
    for s in res["ahead"]:
        print(f"  {s['card']}: {s['state']} — الطلبات {s['prs']} غير مدموجة")
    print(f"غير مؤكد: {len(res['unconfirmed'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
