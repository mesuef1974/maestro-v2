"""يركّب خطّاف post-commit ليعمل tools/daily_push.py بعد كل إيداع (قرار المالك 2026-11-06).

يشغّله المالك بنفسه مرة واحدة. الدفع في الخلفية فلا يؤخّر الإيداع، والفحص والحظر في daily_push.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".git" / "hooks" / "post-commit"
PYTHONW = Path(sys.executable).with_name("pythonw.exe")
BODY = f"""#!/bin/sh
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE
"{PYTHONW.as_posix()}" "{(ROOT / 'tools' / 'daily_push.py').as_posix()}" >/dev/null 2>&1 &
"""


def main() -> int:
    if HOOK.exists() and HOOK.read_text(encoding="utf-8") != BODY:
        print(f"يوجد خطّاف آخر، فلم يُستبدل: {HOOK}")
        return 1
    HOOK.write_text(BODY, encoding="utf-8", newline="\n")
    print(f"رُكّب الخطّاف: {HOOK}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
