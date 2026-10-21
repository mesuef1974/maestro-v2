#!/usr/bin/env python3
"""حارسُ طول رسائل الجلسات (PreToolUse hook) — W-20261013-032، أمرُ المالك «إحالة الرسائل الطويلة لملفات».

الجذر: رسائلُ الجلسات الطويلة (3–6 ك.ب) تُحمَّل في سياق المستلم كاملةً ثمّ تبقى في كلّ طلبٍ لاحق.
القاعدة: رسالةٌ فوق العتبة تُكتب في `handover_notes/msg_<من>_<إلى>_<تاريخ>.md` ويُرسَل ملخّصٌ بخمسة أسطرٍ مع المسار.
المستثنى: القصيرةُ، وما فيه مسارُ ملفٍّ حقيقيّ في handover_notes أو docs، والعاجلةُ بوسم «[عاجل]».

    python message_length_guard.py            # hook (stdin)
    python message_length_guard.py --measure [--days 7]   # توزيع الأطوال في السجلّات (خطّ الأساس)

الوضعان: warn (الافتراضي) وblock؛ MESSAGE_LENGTH_GUARD_MODE أو الملفّ message_length_guard.mode. أيّ خللٍ = سماح.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODE_FILE = ROOT / "message_length_guard.mode"
LOGS = Path.home() / ".claude" / "projects"
#: عتبةٌ عند p90 المقيس (1007 حرفاً في 8,742 رسالة، 7 أيام) ويُعلَن الرقم النهائيّ في قرارٍ مسجَّل.
THRESHOLD = 1000
SEND_TOOLS = ("SendMessage", "mcp__ccd_session_mgmt__send_message")
URGENT = re.compile(r"^\s*\[\s*عاجل\s*\]")
FILE_REF = re.compile(r"(handover_notes[\/][\w.\-]+\.md|docs[\/][\w.\-]+\.(?:md|html))", re.I)
MESSAGE = (
    "رسالتك {n} حرفاً (العتبة {t}). الرسالةُ الطويلةُ تُحمَّل كاملةً في سياق المستلم وتبقى فيه. اكتبيها في "
    "handover_notes/msg_<من>_<إلى>_<التاريخ>.md وأرسلي ملخّصاً بخمسة أسطرٍ على الأكثر مع المسار؛ والمستلمُ يقرأ الملفّ عند الحاجة. "
    "للعاجل ابدأي الرسالة بـ«[عاجل]»."
)


def mode() -> str:
    env = os.environ.get("MESSAGE_LENGTH_GUARD_MODE", "").strip().lower()
    if env in ("warn", "block"):
        return env
    try:
        text = MODE_FILE.read_text(encoding="utf-8").strip().lower()
        return text if text in ("warn", "block") else "warn"
    except OSError:
        return "warn"


def body_of(tool: str, tool_in: dict) -> str | None:
    if tool not in SEND_TOOLS:
        return None
    return str(tool_in.get("message", ""))


def decide(payload: dict) -> tuple[str, str]:
    """('allow'|'warn'|'deny', الرسالة)."""
    text = body_of(str(payload.get("tool_name", "")), payload.get("tool_input") or {})
    if text is None or len(text) <= THRESHOLD or URGENT.search(text) or FILE_REF.search(text):
        return "allow", ""
    return ("deny" if mode() == "block" else "warn"), MESSAGE.format(n=len(text), t=THRESHOLD)


def log(payload: dict, verdict: str, n: int) -> None:
    try:
        from datetime import datetime, timezone

        row = "|".join([datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), str(payload.get("session_id", ""))[:8], verdict, str(n)])
        with open(MODE_FILE.with_name("message_length_guard.log"), "a", encoding="utf-8") as fh:
            fh.write(row + "\n")
    except Exception:  # noqa: BLE001 — السجل لا يُسقط الحارس
        pass


def measure(days: int) -> dict:
    """أطوال متون الرسائل المرسَلة في السجلّات (الجلسة الأمّ فقط): العدد، الوسيط، p90، فوق العتبة، مجموع الأحرف."""
    cut = time.time() - days * 86400
    lens: list[int] = []
    seen: set[str] = set()
    for f in LOGS.glob("*/**/*.jsonl"):
        if f.stat().st_mtime < cut or f.parent.name == "subagents":
            continue
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if "send_message" not in line and "SendMessage" not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    content = (d.get("message") or {}).get("content")
                    if d.get("type") != "assistant" or not isinstance(content, list):
                        continue
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in SEND_TOOLS:
                            if b.get("id") in seen:
                                continue
                            seen.add(b.get("id"))
                            lens.append(len(str((b.get("input") or {}).get("message", ""))))
        except OSError:
            continue
    if not lens:
        return {"count": 0}
    lens.sort()
    over = [n for n in lens if n > THRESHOLD]
    return {
        "count": len(lens),
        "median": int(statistics.median(lens)),
        "p90": lens[int(0.9 * (len(lens) - 1))],
        "max": lens[-1],
        "over_threshold": len(over),
        "over_threshold_chars": sum(over),
        "total_chars": sum(lens),
        "threshold": THRESHOLD,
    }


def main() -> int:
    if "--measure" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 7
        print(json.dumps(measure(days), ensure_ascii=False))
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        verdict, msg = decide(payload)
        if verdict == "allow":
            return 0
        log(payload, verdict, len(body_of(str(payload.get("tool_name")), payload.get("tool_input") or {}) or ""))
        if verdict == "deny":
            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": msg}}
        else:
            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}}
        print(json.dumps(out, ensure_ascii=False))
    except Exception:  # noqa: BLE001 — الحارس لا يُسقط الجلسة
        return 0
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
