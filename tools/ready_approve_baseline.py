#!/usr/bin/env python3
"""أساسُ زمن «جاهزٌ للمعاينة ← الاعتماد» (W-20261015-013) — قراءةٌ فقط من الدفتر، ولا يمسّ الفلو.

    python ready_approve_baseline.py [--days 3 7 14] [--json]

الحساب: أوّلُ وقتٍ بلغت فيه البطاقةُ approved ناقصَ أوّلِ وقتٍ بلغت فيه ready_for_review (ساعات)، بأدوات ledger_lead_time.first_times؛
وتُستبعد البطاقةُ التي اعتمادُها قبل جاهزيّتها. الوسيطُ وp75 وp90 بأقرب رتبة كما في flow_metrics.percentile.
النافذةُ بتاريخ الاعتماد. يُعاد التشغيلُ بالأمر نفسه ويُقارَن نافذةً بنافذة (بعد المعاينة الدفعيّة: 2026-10-22).

⚠ حدّ التغطية: ثلثُ البطاقات المعتمَدة فقط لها حالةُ ready_for_review في الدفتر (٩٨ من نحو ٢٩٦ يوم 2026-10-15)؛ فالأساسُ لا يُعمَّم،
والتغطيةُ تُطبع في رأس كلّ مخرَج. والمقاسُ يأخذ أوّلَ «جاهز» وأوّلَ اعتماد فيُظهر انتظاراً كلّيّاً أطولَ ممّا يراه المالكُ لآخر رأس.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone

import ledger
import ledger_lead_time as llt
from flow_metrics import percentile

COVERAGE_WARNING = "حدّ التغطية: القياسُ على البطاقات التي لها حالةُ ready_for_review فقط — لا يمثّل كلَّ البطاقات المعتمَدة ولا يُعمَّم."


def pairs(times: dict[str, dict[str, datetime]]) -> list[tuple[str, datetime, float]]:
    """(بطاقة، وقتُ الاعتماد، ساعاتُ الانتظار) لكلّ بطاقةٍ جاهزٌ ثمّ اعتماد؛ المعتمَدةُ قبل جاهزيّتها خارجة."""
    out = []
    for cid, s in times.items():
        if "ready_for_review" in s and "approved" in s and s["approved"] >= s["ready_for_review"]:
            out.append((cid, s["approved"], (s["approved"] - s["ready_for_review"]).total_seconds() / 3600))
    return out


def coverage(times: dict[str, dict[str, datetime]]) -> dict:
    approved = [c for c, s in times.items() if "approved" in s]
    with_ready = [c for c in approved if "ready_for_review" in times[c]]
    return {"approved": len(approved), "with_ready": len(with_ready), "ratio": round(len(with_ready) / len(approved), 2) if approved else 0.0}


def stats(hours: list[float]) -> dict:
    if not hours:
        return {"n": 0}
    v = sorted(hours)
    return {
        "n": len(v), "median": round(statistics.median(v), 2), "p75": round(percentile(v, 0.75), 2),
        "p90": round(percentile(v, 0.9), 2), "mean": round(statistics.mean(v), 2), "max": round(v[-1], 1),
    }


def report(events: list[dict], days: list[int], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    times = llt.first_times(events)
    rows = pairs(times)
    res = {"coverage": coverage(times), "warning": COVERAGE_WARNING, "all": stats([h for _c, _t, h in rows]), "windows": {}}
    for d in days:
        cut = now - timedelta(days=d)
        res["windows"][str(d)] = stats([h for _c, t, h in rows if t >= cut])
    return res


def render(res: dict) -> str:
    c = res["coverage"]
    lines = [
        f"⚠ {res['warning']}",
        f"التغطية: {c['with_ready']} من {c['approved']} معتمَدة ({c['ratio']:.0%}).",
        "النافذة (بتاريخ الاعتماد) | العدد | وسيط س | p75 س | p90 س | متوسط س",
    ]
    for name, s in (("كلّ السجلّ", res["all"]), *((f"آخر {d} أيام", v) for d, v in res["windows"].items())):
        lines.append(f"{name} | {s['n']} | " + " | ".join(str(s.get(k, "—")) for k in ("median", "p75", "p90", "mean")) if s["n"] else f"{name} | 0")
    return "\n".join(lines)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, nargs="*", default=[3, 7, 14])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = report(ledger.load_events(), a.days)
    print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else render(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
