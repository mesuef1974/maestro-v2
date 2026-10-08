#!/usr/bin/env python3
"""بطاقاتٌ دُمجت طلباتُها وبقيت «approved» — يكشفها ويطبع أوامر نقلها (0102، 2026-10-08).

    python merged_cards_sync.py            # عرضٌ فقط: القائمة وأوامر ledger.py الجاهزة
    python merged_cards_sync.py --limit 80 # عدد الطلبات المدموجة المفحوصة (الافتراضيّ 60)

يقابل `approved_head` في آخر حدث حالةٍ للبطاقة برأس طلبٍ **MERGED** في GitHub. التنفيذُ لجلسة الدمج (0601) وحدَها
(D-88م): هذه الأداةُ لا تنقل شيئاً، وتطبع الأمر كما يُشغَّل. سببُها: يوم 2026-10-08 بقيت خمسُ بطاقاتٍ approved ساعتين فأكثر
بعد دمج طلباتها (انظر docs/flow_compliance_v2_2026-10-08.html).
"""
from __future__ import annotations

import argparse
import json
import subprocess

import ledger

SLUG = "sh-school/shschool_mvp"


def merged(limit: int) -> dict[str, tuple[int, str]]:
    out = subprocess.run(
        ["gh", "pr", "list", "--repo", SLUG, "--state", "merged", "--limit", str(limit), "--json", "number,headRefOid,mergedAt"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if out.returncode:
        raise SystemExit("فشل gh: " + (out.stderr or "").strip()[:200])
    return {p["headRefOid"][:8]: (p["number"], p["mergedAt"]) for p in json.loads(out.stdout)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    a = ap.parse_args()
    last = {}
    for e in ledger.load_events():
        if e["kind"] == "state":
            last[e["id"]] = e
    prs = merged(a.limit)
    hits = []
    for cid, e in last.items():
        d = e["data"]
        head = (d.get("head") or d.get("approved_head") or "")[:8]
        if d.get("state") == "approved" and head in prs:
            hits.append((cid, head, *prs[head]))
    print(f"{len(hits)} بطاقة approved ودُمج طلبُها (من آخر {a.limit} طلباً مدموجاً)")
    for cid, head, num, at in sorted(hits):
        print(f"  {cid} #{num} دُمج {at[5:16]}Z")
        print(f"    python tools/ledger.py move {cid} published --head {head} --by 0601")
    if hits:
        print("بعد النقل: أبلغ 0701 برمز البطاقة ورقم الطلب (post_merge_checklist.py <رقم> --card <رمز>).")


main()
