"""مطابقةُ موضوع المهمّة بعنوان الجلسة — قراءةٌ فقط؛ تمنع إسنادَ مهمّةٍ إلى جلسةٍ مشغولةٍ بموضوعٍ مختلف (الوسمُ وحدَه لا يكفي)."""

from __future__ import annotations

import re

_WORD = re.compile(r"[\w]+", re.UNICODE)
_CODE = re.compile(r"\(([^)]*)\)\s*$")


def task_of(session_name: str) -> str:
    """مهمّةُ الجلسة من عنوانها «04SS · وسم: مهمّة (رمز)» — بلا الرقم والوسم والرمز."""
    _, _, rest = session_name.partition(" · ")
    _, _, body = rest.partition(":")
    return _CODE.sub("", body or rest).strip()


def code_of(session_name: str) -> str | None:
    m = _CODE.search(session_name)
    return m.group(1).split("/")[0].strip() if m else None


def tokens(text: str) -> set[str]:
    """كلماتٌ دالّة: أطولُ من حرفين، بلا أداة التعريف ولا التشكيل."""
    text = re.sub(r"[\u064B-\u0652\u0640]", "", text)
    out = set()
    for w in _WORD.findall(text):
        w = w[2:] if w.startswith("ال") and len(w) > 4 else w
        if len(w) > 2:
            out.add(w)
    return out


def same_topic(session_name: str, task: str | None, code: str | None = None) -> bool:
    """هل المهمّةُ المطلوبة من عائلة ما تعمل عليه الجلسة؟ (الرمزُ نفسُه أو كلمةٌ دالّةٌ مشتركة). بلا مهمّةٍ مطلوبة ← نعم (سلوكٌ قديم)."""
    if not task and not code:
        return True
    if code and code_of(session_name) and code.split("/")[0] == code_of(session_name):
        return True
    return bool(tokens(task or "") & tokens(task_of(session_name)))


def is_busy(row: dict) -> bool:
    """مشغولةٌ: عندها عملٌ جارٍ (wip) أو طلبُ دمجٍ مفتوح أو غيرُ صالحةٍ للإسناد."""
    return bool(row.get("wip", 0) or row.get("open_prs", 0) or row.get("assignable") is False)


def excluded_by_topic(row: dict, task: str | None, code: str | None = None) -> bool:
    """تُستبعد الجلسةُ إن كانت مشغولةً بموضوعٍ مختلف؛ والخاملةُ تبقى مرشّحةً أياً كان عنوانُها القديم."""
    return is_busy(row) and not same_topic(row.get("session", ""), task, code)
