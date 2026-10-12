#!/usr/bin/env python3
"""حارسُ العربيّة الآليّ (PreToolUse hook) — نموذجٌ غير مسجَّل بانتظار قرار المالك.

الجذر: قاعدة «العربيّة وحدها في المحادثة وأسطر الحالة ووصف الأدوات» نصٌّ في الذاكرة والبطاقات،
ولا شيء يتحقّق منها، والإنجليزيّة عادةُ توليدٍ تسبق الأداة. فالحارس يقرأ ما سيظهر للمالك:
  1) حقل description في مدخلات الأداة.
  2) آخر مقطع نصّيّ كتبه المساعد قبل هذا الاستدعاء (من transcript_path).
فإن غلبت عليه الإنجليزية مُنع الاستدعاء برسالة عربيّة تطلب إعادة الصياغة بالعربيّة.

الوضعان كـidentity_guard: warn (الافتراضي) يحقن تحذيراً، وblock يمنع؛ بمتغير LANG_GUARD_MODE
أو الملفّ lang_guard.mode. لا يُسقط الجلسة: أيّ خللٍ = سماح.
المستثنى من العدّ: الشيفرة والمسارات والروابط والمعرّفات؛ والشرط: 4 كلماتٍ لاتينيّة فأكثر وأحرفٌ عربيّة لا تزيد على ضعف عددها (الكلمات اللاتينيّة نحو ضعف العربيّة فأكثر، والكلمة العربيّة ≈ 4 أحرف). ثغرة معروفة: وصفٌ قصير مثل «Run the tests» يمرّ.
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
#: حدّا المنع (D-411م): وصفُ الأداة 3 كلماتٍ لاتينيّة فأكثر؛ والنصُّ 6 فأكثر. ما بين 4 و5 في النصّ تحذيرٌ فقط.
DESC_BLOCK_WORDS = 3
TEXT_BLOCK_WORDS = 6
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


def is_english(text: str, min_words: int = MIN_WORDS) -> bool:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"https?://\S+|[A-Za-z]:[\\/]\S+|\S+[\\/]\S+|\S+_\S+", "", text)
    words = LAT.findall(text)
    return len(words) >= min_words and len(AR.findall(text)) <= len(words) * 2


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


def log(payload: dict, offenders: list) -> None:
    """سطرٌ لكل استدعاء في lang_guard.log: الوقت|الجلسة|المجلد|المخالف — لقياس أسبوع warn."""
    try:
        from datetime import datetime, timezone
        row = "|".join([datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), str(payload.get("session_id", ""))[:8],
                        os.path.basename(str(payload.get("cwd", ""))), ",".join(offenders) or "-"])
        with open(MODE_FILE.with_name("lang_guard.log"), "a", encoding="utf-8") as fh:
            fh.write(row + chr(10))
    except Exception:  # noqa: BLE001 — السجل لا يُسقط الحارس
        pass


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        tool_in = payload.get("tool_input") or {}
        offenders, hard = [], False
        if is_english(str(tool_in.get("description", "")), DESC_BLOCK_WORDS):
            offenders.append("وصف الأداة")
            hard = True
        before = last_assistant_text(payload.get("transcript_path", ""))
        if is_english(before, MIN_WORDS):
            offenders.append("النصّ الذي كتبتَه قبل الأداة")
            hard = hard or is_english(before, TEXT_BLOCK_WORDS)
        log(payload, offenders)
        if not offenders:
            return 0
        msg = (
            "القاعدة: العربيّة وحدها في المحادثة وأسطر الحالة ووصف الأدوات. غلبت الإنجليزيّة على: "
            + "، ".join(offenders)
            + ". أعد الصياغة بالعربيّة ثمّ أعد الاستدعاء (الأسماء والأوامر والمسارات تبقى كما هي)."
        )
        if mode() == "block" and hard:
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
