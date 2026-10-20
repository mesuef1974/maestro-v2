"""اختباراتُ قياس جاهز←اعتماد (W-20261015-012) — بلا شبكةٍ:  python -m pytest test_ready_to_approval_metric.py"""

import unittest
from datetime import datetime, timedelta, timezone

import ready_to_approval_metric as m

DOHA = timezone(timedelta(hours=3))
T0 = datetime(2026, 10, 10, 8, 0, tzinfo=DOHA)


def ev(card, state, at):
    return {"ts": at.isoformat(timespec="seconds"), "id": card, "kind": "state", "data": {"state": state}}


class Cycles(unittest.TestCase):
    def test_hours_between_the_last_ready_and_the_approval(self):
        events = [ev("A", "ready_for_review", T0), ev("A", "approved", T0 + timedelta(hours=5))]
        (c,) = m.cycles(events)
        self.assertEqual((c["id"], c["hours"]), ("A", 5.0))

    def test_a_new_ready_restarts_the_clock(self):
        events = [
            ev("A", "ready_for_review", T0),
            ev("A", "ready_for_review", T0 + timedelta(hours=10)),
            ev("A", "approved", T0 + timedelta(hours=12)),
        ]
        self.assertEqual(m.cycles(events)[0]["hours"], 2.0)

    def test_an_approval_without_a_ready_or_a_repeated_one_is_not_a_cycle(self):
        events = [
            ev("B", "approved", T0),
            ev("A", "ready_for_review", T0),
            ev("A", "approved", T0 + timedelta(hours=1)),
            ev("A", "approved", T0 + timedelta(hours=2)),
        ]
        self.assertEqual([c["id"] for c in m.cycles(events)], ["A"])

    def test_notes_and_bad_timestamps_are_ignored(self):
        events = [
            {"ts": T0.isoformat(), "id": "A", "kind": "note", "data": {"text": "x"}},
            {"ts": "garbage", "id": "A", "kind": "state", "data": {"state": "ready_for_review"}},
            ev("A", "approved", T0),
        ]
        self.assertEqual(m.cycles(events), [])


class Report(unittest.TestCase):
    def events(self):
        out = []
        for i, hrs in enumerate([0.01, 0.02, 2, 4, 6, 8, 10, 20, 30, 40]):  # اثنان متزامنان
            out += [ev(f"C{i}", "ready_for_review", T0), ev(f"C{i}", "approved", T0 + timedelta(hours=hrs))]
        return out

    def test_simultaneous_records_are_split_from_the_actual_series(self):
        rep = m.report(self.events(), days=30, min_minutes=10, now=T0 + timedelta(days=3))
        self.assertEqual(rep["all"]["n"], 10)
        self.assertEqual(rep["actual"]["n"], 8)
        self.assertEqual(rep["excluded_as_simultaneous"], 2)
        self.assertEqual(rep["actual"]["median"], 9.0)
        self.assertEqual(rep["actual"]["max"], 40.0)
        self.assertAlmostEqual(rep["actual"]["p90"], 33.0, places=1)

    def test_the_window_drops_old_cycles(self):
        rep = m.report(self.events(), days=1, now=T0 + timedelta(days=30))
        self.assertEqual(rep["all"]["n"], 0)
        self.assertIsNone(rep["actual"]["median"])

    def test_zero_days_means_since_the_beginning(self):
        rep = m.report(self.events(), days=None, now=T0 + timedelta(days=400))
        self.assertEqual(rep["all"]["n"], 10)

    def test_render_has_both_series_in_arabic(self):
        text = m.render(m.report(self.events(), days=30, now=T0 + timedelta(days=3)))
        self.assertIn("الكلّ", text)
        self.assertIn("الفعليّ", text)
        self.assertIn("p90", text)
        self.assertIn("المستبعَد", text)

    def test_percentile_interpolates(self):
        self.assertEqual(m.percentile([1, 2, 3, 4, 5], 0.5), 3)
        self.assertEqual(m.percentile([10], 0.9), 10)


if __name__ == "__main__":
    unittest.main()
