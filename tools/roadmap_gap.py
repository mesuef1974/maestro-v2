#!/usr/bin/env python3
"""قياسُ ما سقط من طابور الخارطة (W-20261023-014) — قراءةٌ فقط.

    python roadmap_gap.py [--days 7] [--json]

بطاقاتُ الدفتر التي بلغت merged/published خلال النافذة ولا سطرَ لها في ledger/roadmap_queue.jsonl (بالبطاقة)؛ كلُّ واحدةٍ منها
سقطت من الطابور قبل أتمتة المضخّة. المصدرُ الدفترُ والطابورُ وحدَهما (بلا gh فلا يُخمَّن رقمُ الطلب).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402
import roadmap_queue as rq  # noqa: E402

MERGED_STATES = ("merged", "published")


def merged_at(events: list[dict], card: str) -> datetime | None:
    """أوّلُ حدثٍ إلى merged أو published للبطاقة."""
    for e in events:
        if e.get("id") == card and e.get("kind") == "state" and (e.get("data") or {}).get("state") in MERGED_STATES:
            return rq._parse(e.get("ts"))
    return None


def gap(states: dict, events: list[dict], queue: list[dict], now: datetime | None = None, days: int = 7) -> dict:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    queued = {str(e.get("card")) for e in queue if e.get("card")}
    merged, missing = [], []
    for cid, st in sorted(states.items()):
        if st.get("state") not in MERGED_STATES:
            continue
        at = merged_at(events, cid)
        if at is None or at < cutoff:
            continue
        merged.append(cid)
        if cid not in queued:
            missing.append(cid)
    return {"days": days, "merged": len(merged), "missing": len(missing), "missing_cards": missing, "queue_total": len(queue)}


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    events = ledger.load_events()
    out = gap(ledger.reduce_state(events), events, rq.read(), days=a.days)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print(f"آخر {out['days']} أيام: {out['merged']} بطاقةً مدموجةً، منها {out['missing']} بلا سطرٍ في الطابور (الطابور كلُّه {out['queue_total']})")
        for cid in out["missing_cards"]:
            print("  " + cid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
