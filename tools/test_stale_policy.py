"""اختبار سياسة الراكدة (عرضٌ فقط)."""

import datetime as dt
import unittest

import stale_policy as sp

NOW = dt.datetime(2026, 10, 19, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=3)))


def ts(hours_ago):
    return (NOW - dt.timedelta(hours=hours_ago)).isoformat()


def item(state, hours, holder="0701"):
    return {"state": state, "state_ts": ts(hours), "held_by": holder}


def none_commit(_b):
    return None


class StalePolicyTest(unittest.TestCase):
    def test_routed_72h_without_branch_returns_to_queue(self):
        out = sp.plan({"W-20261001-001": item("routed", 80)}, NOW, [], none_commit)
        self.assertEqual(out["return_to_queue"][0]["card"], "W-20261001-001")

    def test_recent_commit_on_branch_keeps_card(self):
        out = sp.plan(
            {"W-20261001-001": item("in_progress", 100)},
            NOW,
            ["claude/w20261001-001-x"],
            lambda b: NOW - dt.timedelta(hours=5),
        )
        self.assertEqual(out["return_to_queue"], [])

    def test_young_card_not_stale(self):
        self.assertEqual(sp.plan({"W-20261001-001": item("routed", 10)}, NOW, [], none_commit)["return_to_queue"], [])

    def test_unmeasured_branches_is_not_stale(self):
        out = sp.plan({"W-20261001-001": item("routed", 100)}, NOW, None, none_commit)
        self.assertEqual((out["return_to_queue"], out["unmeasured"]), ([], ["W-20261001-001"]))

    def test_approved_two_hours_nudges_once_per_two_hours(self):
        items = {"W-20261001-002": item("approved", 3)}
        self.assertEqual(sp.plan(items, NOW, [], none_commit)["nudge"][0]["holder"], "0701")
        self.assertEqual(sp.plan(items, NOW, [], none_commit, {"W-20261001-002": ts(1)})["nudge"], [])
        self.assertEqual(len(sp.plan(items, NOW, [], none_commit, {"W-20261001-002": ts(2.5)})["nudge"]), 1)

    def test_no_holder_no_action_and_other_states_ignored(self):
        items = {"W-20261001-003": item("routed", 200, holder=None), "W-20261001-004": item("pushed", 200)}
        out = sp.plan(items, NOW, [], none_commit)
        self.assertEqual((out["return_to_queue"], out["nudge"]), ([], []))


if __name__ == "__main__":
    unittest.main()
