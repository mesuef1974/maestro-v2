#!/usr/bin/env python3
"""حارسُ العربيّة الآليّ (PreToolUse hook) — نموذجٌ غير مسجَّل بانتظار قرار المالك.

الجذر: قاعدة «العربيّة وحدها في المحادثة وأسطر الحالة ووصف الأدوات» نصٌّ في الذاكرة والبطاقات،
ولا شيء يتحقّق منها، والإنجليزيّة عادةُ توليدٍ تسبق الأداة. فالحارس يقرأ ما سيظهر للمالك:
  1) حقل description في مدخلات الأداة.
  2) آخر مقطع نصّيّ كتبه المساعد قبل هذا الاستدعاء (من transcript_path).
فإن غلبت عليه الإنجليزية مُنع الاستدعاء برسالة عربيّة تطلب إعادة الصياغة بالعربيّة.

الوضعان كـidentity_guard: warn (الافتراضي) يحقن تحذيراً، وblock يمنع؛ بمتغير LANG_GUARD_MODE
أو الملفّ lang_guard.mode. لا يُسقط الجلسة: أيّ خللٍ = سماح.
المستثنى من العدّ: الشيفرة والمسارات والروابط والمعرّفات؛ ويكفي 4 كلماتٍ لاتينيّة تفوق نصف العربيّ.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

MODE_FILE = Path(__file__).resolve().parent.parent / "lang_guard.mode"
AR = re.compile(r"[؀-ۿ]")
LAT = re.compile(r"[A-Za-z]{3,}")
MIN_WORDS = 4
TAIL_BYTES = 400_000


def mode() -> str:
    env = os.environ.get("LANG_GUARD_MODE", "").strip().lower()
    if env in ("warn", "block"):
        return env
    try:
        text = MODE_FILE.read_text(encoding="utf-8").strip().lower()
        return text if text in ("warn", "block") else "warn"
    except OSError:
        return "warn"


def is_english(text: str) -> bool:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"https?://\S+|[A-Za-z]:[\\/]\S+|\S+[\\/]\S+|\S+_\S+", "", text)
    words = LAT.findall(text)
    return len(words) >= MIN_WORDS and len(AR.findall(text)) <= len(words) * 2


def last_assistant_text(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - TAIL_BYTES))
            lines = fh.read().decode("utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            msg = json.loads(line).get("message", {})
        except ValueError:
            continue
        if msg.get("role") == "user":
            return ""  # لا نصَّ كتبه المساعد منذ آخر مدخلٍ للمستخدم/نتيجة أداة
        content = msg.get("content")
        if msg.get("role") == "assistant" and isinstance(content, list):
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            if any(texts):
                return "\n".join(texts)
    return ""


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        tool_in = payload.get("tool_input") or {}
        offenders = []
        if is_english(str(tool_in.get("description", ""))):
            offenders.append("وصف الأداة")
        if is_english(last_assistant_text(payload.get("transcript_path", ""))):
            offenders.append("النصّ الذي كتبتَه قبل الأداة")
        if not offenders:
            return 0
        msg = (
            "القاعدة: العربيّة وحدها في المحادثة وأسطر الحالة ووصف الأدوات. غلبت الإنجليزيّة على: "
            + "، ".join(offenders)
            + ". أعد الصياغة بالعربيّة ثمّ أعد الاستدعاء (الأسماء والأوامر والمسارات تبقى كما هي)."
        )
        if mode() == "block":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                     "permissionDecisionReason": msg}}, ensure_ascii=False))
        else:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}},
                             ensure_ascii=False))
    except Exception:  # noqa: BLE001 — الحارس لا يُسقط الجلسة
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
