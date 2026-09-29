#!/usr/bin/env python3
"""أزمنةُ التدفّق من سجلّ البطاقات (قراءةٌ فقط): الالتقاط ثمّ التوجيه ثمّ الاعتماد ثمّ النشر.

لماذا: flow_metrics يقيس من دفع الطلب، والعملُ محلّيٌّ حتى اعتماد المالك؛ فلا يرى الانتظارَ الفعليّ
قبل الدفع (تقييم 0102 يوم 09-29، قرار D-67م). هذا يقيس من السجلّ نفسِه.

    python ledger_lead_time.py [--json]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime

import ledger

STAGES = (
    ("capture_to_route", "captured", "routed", "من الالتقاط إلى التوجيه"),
    ("route_to_publish", "routed", "published", "من التوجيه إلى النشر"),
    ("review_to_approve", "ready_for_review", "approved", "من «جاهزٌ للمعاينة» إلى الاعتماد"),
    ("capture_to_publish", "captured", "published", "من الالتقاط إلى النشر"),
)


def first_times(events: list[dict]) -> dict[str, dict[str, datetime]]:
    """أوّلُ وقتٍ بلغته كلُّ بطاقةٍ في كلّ حالة؛ إنشاؤها يُعدّ التقاطاً."""
    times: dict[str, dict[str, datetime]] = {}
    for e in events:
        ts = datetime.fromisoformat(e["ts"].replace("Z", "+00:00"))
        if e["kind"] == "created":
            times.setdefault(e["id"], {}).setdefault("captured", ts)
        elif e["kind"] == "state":
            times.setdefault(e["id"], {}).setdefault(e["data"]["state"], ts)
    return times


def skipped_cards(events: list[dict]) -> list[str]:
    """بطاقاتٌ قفزت بوّابةً من بوّابات الفلو (كنشرٍ بلا دمجٍ أو دفع): زمنُ نشرها مسجَّلٌ متأخّراً بالدفعة لا وقتَ حدوثه (D-73م)."""
    bad = []
    for cid, s in first_times(events).items():
        for target, prevs in ledger.GATES.items():
            if target in s and not any(p in s and s[p] <= s[target] for p in prevs):
                bad.append(cid)
                break
    return sorted(bad)


def stage_hours(events: list[dict]) -> dict[str, list[float]]:
    """أزمنةُ كلّ مرحلة؛ والبطاقاتُ القافزةُ تُستبعَد من المراحل المنتهيةِ بالنشر وحدَها (مرحلةُ الاعتماد سليمةٌ)."""
    times = first_times(events)
    skipped = set(skipped_cards(events))
    out: dict[str, list[float]] = {}
    for key, start, end, _label in STAGES:
        out[key] = [
            (s[end] - s[start]).total_seconds() / 3600
            for cid, s in times.items()
            if start in s and end in s and s[end] >= s[start] and not (end == "published" and cid in skipped)
        ]
    return out


def summarize(hours: dict[str, list[float]]) -> dict[str, dict | None]:
    return {
        key: (
            {"median": round(statistics.median(v), 1), "mean": round(statistics.mean(v), 1), "n": len(v)}
            if v
            else None
        )
        for key, v in hours.items()
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # طرفيّةُ ويندوز cp1256 تُسقط العربيّة والأسهم
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    events = ledger.load_events()
    summary = summarize(stage_hours(events))
    skipped = skipped_cards(events)
    if args.json:
        print(json.dumps({"stages": summary, "skipped_cards": skipped}, ensure_ascii=False, indent=2))
        return
    print(f"بطاقاتٌ قفزت مراحلَها (مستبعَدةٌ من مراحل النشر): {len(skipped)} — {'، '.join(skipped) or 'لا شيء'}")
    for key, _start, _end, label in STAGES:
        s = summary[key]
        print(f"{label}: " + (f"وسيط {s['median']} س | متوسّط {s['mean']} س | عدد {s['n']}" if s else "غيرُ مقيس (لا بطاقةَ بلغت الحالتين)"))


if __name__ == "__main__":
    main()
