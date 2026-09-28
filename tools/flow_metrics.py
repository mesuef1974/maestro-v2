#!/usr/bin/env python3
"""مقاييسُ التدفّق من GitHub (قراءةٌ فقط) — يصحّح حسابَ قانون ليتل في الأساس القديم.

قانون ليتل: WIP = الإنتاجيّة × **متوسّط** زمنِ الدورة (لا الوسيط). الأساسُ القديم استعمل الوسيط (1.2 س) فأنقص التقدير
لأنّ التوزيعَ ذو ذيلٍ طويل (p90 ≈ 6.8 س). هنا يُحسب الاثنان ويُعرضان معاً، والمعتمَدُ المتوسّط.

    python flow_metrics.py [--days 3] [--json]
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
from datetime import datetime, timedelta, timezone

DOHA = timezone(timedelta(hours=3))


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def percentile(sorted_vals: list[float], p: float) -> float:
    """أقربُ رتبةٍ (nearest-rank) — نفسُ ما يُنتظر من p75/p90 على عيّنةٍ صغيرة."""
    if not sorted_vals:
        return 0.0
    rank = max(1, math.ceil(p * len(sorted_vals)))
    return sorted_vals[min(rank, len(sorted_vals)) - 1]


def cycle_hours(prs: list[dict]) -> list[float]:
    return sorted((parse(p["mergedAt"]) - parse(p["createdAt"])).total_seconds() / 3600 for p in prs)


def littles_wip(per_day: float, mean_cycle_h: float) -> float:
    """WIP المتوقَّع = معدّلُ الوصول (طلبٌ/ساعة) × متوسّطُ زمن الدورة (ساعة)."""
    return per_day / 24 * mean_cycle_h


def summarize(merged: list[dict], open_: list[dict], now: datetime, days: int) -> dict:
    since = now - timedelta(days=days)
    window = [p for p in merged if parse(p["mergedAt"]) >= since]
    cyc = cycle_hours(window)
    per_day = len(window) / days
    mean_h = statistics.fmean(cyc) if cyc else 0.0
    median_h = statistics.median(cyc) if cyc else 0.0
    ages = sorted((now - parse(p["createdAt"])).total_seconds() / 3600 for p in open_)
    return {
        "window_days": days,
        "merged": len(window),
        "throughput_per_day": round(per_day, 1),
        "cycle_h": {
            "mean": round(mean_h, 2), "median": round(median_h, 2),
            "p75": round(percentile(cyc, 0.75), 2), "p90": round(percentile(cyc, 0.90), 2),
            "max": round(cyc[-1], 2) if cyc else 0.0,
        },
        "wip_expected_littles_mean": round(littles_wip(per_day, mean_h), 1),
        "wip_expected_if_median_was_used": round(littles_wip(per_day, median_h), 1),
        "open_prs": len(open_),
        "open_age_h": {"median": round(statistics.median(ages), 1) if ages else 0.0, "oldest": round(ages[-1], 1) if ages else 0.0},
        "backlog_ratio_actual_vs_expected": round(len(open_) / max(littles_wip(per_day, mean_h), 0.01), 1),
    }


def gh_json(*args: str) -> list[dict]:
    proc = subprocess.run(["gh", *args], capture_output=True, encoding="utf-8", errors="replace", check=False, cwd="D:/shschool_mvp")
    if proc.returncode != 0:
        sys.exit(f"gh فشل: {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout or "[]")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    merged = gh_json("pr", "list", "--state", "merged", "--limit", "400", "--json", "number,createdAt,mergedAt")
    open_ = gh_json("pr", "list", "--state", "open", "--limit", "200", "--json", "number,createdAt,isDraft")
    open_ = [p for p in open_ if not p["isDraft"]]  # المسوّداتُ المحجوزةُ عمداً لا تُعدّ WIP
    out = summarize(merged, open_, now, args.days)
    out["generated_doha"] = now.astimezone(DOHA).isoformat(timespec="minutes")
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    c = out["cycle_h"]
    print(f"مقاييسُ التدفّق — الدوحة {out['generated_doha']} — نافذة {out['window_days']} أيّام")
    print(f"مدموج: {out['merged']} ({out['throughput_per_day']}/يوم)")
    print(f"زمنُ الدورة (س): متوسّط {c['mean']} | وسيط {c['median']} | p75 {c['p75']} | p90 {c['p90']} | أقصى {c['max']}")
    print(f"WIP المتوقَّع بليتل (متوسّط): {out['wip_expected_littles_mean']}   (بالوسيط كان: {out['wip_expected_if_median_was_used']})")
    print(f"المفتوح فعلاً (بلا مسوّدات): {out['open_prs']} — وسيطُ العمر {out['open_age_h']['median']} س، الأقدم {out['open_age_h']['oldest']} س")
    print(f"نسبةُ التراكم (فعليّ ÷ متوقَّع): {out['backlog_ratio_actual_vs_expected']}×")


if __name__ == "__main__":
    main()
