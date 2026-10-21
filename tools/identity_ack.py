#!/usr/bin/env python3
"""إيصالُ قراءة قائمة المراجعة 95 (W-20261009-008) — يطبعها كاملةً ثمّ يسجّل إيصالاً ببصمتها.

    python identity_ack.py [--cwd <مسار الشجرة>]

الإيصالُ ملفٌّ في مجلّد git الخاصّ بالشجرة (`<git-dir>/identity_ack.json`) لا في شجرة العمل: غيرُ متتبَّعٍ ولا يظهر
في `git status` ولا يُودَع. فيه بصمةُ references/95-checklist.md ووقتُ القراءة ورأسُ HEAD وقتَها (D-376م: يربط الإيصالَ برأسٍ). ويبطل تلقائياً إن تغيّر الملفّ
(حدّثته ترقيةٌ لاحقة) فتُقرأ القائمةُ من جديد. يقرأه identity_guard.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import identity_guard as g  # noqa: E402


def current_head(top: Path) -> str:
    """رأسُ HEAD الكامل للشجرة وقتَ القراءة، أو فراغ إن تعذّر (الإيصالُ يبقى صالحاً بلا رأس)."""
    try:
        r = subprocess.run(["git", "-C", str(top), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cwd", default=os.getcwd())
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    top = g.toplevel(args.cwd)
    if top is None:
        print("هذا المسار ليس شجرةَ المنصّة (shschool_mvp)؛ شغّل الأمر من شجرتك.")
        return 2
    f = top / g.CHECKLIST
    if not f.is_file():
        print(f"قائمةُ المراجعة 95 غير موجودةٍ في شجرتك ({g.CHECKLIST}) — شجرتك بلا ترقية المهارة. "
              "ادمج origin/main أوّلاً (sync_with_base_branch) ثمّ أعد.")
        return 1
    data = f.read_bytes()
    print(data.decode("utf-8"))
    ap_ = g.ack_path(top)
    if ap_ is None:
        print("تعذّر تحديد مجلّد git للشجرة؛ لم يُسجَّل الإيصال.")
        return 1
    ap_.write_text(json.dumps({
        "sha256": hashlib.sha256(data).hexdigest(),
        "time": datetime.now(timezone(timedelta(hours=3))).isoformat(timespec="seconds"),
        "tree": top.name,
        "head": current_head(top),
    }, ensure_ascii=False), encoding="utf-8")
    print(f"\n[إيصال] سُجِّلت قراءةُ 95 للشجرة {top.name}. اعمل الآن وفق القائمة أعلاه؛ ويبطل الإيصالُ إن تغيّر الملفّ.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
