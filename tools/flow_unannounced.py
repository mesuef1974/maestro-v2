#!/usr/bin/env python3
"""إصداراتُ الفلو التي لم تُبلَّغ بعد (W-20261014-014) — قراءةٌ فقط من flow_changelog.md.

    python flow_unannounced.py [--json] [--notice]

يعدّ أسطرَ الإصدارات بوسم «لم تُبلَّغ بعد» أو «مسوّدة» ويطبع الإصدارَ والقرار؛ وأيُّ سطرِ إصدارٍ بلا وسمِ إبلاغٍ معروف
يُبلَّغ عنه «تنسيقٌ غيرُ معروف» ولا يُعدّ. و`--notice` يطبع تبليغاً من ثلاثة أسطر لكلّ إصدارٍ معلّق من نصّ السطر نفسه.
لا تعدّل الأداةُ السجلَّ: إزالةُ الوسم تتمّ بعد الإرسال الفعليّ بيد من أرسل.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "flow_changelog.md"
ROW = re.compile(r"^(?:\|\s*|-\s+\*\*)(v\d+\.\d+)\b")
DECISION = re.compile(r"D-\d+م")
BOLD = re.compile(r"\*\*(.+?)\*\*")
PENDING, ANNOUNCED, UNKNOWN = "pending", "announced", "unknown"


def classify(line: str) -> str:
    if "لم تُبلَّغ بعد" in line or "مسوّدة" in line:
        return PENDING
    if "أُبلغت" in line:
        return ANNOUNCED
    return UNKNOWN


def parse(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        rows.append({"version": m.group(1), "status": classify(line), "decision": (DECISION.findall(line) or ["—"])[0], "line": line})
    return rows


def notice(row: dict) -> str:
    """تبليغٌ من ثلاثة أسطر من نصّ السطر نفسه: العنوان (أوّلُ غامقٍ بعد الوسم)، ثمّ المقتطف، ثمّ المرجع."""
    text = row["line"].split("|", 4)[-1] if row["line"].startswith("|") else row["line"]
    text = re.sub(r"\*\*\((?:[^)]*تُبلَّغ[^)]*|[^)]*مسوّدة[^)]*|[^)]*أُبلغت[^)]*)\)\*\*", "", text)
    plain = re.sub(r"\s+", " ", text.replace("**", "")).strip(" |-*")
    title, _sep, rest = plain.partition(":")
    title = title.strip() or row["version"]
    body = rest.strip()[:160] or plain[:160]
    return (f"إصدار الفلو {row['version']} ({row['decision']}): {title}\n"
            f"ما يتغيّر: {body}\n"
            f"المرجع: flow_changelog.md سطر {row['version']}؛ ولا يُبلَّغ ثانيةً بعد إزالة وسم «لم تُبلَّغ بعد» بيد المرسِل.")


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--notice", action="store_true")
    ap.add_argument("--file", default=str(CHANGELOG))
    a = ap.parse_args(argv)
    rows = parse(Path(a.file).read_text(encoding="utf-8"))
    pending = [r for r in rows if r["status"] == PENDING]
    unknown = [r for r in rows if r["status"] == UNKNOWN]
    if a.json:
        print(json.dumps({"pending": [r["version"] for r in pending], "unknown": [r["version"] for r in unknown],
                          "total": len(rows)}, ensure_ascii=False))
        return 0
    print(f"إصداراتٌ لم تُبلَّغ بعد: {len(pending)} من {len(rows)}")
    for r in pending:
        print(f"  {r['version']} — {r['decision']}")
        if a.notice:
            print("    " + notice(r).replace("\n", "\n    "))
    if unknown:
        print(f"تنسيقٌ غيرُ معروف (بلا وسم إبلاغ، لا يُعدّ): {', '.join(r['version'] for r in unknown)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
