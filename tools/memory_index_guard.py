#!/usr/bin/env python3
"""حارسُ فهرس الذاكرة (PreToolUse hook) — W-20261013-030، أمرُ المالك «تثبيت الفهرس».

الجذر: `MEMORY.md` يُحقَن كاملاً (≈9 آلاف رمز) في كلّ جلسةٍ حيّة كلّما عدّلتْه جلسة (714 حدثَ إعادة
حقنٍ في 31 جلسةً خلال 7 أيّام، docs/token_baseline_2026-10-13.md). فالتعديلُ مرّةً يوميّاً بيد 0103 وحدها،
وتكتب كلُّ جلسةٍ أخرى ذاكرتَها في `memory/on_demand/` وسطرَها في `INDEX_violations_pending.md` فتدخل الفهرسَ بتنقيح 0103.

    وضعان كـlang_guard: warn (الافتراضي) يحقن تنبيهاً، وblock يمنع. يُحدَّدان بمتغيّر MEMORY_INDEX_GUARD_MODE
    أو الملفّ memory_index_guard.mode في جذر delivery_manager_work.
    هويّة الجلسة من cwd عبر session_names.json (كـsession_identity). 0103 وحدها تُسمح.
    لا يُسقط الجلسة: أيّ خللٍ = سماح. القراءةُ (cat/grep/Read) مسموحةٌ دائماً.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODE_FILE = ROOT / "memory_index_guard.mode"
NAMES = ROOT / "projects" / "schoolos" / "session_names.json"
ALLOWED_ROLE = "0103"
TARGET = re.compile(r"projects[/\\]+D--shschool-mvp[/\\]+memory[/\\]+MEMORY\.md", re.I)
#: أوامرُ Bash التي تكتب (لا القراءة): إعادة توجيه، sed -i، tee، نقل/نسخ/حذف، أدوات كتابة PowerShell وبايثون.
WRITE_HINT = re.compile(
    r"(>>?|\btee\b|\bsed\s+-[a-z]*i|\bmv\b|\bcp\b|\brm\b|\btruncate\b|Set-Content|Add-Content|Out-File|"
    r"Remove-Item|Move-Item|Copy-Item|\.write_text|\.write\(|open\([^)]*['\"][wa]|os\.replace|shutil\.)",
    re.I,
)
MESSAGE = (
    "فهرس الذاكرة MEMORY.md يعدّله 0103 وحدها مرّةً يوميّاً (W-20261013-030): كلُّ تعديلٍ يعيد حقنه كاملاً "
    "في كلّ جلسةٍ حيّة. اكتبي ذاكرتَك في memory/on_demand/<النوع>_<الاسم>.md وأضيفي سطرَها إلى "
    "memory/on_demand/INDEX_violations_pending.md، ولا تمسّي الفهرس؛ فتدخله 0103 بالتنقيح اليوميّ. "
    "المخالفةُ العاجلة تُسجَّل في الملفّين فوراً ولا تضيع."
)


def mode() -> str:
    env = os.environ.get("MEMORY_INDEX_GUARD_MODE", "").strip().lower()
    if env in ("warn", "block"):
        return env
    try:
        text = MODE_FILE.read_text(encoding="utf-8").strip().lower()
        return text if text in ("warn", "block") else "warn"
    except OSError:
        return "warn"


def role_of(cwd: str) -> str | None:
    """رقمُ الدور من مجلّد العمل؛ None إن لم يُعرف (فنسمح)."""
    parts = Path(str(cwd).replace("\\", "/")).parts
    tree = next((parts[i + 1] for i, p in enumerate(parts) if p == "worktrees" and i + 1 < len(parts)), None)
    if not tree:
        return None
    try:
        title = json.loads(NAMES.read_text(encoding="utf-8")).get(tree)
    except (OSError, ValueError):
        return None
    m = re.match(r"\s*(\d{2,4})", title or "")
    return m.group(1) if m else None


def touches_index(tool: str, tool_in: dict) -> bool:
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return bool(TARGET.search(str(tool_in.get("file_path", ""))))
    if tool == "Bash":
        cmd = str(tool_in.get("command", ""))
        return bool(TARGET.search(cmd) or "MEMORY.md" in cmd) and bool(WRITE_HINT.search(cmd))
    return False


def log(payload: dict, role: str | None, verdict: str) -> None:
    try:
        from datetime import datetime, timezone

        row = "|".join(
            [datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), str(payload.get("session_id", ""))[:8], role or "-", verdict]
        )
        with open(MODE_FILE.with_name("memory_index_guard.log"), "a", encoding="utf-8") as fh:
            fh.write(row + "\n")
    except Exception:  # noqa: BLE001 — السجل لا يُسقط الحارس
        pass


def decide(payload: dict) -> tuple[str, str]:
    """('allow'|'warn'|'deny', الرسالة)."""
    tool = str(payload.get("tool_name", ""))
    if not touches_index(tool, payload.get("tool_input") or {}):
        return "allow", ""
    role = role_of(payload.get("cwd", ""))
    if role is None or role == ALLOWED_ROLE:
        return "allow", ""
    return ("deny" if mode() == "block" else "warn"), MESSAGE


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        verdict, msg = decide(payload)
        if verdict == "allow":
            return 0
        log(payload, role_of(payload.get("cwd", "")), verdict)
        if verdict == "deny":
            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": msg}}
        else:
            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}}
        print(json.dumps(out, ensure_ascii=False))
    except Exception:  # noqa: BLE001 — الحارس لا يُسقط الجلسة
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
