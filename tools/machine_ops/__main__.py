"""سطرُ الأوامر: python -m machine_ops (من مجلّد tools) — المرحلة 1 قراءةٌ فقط."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import history, report, snapshot


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="قياس الجهاز قبل/بعد (قراءةٌ فقط)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot", help="لقطةٌ تُطبع JSON أو تُحفظ بـ--out")
    s.add_argument("--label", default="لقطة")
    s.add_argument("--out", type=Path)
    r = sub.add_parser("report", help="تقريرُ قبل/بعد من ملفّي لقطتين")
    r.add_argument("before", type=Path)
    r.add_argument("after", type=Path)
    h = sub.add_parser("history", help="ملخّصُ عيّنات monitor.db بنسخةٍ مؤقّتة وبصمةٍ قبل/بعد")
    h.add_argument("--db", type=Path, required=True)
    h.add_argument("--hours", type=float, default=24)
    a = ap.parse_args(argv)
    if a.cmd == "snapshot":
        text = snapshot.dumps(snapshot.take(a.label))
        if a.out:
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_text(text, encoding="utf-8")
        else:
            print(text)
    elif a.cmd == "report":
        print(report.render(json.loads(a.before.read_text(encoding="utf-8")), json.loads(a.after.read_text(encoding="utf-8"))))
    else:
        now = int(time.time())
        rows, fp = history.read_samples(a.db, now - int(a.hours * 3600), now)
        print(json.dumps({"summary": history.summarize(rows), "original_unchanged_by_tool": fp["unchanged"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
