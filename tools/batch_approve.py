#!/usr/bin/env python3
"""اعتمادُ المالك الجماعيّ بالرأس (W-20261015-012، قرارُ المالك 2026-10-20 «نعم» عبر 0101).

يعاين المالكُ جدولَ الدفعة (`batch_preview`) مرّةً واحدة ويقول «اعتمد»، فيُسجَّل سطرُ اعتمادٍ **لكلّ بطاقةٍ ولرأسها** في
`owner_confirmations.md` بنصّه الحرفيّ — ويبقى `approval_check` يتحقّق بالرأس كما كان. الاعتمادُ الجماعيّ ليس اعتماداً بالجملة:

* لا يُسجَّل إلا لبطاقةٍ **سمّاها المتكلّمُ صراحةً بـ`رمز@رأس`** ويطابق رأسُها رأسَ الجدول الحاليّ داخل «تدخل الدفعة»؛
  رأسٌ تغيّر بعد العرض أو بطاقةٌ مستبعَدة أو غير مسمّاة تُرفض بسببها ولا يُكتب شيءٌ لها.
* مصدرُ النصّ الحرفيّ كما في `record_owner_confirmation` («مباشر» أو «نقلاً عن جلسة <رقم>») فيُدقَّق بالعيّنة نفسِها.
* بلا `--write` عرضٌ فقط. لا يحرّك الدفترَ ولا يدفع؛ تسجيلُ `approved` يبقى لـ0501/0101.

    python batch_approve.py --session 0101 --source "نقلاً عن جلسة 0101" --quote "اعتمد" --cards W-1@abcd1234 W-2@ef567890 [--write]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import batch_preview  # noqa: E402
import ledger  # noqa: E402
import record_owner_confirmation as roc  # noqa: E402

PAIR = re.compile(r"^(W-\d{8}-\d{3})@([0-9a-f]{7,40})$")


def decide(rep: dict, pairs: list[str]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(مقبولة [(بطاقة، رأس8)]، مرفوضة [(مدخَل، سبب)]) — لا قبولَ إلا برمزٍ ورأسٍ مطابقَين لمُدرَجٍ في الدفعة."""
    inc = {r["id"]: r["head"] for r in rep["included"]}
    exc = {r["id"]: r["why"] for r in rep["excluded"]}
    ok, bad = [], []
    for raw in pairs:
        m = PAIR.match(raw)
        if not m:
            bad.append((raw, "الصيغة «رمز@رأس» (مثل W-20261015-012@24793ab)"))
            continue
        card, head = m.groups()
        if card in exc:
            bad.append((raw, "مستبعَدة من الدفعة: " + exc[card]))
        elif card not in inc:
            bad.append((raw, "ليست في الدفعة (ليست جاهزةً للمعاينة أو غير واجهيّة)"))
        elif not inc[card].startswith(head):
            bad.append((raw, f"الرأسُ تغيّر بعد العرض: الحاليّ {inc[card][:8]}"))
        else:
            ok.append((card, inc[card][:8]))
    return ok, bad


def lines(ok: list[tuple[str, str]], session: str, quote: str, source: str, now=None) -> list[str]:
    q = f"{quote} (اعتمادٌ جماعيّ بالرأس لـ{len(ok)} بطاقة)"
    return [roc.row(session, card, q, "اعتمادٌ جماعيّ بالرأس", now=now, head=head, source=source) for card, head in ok]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--session", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--quote", required=True)
    ap.add_argument("--cards", nargs="+", required=True, help="رمز@رأس لكلّ بطاقةٍ سمّاها المالك")
    ap.add_argument("--repo", default=batch_preview.DEFAULT_REPO)
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--max-age-h", type=int, default=48)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    source = roc.normalize_source(a.source)
    if source is None or len(a.quote.strip()) < 2 or not roc.SESSION.match(a.session):
        print("✗ --source «مباشر»/«نقلاً عن جلسة <رقم>» ونصٌّ حرفيّ و--session من أربع خانات", file=sys.stderr)
        return 2
    registry = json.loads(batch_preview.REGISTRY.read_text(encoding="utf-8")) if batch_preview.REGISTRY.is_file() else []
    rep = batch_preview.plan(ledger.reduce_state(ledger.load_events()), a.repo, a.base, a.max_age_h, registry=registry)
    ok, bad = decide(rep, a.cards)
    for raw, why in bad:
        print(f"✗ {raw} — {why}")
    out = lines(ok, a.session, a.quote, source)
    for (card, head), ln in zip(ok, out, strict=True):
        print(f"✔ {card} @{head}")
        if a.write:
            with roc.FILE.open("a", encoding="utf-8") as f:
                f.write(ln)
    print(("كُتب" if a.write else "عرضٌ فقط (أضف --write)") + f": {len(ok)} مقبولة، {len(bad)} مرفوضة")
    return 0 if ok and not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
