"""خلاصةُ فشل pytest للنموذج: الأسبابُ الفريدة (سطور `E`) قبل ذيل السجلّ.

ذيلُ 4000 حرفٍ وحدَه يكفي لفشلٍ أو اثنين؛ أمّا عشراتُ الأخطاء فيملأ ذيلَها سطورُ الأسماء (`ERROR tests/...`) بلا سبب،
فيصلح النموذجُ على العمى (W-20261109-006، 2026-11-10: 5 فشل و33 خطأً ولم يصل النموذجَ سببٌ واحد).
"""

from __future__ import annotations

NL = chr(10)


def failure_digest(text: str, limit: int = 3600, max_causes: int = 25, cause_chars: int = 240) -> str:
    causes = list(dict.fromkeys(ln.strip()[:cause_chars] for ln in text.splitlines() if ln.startswith("E  ")))[:max_causes]
    if not causes:
        return text[-limit:]
    head = "أسبابٌ فريدة من السجلّ (سطور E):" + NL + NL.join(causes) + NL + "…" + NL
    room = max(limit - len(head), 1200)  # الذيلُ يبقى: فيه أسماءُ الاختبارات والحصيلة
    return head + text[-room:]
