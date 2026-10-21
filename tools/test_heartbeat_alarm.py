"""إنذارُ توقّف pr_watch: عتبةٌ، مرّةٌ لكلّ توقّف، إعادةُ تسليحٍ، الليلُ، والفشلُ الحديث — بساعةٍ وهميّة."""

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

import heartbeat_alarm as ha

DAY = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)  # 12:00 الدوحة
NIGHT = datetime(2026, 10, 20, 21, 30, tzinfo=UTC)  # 00:30 الدوحة
DIR = {"0601": {"id": "local_0601"}, "0101": {"id": "local_0101"}}


class Evaluate(unittest.TestCase):
    def test_live_heartbeat_gives_no_alarm(self):
        self.assertIsNone(ha.evaluate(3, True, {}, DAY, 10))

    def test_no_heartbeat_ever_gives_no_alarm(self):
        self.assertIsNone(ha.evaluate(None, False, {}, DAY, 10))

    def test_stale_heartbeat_alarms_once_per_outage(self):
        state = {}
        self.assertIn("متوقّف", ha.evaluate(25, True, state, DAY, 10))
        self.assertIsNone(ha.evaluate(40, True, state, DAY, 10), "لا تكرار لتوقّفٍ واحد")

    def test_resume_rearms_then_a_new_outage_alarms_again(self):
        state = {}
        ha.evaluate(25, True, state, DAY, 10)
        self.assertIsNone(ha.evaluate(2, True, state, DAY, 10))
        self.assertFalse(state["alarmed"])
        self.assertIsNotNone(ha.evaluate(30, True, state, DAY, 10))

    def test_fresh_but_failed_cycle_alarms(self):
        self.assertIn("فشلت", ha.evaluate(2, False, {}, DAY, 10))

    def test_night_is_silent_and_not_consumed(self):
        state = {}
        self.assertIsNone(ha.evaluate(90, True, state, NIGHT, 10))
        self.assertFalse(state.get("alarmed"))
        self.assertIsNotNone(ha.evaluate(90, True, state, DAY, 10))

    def test_threshold_is_configurable(self):
        self.assertIsNone(ha.evaluate(25, True, {}, DAY, 30))
        self.assertIsNotNone(ha.evaluate(25, True, {}, DAY, 20))


class Cycle(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        self.state, self.hb = d / "state.json", d / "hb.json"

    def _beat(self, ts):
        self.hb.write_text(json.dumps({"ts": ts, "ok": True, "open": 2}), encoding="utf-8")

    def test_dead_monitor_notifies_on_duty_and_proxy_once(self):
        self._beat("2026-10-20T07:55:00+00:00")  # قبل 65 د
        out = ha.cycle(DAY, directory=DIR, state_path=self.state, heartbeat_path=self.hb)
        self.assertEqual([m[0] for m in out], ["0601", "0101"])
        self.assertEqual(out[0][1], "local_0601")
        again = ha.cycle(DAY, directory=DIR, state_path=self.state, heartbeat_path=self.hb)
        self.assertEqual(again, [], "لا تكرار")

    def test_live_monitor_is_silent(self):
        self._beat("2026-10-20T08:58:00+00:00")
        self.assertEqual(ha.cycle(DAY, directory=DIR, state_path=self.state, heartbeat_path=self.hb), [])

    def test_dry_run_does_not_save_state(self):
        self._beat("2026-10-20T07:55:00+00:00")
        ha.cycle(DAY, dry_run=True, directory=DIR, state_path=self.state, heartbeat_path=self.hb)
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
