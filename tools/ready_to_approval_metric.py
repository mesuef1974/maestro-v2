#!/usr/bin/env python3
"""قياسُ زمن «جاهزٌ للمعاينة ← اعتماد» من الدفتر (W-20261015-012، الخطوة 1: الأساس قبل أي تغيير).

كل دورةٍ = حدثُ حالةٍ `ready_for_review` يليه أوّلُ `approved` بعده للبطاقة نفسها. وإعادةُ «جاهز» (إيداعٌ جديد يُبطل الاعتماد)
تفتح دورةً جديدة: يُحسب الزمنُ من آخر `ready_for_review` قبل الاعتماد.

لماذا عمودان: الحالتان تُسجَّلان أحياناً معاً (اعتمادٌ مباشرٌ يُسجَّل بجوار الجاهز بثوانٍ) فيشوّه الوسيطَ نحو الصفر
(قياس 0501: وسيط 0.1 ساعة، متوسط 8.9). فتُعرض السلسلتان: **الكلّ** و**الفعليّ** (دورات زمنها ≥ `--min-minutes` الافتراضيّ 10 دقائق)،
مع عدد المستبعَدة. والهدفُ في المواصفة خفضُ p90 عن 25.3 ساعة (قياس 0102).

    python tools/ready_to_approval_metric.py [--days 30] [--min-minutes 10] [--json] [--ledger PATH]

للقراءة فقط: لا يكتب في الدفتر.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402

DOHA = timezone(timedelta(hours=3))


def _ts(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=DOHA)


def cycles(events: list[dict]) -> list[dict]:
    """[{id, ready, approved, hours}] لكل اعتمادٍ سبقه جاهزٌ؛ يُهمل اعتمادٌ بلا جاهز سابق."""
    last_ready: dict[str, datetime] = {}
    out = []
    for e in sorted(events, key=lambda r: r.get("ts", "")):
        if e.get("kind") != "state":
            continue
        state, at = (e.get("data") or {}).get("state"), _ts(e.get("ts", ""))
        if at is None:
            continue
        if state == "ready_for_review":
            last_ready[e["id"]] = at
        elif state == "approved" and e["id"] in last_ready:
            ready = last_ready.pop(e["id"])  # اعتمادٌ ثانٍ بلا جاهزٍ جديد لا يُحتسب دورةً
            out.append({"id": e["id"], "ready": ready, "approved": at, "hours": (at - ready).total_seconds() / 3600})
    return out


def percentile(values: list[float], q: float) -> float:
    """p-q بالاستيفاء الخطيّ (نمطُ numpy الافتراضيّ)."""
    if not values:
        return float("nan")
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def summarize(hours: list[float]) -> dict:
    if not hours:
        return {"n": 0, "median": None, "mean": None, "p90": None, "max": None}
    return {
        "n": len(hours),
        "median": round(statistics.median(hours), 2),
        "mean": round(statistics.fmean(hours), 2),
        "p90": round(percentile(hours, 0.9), 2),
        "max": round(max(hours), 2),
    }


def report(events: list[dict], days: int | None = 30, min_minutes: float = 10, now: datetime | None = None) -> dict:
    now = now or datetime.now(DOHA)
    cyc = cycles(events)
    if days:
        cyc = [c for c in cyc if c["approved"] >= now - timedelta(days=days)]
    actual = [c["hours"] for c in cyc if c["hours"] * 60 >= min_minutes]
    return {
        "as_of": now.isoformat(timespec="minutes"),
        "days": days,
        "min_minutes": min_minutes,
        "all": summarize([c["hours"] for c in cyc]),
        "actual": summarize(actual),
        "excluded_as_simultaneous": len(cyc) - len(actual),
    }


def render(rep: dict) -> str:
    def row(name: str, s: dict) -> str:
        if not s["n"]:
            return f"{name}: لا دوراتٍ"
        return f"{name}: ن={s['n']} · وسيط {s['median']} س · متوسط {s['mean']} س · p90 {s['p90']} س · أقصى {s['max']} س"

    span = f"آخر {rep['days']} يوماً" if rep["days"] else "منذ البداية"
    return "\n".join(
        [
            f"زمن جاهز←اعتماد ({span}، حتى {rep['as_of']})",
            row("الكلّ   ", rep["all"]),
            row(f"الفعليّ (≥{rep['min_minutes']:g} د)", rep["actual"]),
            f"المستبعَد لتسجيلٍ متزامن: {rep['excluded_as_simultaneous']}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=30, help="0 = منذ البداية")
    ap.add_argument("--min-minutes", type=float, default=10)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--ledger")
    args = ap.parse_args(argv)
    rep = report(ledger.load_events(args.ledger), args.days or None, args.min_minutes)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else render(rep))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
