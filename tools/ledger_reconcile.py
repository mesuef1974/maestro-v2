#!/usr/bin/env python3
"""مصالحةُ الدفتر مع GitHub (وضع الظلّ) — W-20261016-022 (المكوّن C): تقترح نقلَ pushed/merged بدليلٍ يسمّي رمزَ البطاقة.

    python ledger_reconcile.py [--repo sh-school/shschool_mvp] [--limit 400] [--json]

للقراءة فقط: لا يكتب في الدفتر أبداً (فرقُ الدفتر قبل/بعد صفر). المطابقةُ بالرمز W-… في **اسم الفرع أو عنوان الطلب أو سطرٍ
صريحٍ «بطاقةُ الدفتر: W-…» في أوّل الوصف** وحدها؛ فرمزٌ يُذكر عَرَضاً في متن الوصف («مستقلّة عنه W-…» كطلب #913) لا يطابق.
ولا اقتراحَ لـpublished (لا دليلَ نشرٍ هنا) فيُعرض «غير مؤكد». وغيابُ gh يطبع «غير مقيس» ولا يقترح شيئاً.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ledger  # noqa: E402

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


def reconcile(items: dict[str, dict], prs: list[dict]) -> dict:
    """{suggestions: [...], unconfirmed: [...]}؛ كلُّ اقتراحٍ يحمل الدليلَ (رقمُ الطلب وموضعُ الرمز)."""
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
    for code, item in items.items():
        if item["state"] == "merged":
            unconfirmed.append(
                {
                    "card": code,
                    "state": "merged",
                    "why": "نقلُها إلى published بلا دليل نشرٍ هنا — غير مؤكد",
                }
            )
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
                "number,title,headRefName,state,body",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError:
        return None
    return json.loads(p.stdout) if p.returncode == 0 else None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default="sh-school/shschool_mvp")
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    prs = fetch_prs(a.repo, a.limit)
    if prs is None:
        print("غير مقيس: gh غير متاح — لا اقتراح")
        return 0
    res = reconcile(ledger.reduce_state(ledger.load_events()), prs)
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
