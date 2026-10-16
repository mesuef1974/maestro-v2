#!/usr/bin/env python3
"""تسجيلُ أمرِ المالك المباشر في محادثتك بنصّه الحرفيّ — فيتحقّق منه 0501/0601 بالأداة ولا يُسأل المالكُ.

    python record_owner_confirmation.py --session 0405 --target W-20261002-013 --quote "ادفع" [--question "…"]

يُلحَق سطرٌ بـ`owner_confirmations.md` (التاريخ، الجلسة، السؤال، النصُّ الحرفيّ، الهدف). يقرؤه `approval_check.py`. الإفادةُ **إفادةُ جلسة**
تُدقَّق بالعيّنة: 0102 يطابق أسطراً منها مع سجلّات الجلسات (واجبُ التدقيق الدوريّ)، فالنصُّ الحرفيُّ لا الوصفُ، ويُرفض الفارغُ والقصيرُ جدّاً.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "owner_confirmations.md"
DOHA = timezone(timedelta(hours=3))
SESSION = re.compile(r"^0[1-8]\d\d$|^0[1-8]\d\d ·")
#: مصدرُ الإفادة: «مباشر» (سمعتُ المالكَ في محادثتي) أو «نقلاً عن جلسة <رقم>» (W-20261016-030)
SOURCE = re.compile(r"^(?:مباشر|نقلاً عن (?:جلسة )?(0[1-8]\d\d))$")


def normalize_source(source: str) -> str | None:
    """الصيغةُ المخزَّنة («مباشر» أو «نقلاً عن 0101») أو None إن لم تصحّ."""
    m = SOURCE.match(source.strip())
    if not m:
        return None
    return f"نقلاً عن {m.group(1)}" if m.group(1) else "مباشر"


def row(session: str, target: str, quote: str, question: str, now: datetime | None = None, head: str = "", source: str = "") -> str:
    now = now or datetime.now(DOHA)
    esc = lambda t: t.replace("|", "/").replace("\n", " ").strip()  # noqa: E731
    tag = f" مصدره: {source}" if source else ""
    return f"| {now:%Y-%m-%d %H:%M} | {esc(session)} (إفادةُ جلسة){tag} | {esc(question) or 'أمرٌ مباشر'} | «{esc(quote)}» | {esc(target)}{' @' + head[:8] if head else ''} |\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--session", required=True, help="رقمُ جلستك (مثل 0405)")
    ap.add_argument("--target", required=True, help="رمزُ البطاقة أو رقمُ الطلب (مثل W-20261002-013 أو #772)")
    ap.add_argument("--quote", required=True, help="نصُّ المالك الحرفيّ كما كتبه")
    ap.add_argument("--question", default="")
    ap.add_argument("--head", default="", help="رأسُ الإيداع الذي عاينه المالك (sha8) — يربط الاعتمادَ به (v2.23)")
    ap.add_argument("--source", required=True, help="«مباشر» أو «نقلاً عن جلسة <رقم>» — مصدرُ الإفادة")
    a = ap.parse_args()
    source = normalize_source(a.source)
    if source is None:
        sys.exit("--source إلزاميّ: «مباشر» (سمعتُ المالكَ في محادثتي) أو «نقلاً عن جلسة <رقم>»")
    if len(a.quote.strip()) < 2:
        sys.exit("النصُّ الحرفيُّ للمالك مطلوب (لا وصفٌ ولا فراغ)")
    if not re.fullmatch(r"[0-9a-f]{7,40}", a.head or ""):
        sys.exit("--head إلزاميّ: رأسُ الإيداع المعاين (git rev-parse --short=8 <الفرع>)")
    if not SESSION.match(a.session):
        sys.exit("--session رقمُ جلسةٍ من أربع خانات (مثل 0405)")
    with FILE.open("a", encoding="utf-8") as f:
        f.write(row(a.session, a.target, a.quote, a.question, head=a.head, source=source))
    print("سُجّل في owner_confirmations.md — يتحقّق منه approval_check.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
