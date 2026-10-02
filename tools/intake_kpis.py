#!/usr/bin/env python3
"""مؤشّراتُ مخرجِ تبويب المدخلات (0201/0203/0204) من الدفتر وحده — قراءةٌ فقط (D-150م).

    python intake_kpis.py [--json]

كلُّ رقمٍ بمصدره: `ledger/events.jsonl`. «مركونٌ بقرار» وسمٌ صريحٌ (`ledger.py park`) لا تخمين، فيُعرض الراكدُ بقيمتين: الكلّيّ ومنه المركون.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from datetime import datetime

import ledger

STALE_H = 24
FALSE_ALARM = ledger.FALSE_ALARM_NOTE


def _h(a: str, b: str) -> float:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 3600


def compute(items: dict, events: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now(ledger.DOHA)
    cap = [i for i in items.values() if i["state"] == "captured"]
    stale = [i for i in cap if (now - datetime.fromisoformat(i["created"])).total_seconds() / 3600 > STALE_H]
    parked = [i for i in stale if i.get("parked")]
    routed_at: dict[str, str] = {}
    for e in events:
        if e["kind"] == "state" and e["data"].get("state") == "routed":
            routed_at.setdefault(e["id"], e["ts"])
    cap_to_route = [_h(items[k]["created"], ts) for k, ts in routed_at.items() if k in items]
    alerts = [i for i in items.values() if i.get("source") == "alert"]
    false_alarms = [i for i in alerts if any(FALSE_ALARM in str(n.get("text", n.get("note", ""))) for n in i["notes"])]
    dup = [i for i in items.values() if i["state"] == "closed" and any("مكرَّر" in str(n.get("text", n.get("note", ""))) for n in i["notes"])]
    by_source: dict[str, int] = {}
    for i in items.values():
        by_source[i.get("source", "—")] = by_source.get(i.get("source", "—"), 0) + 1
    return {
        "0204": {
            "captured_total": len(cap),
            "captured_older_24h": len(stale),
            "captured_older_24h_parked_by_decision": len(parked),
            "captured_older_24h_unparked": len(stale) - len(parked),
            "median_created_to_routed_h": round(st.median(cap_to_route), 2) if cap_to_route else None,
            "duplicates_closed": len(dup),
        },
        "0201": {"cards_from_intake": by_source.get("intake", 0)},
        "0203": {"alert_cards": len(alerts), "false_alarm_cards": len(false_alarms),
                 "false_alarm_ratio": round(len(false_alarms) / len(alerts), 2) if alerts else None},
        "by_source": by_source,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = compute(ledger.reduce_state(ledger.load_events()), ledger.load_events())
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    d4 = out["0204"]
    print(f"0204: ملتقَطةٌ {d4['captured_total']} — الأقدمُ من {STALE_H} س: {d4['captured_older_24h']} (منها مركونٌ بقرار {d4['captured_older_24h_parked_by_decision']}، راكدٌ فعلاً {d4['captured_older_24h_unparked']})")
    print(f"      وسيطُ التقاط←توجيه: {d4['median_created_to_routed_h']} س؛ تكرارٌ مكتشَفٌ مُغلَق: {d4['duplicates_closed']}")
    print(f"0201: بطاقاتٌ من مصدر intake: {out['0201']['cards_from_intake']}")
    print(f"0203: بطاقاتُ إنذارات {out['0203']['alert_cards']}، كاذبةٌ {out['0203']['false_alarm_cards']} (نسبة {out['0203']['false_alarm_ratio']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
