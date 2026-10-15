"""اختباراتُ ready_approve_baseline (W-20261015-013) — بلا الدفتر الحقيقيّ:  python -m unittest tools.test_ready_approve_baseline"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ready_approve_baseline as rb  # noqa: E402

T0 = datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)


def st(cid, state, hours):
    return {"kind": "state", "id": cid, "ts": (T0 + timedelta(hours=hours)).isoformat(), "data": {"state": state}}


def created(cid):
    return {"kind": "created", "id": cid, "ts": T0.isoformat(), "data": {}}


EVENTS = [
    created("A"), st("A", "ready_for_review", 0), st("A", "approved", 1),     # 1 س
    created("B"), st("B", "ready_for_review", 0), st("B", "approved", 3),     # 3 س
    created("C"), st("C", "ready_for_review", 0), st("C", "approved", 30),    # 30 س
    created("D"), st("D", "approved", 5),                                      # بلا جاهز: خارج القياس ويُحسب في التغطية
    created("E"), st("E", "approved", 2), st("E", "ready_for_review", 4),     # اعتماد قبل الجاهز: مستبعد
    created("F"), st("F", "ready_for_review", 0), st("F", "ready_for_review", 10), st("F", "approved", 12),  # أوّل جاهز يُعتمد
]


class Baseline(unittest.TestCase):
    def test_pairs_use_first_ready_and_skip_approved_before_ready(self):
        got = {c: round(h) for c, _t, h in rb.pairs(rb.llt.first_times(EVENTS))}
        self.assertEqual(got, {"A": 1, "B": 3, "C": 30, "F": 12})

    def test_coverage_counts_approved_with_and_without_ready(self):
        c = rb.coverage(rb.llt.first_times(EVENTS))
        self.assertEqual((c["approved"], c["with_ready"]), (6, 5))  # D وحدها بلا جاهز؛ E لها جاهز لاحق

    def test_stats_median_and_p90_nearest_rank(self):
        s = rb.stats([1, 3, 12, 30])
        self.assertEqual((s["n"], s["median"], s["p90"], s["max"]), (4, 7.5, 30, 30.0))

    def test_empty_stats(self):
        self.assertEqual(rb.stats([]), {"n": 0})

    def test_windows_filter_by_approval_time(self):
        now = T0 + timedelta(hours=40)  # يوم قبل now = T0+16س: لا يبقى إلا اعتمادُ C (عند 30س)
        res = rb.report(EVENTS, [1], now=now)
        self.assertEqual(res["windows"]["1"]["n"], 1)
        self.assertEqual(res["all"]["n"], 4)

    def test_render_has_coverage_warning_first(self):
        text = rb.render(rb.report(EVENTS, [7], now=T0 + timedelta(days=1)))
        self.assertTrue(text.splitlines()[0].startswith("⚠ حدّ التغطية"))
        self.assertIn("التغطية:", text.splitlines()[1])


if __name__ == "__main__":
    unittest.main()
