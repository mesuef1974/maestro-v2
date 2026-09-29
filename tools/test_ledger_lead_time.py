"""اختباراتُ ledger_lead_time — unittest بلا اعتمادٍ خارجيّ:  python -m unittest test_ledger_lead_time"""

import unittest

import ledger_lead_time as llt


def ev(ts, item, kind, state=None):
    return {"ts": ts, "id": item, "kind": kind, "data": {"state": state} if state else {}}


CARD = [
    ev("2026-09-29T08:00:00+03:00", "W-1", "created"),
    ev("2026-09-29T09:00:00+03:00", "W-1", "state", "routed"),
    ev("2026-09-29T12:00:00+03:00", "W-1", "state", "ready_for_review"),
    ev("2026-09-29T12:30:00+03:00", "W-1", "state", "approved"),
    ev("2026-09-29T20:00:00+03:00", "W-1", "state", "published"),
]


class LeadTime(unittest.TestCase):
    def test_stage_hours_of_one_card(self):
        h = llt.stage_hours(CARD)
        self.assertEqual(h["capture_to_route"], [1.0])
        self.assertEqual(h["route_to_publish"], [11.0])
        self.assertEqual(h["review_to_approve"], [0.5])
        self.assertEqual(h["capture_to_publish"], [12.0])

    def test_card_without_end_state_is_excluded(self):
        events = CARD[:2] + [ev("2026-09-29T08:00:00+03:00", "W-2", "created")]
        h = llt.stage_hours(events)
        self.assertEqual(h["capture_to_route"], [1.0])
        self.assertEqual(h["capture_to_publish"], [])

    def test_summary_median_and_unmeasured(self):
        s = llt.summarize({"a": [1.0, 3.0, 5.0], "b": []})
        self.assertEqual(s["a"], {"median": 3.0, "mean": 3.0, "n": 3})
        self.assertIsNone(s["b"])


if __name__ == "__main__":
    unittest.main()
