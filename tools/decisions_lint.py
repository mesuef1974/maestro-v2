#!/usr/bin/env python3
"""فحصُ سلامة سجلّ القرارات decisions.md: تكرارُ نصٍّ، رقمٌ مكرَّرٌ أو متخطّى، طابعُ زمنٍ يرجع إلى الوراء.

    python decisions_lint.py [--since 80] [--file path]

قراءةٌ فقط؛ يخرج برمز 1 إن وُجدت ملاحظات. السجلُّ يُلحَق فقط — الفحصُ يكشف ولا يعدّل (D-107م: سلامةُ المعلومة).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = re.compile(r"^- D-(\d+)م(-[ء-ي])? \| ([^|]*)\| (.*)$")
# تكراراتٌ تاريخيّةٌ (كتلتان من جلستين في 10-22 و10-23) لا تُعاد ترقيمها لأنّ إحالاتِ القرارات اللاحقة إليها ملتبسة؛ كلُّ تكرارٍ جديدٍ خارجَها يُرفض (W-20261028-023، D-499م R7)
LEGACY_DUPLICATES = frozenset(range(476, 485)) | {486}
STAMP = re.compile(r"(\d{2})-(\d{2})(?:\s+(?:~|≈)?(\d{1,2}):(\d{2}))?")


def parse(text: str) -> list[dict]:
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        m = ENTRY.match(line)
        if not m:
            continue
        s = STAMP.search(m.group(3))
        stamp = None
        if s and s.group(3):
            stamp = (int(s.group(1)), int(s.group(2)), int(s.group(3)), int(s.group(4)))
        body = re.sub(r"[\W_]+", "", m.group(4).split("|")[0])[:140]
        out.append({"num": int(m.group(1)), "suffix": m.group(2), "line": n, "stamp": stamp, "key": body,
                    "event_time": "وقتُ الحدث" in m.group(3)})
    return out


def lint(entries: list[dict], since: int = 0) -> list[str]:
    notes: list[str] = []
    seen_nums: dict[int, int] = {}
    seen_keys: dict[str, int] = {}
    prev = None
    for e in entries:
        if e["num"] < since:
            prev = e if e["stamp"] else prev
            continue
        if e["num"] in seen_nums and not e["suffix"] and e["num"] not in LEGACY_DUPLICATES:
            notes.append(f"D-{e['num']}م: رقمٌ مكرَّر (السطر {seen_nums[e['num']]} و{e['line']})")
        seen_nums.setdefault(e["num"], e["line"])
        if e["key"] and e["key"] in seen_keys:
            notes.append(f"D-{e['num']}م: نصٌّ مكرَّرٌ لقرارٍ سابق (السطر {seen_keys[e['key']]} و{e['line']})")
        seen_keys.setdefault(e["key"], e["line"])
        if prev and e["stamp"] and prev["stamp"] and e["stamp"] < prev["stamp"] and not e["event_time"]:
            notes.append(f"D-{e['num']}م: طابعُ زمنٍ أسبقُ من D-{prev['num']}م الذي قبلَه (السطر {e['line']})")
        if e["stamp"]:
            prev = e
    nums = sorted(n for n in seen_nums if n >= since)
    for a, b in zip(nums, nums[1:]):
        if b - a > 1:
            notes.append(f"فجوةٌ في الترقيم بين D-{a}م وD-{b}م")
    return notes


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", type=int, default=0, help="يبدأ الفحصَ من هذا الرقم")
    ap.add_argument("--file", default=str(ROOT / "decisions.md"))
    args = ap.parse_args()
    f = Path(args.file)
    arch = f.with_name("decisions_archive.md")  # الأرشيفُ أولاً ليبقى الترتيبُ والأرقامُ متّصلة (W-20261025-016)
    text = (arch.read_text(encoding="utf-8") + chr(10) if arch.is_file() else "") + f.read_text(encoding="utf-8")
    notes = lint(parse(text), args.since)
    print("\n".join(notes) if notes else "سجلُّ القرارات سليم")
    return 1 if notes else 0


if __name__ == "__main__":
    raise SystemExit(main())
