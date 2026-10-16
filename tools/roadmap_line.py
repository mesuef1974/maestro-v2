#!/usr/bin/env python3
"""مقترحُ سطر الخارطة عند الدمج (W-20261016-027) — نصٌّ يقرؤه جلسةُ «خارطة التجويد» وحدَها؛ لا هجرةَ ولا كتابةَ في roadmap/.

    python roadmap_line.py                       # عرض المقترحات
    python roadmap_line.py --write               # يكتب handover_notes/roadmap_proposals.md (يُلحِق ما لم يُقترح بعد)

يقرأ الدفتر وgh: لكلّ بطاقةٍ رأسُها مدموجٌ في طلب يولَّد سطرٌ مقترح (رمز البند، رقم الطلب، الحالة والتقدّم المقترحان، ما قيس وما بقي).
لا سطرَ لطلبٍ غير مدموج، ولا إغلاقَ لبندٍ بلا رقم طلب. غياب الدفتر أو gh = «غير مقيس» لا نجاحٌ صامت.
ترتيبُ إيجاد البند (CLAUDE.md): ملاحظةُ تقدّمٍ على قائم ← ابنٌ تحت مظلة ← عائلةٌ جديدة ← N-… جديد.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import ledger
import publish_sync as ps

OUT = Path(__file__).resolve().parent.parent / "handover_notes" / "roadmap_proposals.md"
ITEM_RE = re.compile(r"\b(N-\d+[A-Za-z0-9-]*)\b")
ONE_HOUR = 3600


def find_item(data: dict) -> tuple[str, str]:
    """(رمز البند، طريقة إيجاده) — قائمٌ مذكورٌ في البطاقة، وإلا مقترحُ بندٍ جديد."""
    for key in ("roadmap_item", "roadmap"):
        if data.get(key):
            return str(data[key]), "ملاحظة تقدّم على بندٍ قائم"
    text = " ".join(str(data.get(k) or "") for k in ("problem", "accept", "source_of_truth"))
    m = ITEM_RE.search(text)
    if m:
        return m.group(1), "ملاحظة تقدّم على بندٍ قائم"
    return "N-جديد", "بندٌ جديد — تحدّد جلسةُ الخارطة العائلةَ أو المظلّة"


def build_line(cid: str, data: dict, pr: dict, now: datetime | None = None) -> dict | None:
    """سطرٌ مقترحٌ لبطاقةٍ رأسُها مدموج؛ None إن لم يُدمج طلبُها (لا بند قبل اندماجه)."""
    if not pr or not pr.get("number") or not pr.get("merge"):
        return None
    item, how = find_item(data)
    now = now or datetime.now(UTC)
    delay = None
    if pr.get("at"):
        delay = (now - datetime.fromisoformat(pr["at"].replace("Z", "+00:00"))).total_seconds()
    return {
        "card": cid,
        "item": item,
        "how": how,
        "pr": pr["number"],
        "merge": pr["merge"][:9],
        "status": "منجز بالدمج" if data.get("state") in ("merged", "published") else "مدموج",
        "progress": "حسب سبب الدمج؛ تقترح جلسةُ الخارطة النسبة",
        "measured": str(data.get("accept") or "غير مقيس")[:160],
        "remaining": "التحقق على الإنتاج بعد النشر" if data.get("state") != "published" else "لا شيء",
        "late": delay is not None and delay > ONE_HOUR,
    }


def collect(states: dict[str, dict], prs: dict[str, dict], seen: set[str], now=None) -> list[dict]:
    lines = []
    for cid, st in sorted(states.items()):
        if cid in seen or st.get("state") not in {"merged", "published"}:
            continue
        line = build_line(cid, st, prs.get(ps.card_head(st), {}), now)
        if line:
            lines.append(line)
    return lines


def render(line: dict) -> str:
    late = " ⚠ تأخّر المقترح أكثر من ساعة عن الدمج" if line["late"] else ""
    return (
        f"- بطاقة {line['card']} ← البند {line['item']} ({line['how']}): الطلب #{line['pr']} ({line['merge']})، "
        f"الحالة: {line['status']}، التقدّم المقترح: {line['progress']}. قيس: {line['measured']}. بقي: {line['remaining']}.{late}"
    )


def seen_cards(path: Path = OUT) -> set[str]:
    if not path.exists():
        return set()
    return set(re.findall(r"بطاقة (W-\d{8}-\d+)", path.read_text(encoding="utf-8")))


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    try:
        states = ledger.reduce_state(ledger.load_events())
        prs = ps.merged_prs(a.limit)
    except Exception as exc:  # الدفتر أو gh غائب
        print(f"غير مقيس: {exc} — لا مقترحات", file=sys.stderr)
        return 2
    lines = collect(states, prs, seen_cards())
    for ln in lines:
        print(render(ln))
    print(f"{len(lines)} مقترح جديد" + ("" if a.write else " (عرض فقط — أضف --write)"))
    if a.write and lines:
        OUT.parent.mkdir(exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        with OUT.open("a", encoding="utf-8") as f:
            f.write(f"\n## {stamp}\n" + "\n".join(render(ln) for ln in lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
