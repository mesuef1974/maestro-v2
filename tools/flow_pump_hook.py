#!/usr/bin/env python3
"""مشغّلُ مضخّة التدفّق من داخل الجلسات — بدل المهمّة المجدولة flow-pump-10min.

أمرُ المالك 2026-10-21: «ادمج المضخة لو سمحت في الجلسات كودا بدون بطاقة وادفعها وادمجها وانشرها انت».
فالمضخّةُ لا تنتظر ساعةً خارجيّة: تدور حين يتحرّك الفلو نفسُه في أيّ جلسة.

يُستدعى خطافاً عامّاً في ~/.claude/settings.json:
  - PostToolUse (Bash|PowerShell): بعد أمرٍ يحرّك الفلو (git push، gh pr create/merge/ready،
    ledger.py move/reapprove/waive-head، record_owner_confirmation، approval_check، ledger_sync)
    ← دورةٌ إن مضت دقيقةٌ على آخر دورة.
  - Stop وSessionStart: دورةٌ احتياطيّة إن مضت خمسُ دقائق على آخر دورة.
ولا يعمل إلا في جلسات المنصّة (shschool_mvp) والإدارة (delivery_manager_work).

لا يحجب الجلسة: يطلق `flow_pump.py --apply` منفصلاً ويخرج فوراً بصفرٍ دائماً، وقفلُ flow_pump
يمنع تداخل الدورات بين الجلسات. حدودُه حدودُ المضخّة وحرّاسُها (D-450م): يدفع الرأسَ المعتمَد ويكتب سطرَ الاعتماد
في الطلب ويطلب الدمجَ الآليّ عند خضرة CI، ولا يرسل رسائل. (`--no-push`/`--no-line`/`--no-merge` في flow_pump لتعطيل مرحلة.)
ومفتاحُ الإيقاف: وجودُ الملف ledger/flow_pump.off.

    python flow_pump_hook.py < hook.json    # كما يستدعيه الخطاف
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER_DIR = HERE.parent / "ledger"
STAMP = LEDGER_DIR / "flow_pump.stamp"
OFF = LEDGER_DIR / "flow_pump.off"
OUT = LEDGER_DIR / "flow_pump.out"
LOCK = LEDGER_DIR / "flow_pump.lock"  # قفلُ flow_pump نفسه
STALE_LOCK_S = 900

#: بطاقاتٌ تُستثنى من النقل كما كانت في المهمّة المجدولة.
SKIP = ("W-20261001-006",)

#: مهلةُ الدورة بعد أمرٍ يحرّك الفلو، ومهلةُ الدورة الاحتياطيّة عند ختام الدور أو بدء الجلسة.
FLOW_INTERVAL_S = 60
IDLE_INTERVAL_S = 300

FLOW_CMD = re.compile(
    r"\bgit\s+push\b"
    r"|\bgh\s+pr\s+(?:create|merge|ready)\b"
    r"|ledger\.py\s+(?:move|reapprove|waive-head)\b"
    r"|ledger_sync\.py"
    r"|record_owner_confirmation\.py"
    r"|approval_check\.py"
)
WORKSPACES = ("shschool_mvp", "delivery_manager_work")


def interval(event: str, tool: str, command: str) -> int | None:
    """مهلةُ الدورة لهذا الحدث، أو None إن لم يكن حدثاً يحرّك المضخّة."""
    if event in ("Stop", "SessionStart"):
        return IDLE_INTERVAL_S
    if event == "PostToolUse" and tool in ("Bash", "PowerShell") and FLOW_CMD.search(command or ""):
        return FLOW_INTERVAL_S
    return None


def in_workspace(cwd: str) -> bool:
    low = (cwd or "").replace("\\", "/").lower()
    return any(w in low for w in WORKSPACES)


def due(now: float, last: float | None, wait: int) -> bool:
    return last is None or now - last >= wait


def last_run() -> float | None:
    try:
        return STAMP.stat().st_mtime
    except OSError:
        return None


def pump_running(now: float) -> bool:
    """دورةٌ قائمةٌ تحمل القفل — فلا تُطلق أخرى تكتب فوق تقريرها."""
    try:
        return now - LOCK.stat().st_mtime < STALE_LOCK_S
    except OSError:
        return False


def spawn() -> None:
    """يطلق دورةَ المضخّة منفصلةً عن الجلسة؛ تقريرُها الأخير في ledger/flow_pump.out."""
    STAMP.touch()
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    with OUT.open("w", encoding="utf-8") as out:
        subprocess.Popen(
            [sys.executable, str(HERE / "flow_pump.py"), "--apply", "--skip", *SKIP],
            cwd=str(HERE.parent),
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=flags,
            close_fds=True,
        )


def decide(payload: dict, now: float, last: float | None, off: bool) -> bool:
    if off or not in_workspace(payload.get("cwd", "")):
        return False
    tool_input = payload.get("tool_input") or {}
    wait = interval(
        payload.get("hook_event_name", ""),
        payload.get("tool_name", ""),
        tool_input.get("command", "") if isinstance(tool_input, dict) else "",
    )
    return wait is not None and due(now, last, wait)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        now = time.time()
        if decide(payload, now, last_run(), OFF.exists()) and not pump_running(now):
            spawn()
    except Exception:  # الخطافُ لا يُسقط الجلسة أبداً
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
