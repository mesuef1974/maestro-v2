#!/usr/bin/env python3
"""خطّافُ PostToolUse: حين ترسل جلسةٌ «جاهزٌ للمعاينة» يُسجَّل الدفترُ ready_for_review بالرأس (W-20261015-015).

يقرأ JSON الخطّاف من stdin، ويتحقّق أنّ الرسالةَ تبدأ بـ«جاهزٌ للمعاينة» وفيها رقمُ الجلسة بين قوسين ورمزُ بطاقةٍ ورأسٌ بعد «الرأس»، ثمّ يستدعي
`ready_mark.mark` **وحدَه** (فتسري بوّاباتُه: الرأسُ موجودٌ ويحمل رمزَ البطاقة، والبطاقةُ ليست معتمدةً). لا يعتمد ولا يراسل ولا يعدّل إعداداتٍ.
والفشلُ دائماً بصمتٍ آمن: يخرج 0 ولا يحجب الأداةَ التي استُدعي بعدها؛ والسببُ يُكتب في logs/ready_mark_hook.log إن وُجد المجلّد.
وللجلسة أن تسجّل بنفسها بأداة ready_mark؛ هذا الخطّافُ لمن نسي.

الإعدادُ (يلصقه المالكُ في settings.json): handover_notes/ready_mark_hook_settings_snippet.md
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ledger  # noqa: E402
import ready_mark  # noqa: E402

TOOLS = {"SendMessage", "mcp__ccd_session_mgmt__send_message"}
PHRASE = "جاهزٌ للمعاينة"
CARD_RE = re.compile(r"W-\d{8}-\d{3}")
HEAD_RE = re.compile(r"الرأس\s+([0-9a-f]{7,40})\b")
BY_RE = re.compile(r"\((\d{4})\)")
LOG = HERE.parent / "logs" / "ready_mark_hook.log"


def log(line: str) -> None:
    if LOG.parent.is_dir():
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")


def parse(message: str) -> tuple[str, str, list[str]] | None:
    """(رقمُ الجلسة، الرأس، البطاقات) من رسالةٍ تبدأ بـ«جاهزٌ للمعاينة»؛ وإلّا None."""
    text = message.strip()
    if not text.startswith(PHRASE):
        return None
    by, head = BY_RE.search(text), HEAD_RE.search(text)
    cards = list(dict.fromkeys(CARD_RE.findall(text)))
    if not (by and head and cards):
        return None
    return by.group(1), head.group(1), cards


def handle(payload: dict, path=None, repo: str | None = None) -> list[str]:
    """يعيد أسطرَ ما جرى (للاختبار والسجلّ)؛ لا يرمي."""
    if payload.get("tool_name") not in TOOLS:
        return []
    message = str((payload.get("tool_input") or {}).get("message") or "")
    parsed = parse(message)
    if not parsed:
        return []
    by, head, cards = parsed
    out = []
    items = ledger.reduce_state(ledger.load_events(path))
    for card in cards:
        item = items.get(card)
        # لا يسجّل جلسةٌ بطاقةَ غيرها: الحاملةُ هي المرسِلة (أو لا حاملة)
        if item is not None and item.get("held_by") not in ("", None, by):
            out.append(f"تخطّي {card}: حاملتُها {item.get('held_by')} لا {by}")
            continue
        try:
            out.append(ready_mark.mark(card, head, by, repo, path=path))
        except ledger.LedgerError as e:
            out.append(f"تخطّي {card}: {e}")
    return out


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        for line in handle(payload):
            log(line)
    except Exception as e:  # noqa: BLE001 — صمتٌ آمنٌ مقصود: الخطّافُ لا يحجب شيئاً
        log(f"خطأ غير متوقَّع: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
