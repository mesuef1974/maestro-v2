"""اختباراتُ pr_watch — unittest بلا اعتمادٍ خارجيّ:  python -m unittest test_pr_watch"""

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pr_watch as pw  # noqa: E402

NOW = datetime(2026, 9, 29, 18, 0, tzinfo=timezone.utc)


def pr(n=1, checks="green", approval=True, merge="CLEAN", age_min=5, draft=False, exempt=False):
    created = (NOW - timedelta(minutes=age_min)).isoformat()
    return {"n": n, "title": f"عنوان {n}", "draft": draft, "merge": merge, "checks": checks,
            "approval": approval, "exempt": exempt, "created": created, "text": ""}


class Checks(unittest.TestCase):
    def test_check_state(self):
        ok = {"status": "COMPLETED", "conclusion": "SUCCESS"}
        self.assertEqual(pw.check_state([ok, {"status": "COMPLETED", "conclusion": "SKIPPED"}]), "green")
        self.assertEqual(pw.check_state([ok, {"status": "COMPLETED", "conclusion": "FAILURE"}]), "red")
        self.assertEqual(pw.check_state([ok, {"status": "IN_PROGRESS", "conclusion": ""}]), "pending")
        self.assertEqual(pw.check_state([{"state": "PENDING"}]), "pending")
        self.assertEqual(pw.check_state([{"state": "SUCCESS"}]), "green")
        self.assertEqual(pw.check_state([]), "green")

    def test_approval_line_detection_and_exemption(self):
        base = {"number": 5, "title": "x", "createdAt": NOW.isoformat(), "statusCheckRollup": []}
        self.assertTrue(pw.normalize({**base, "body": "اعتُمد من المالك على 8500 — 2026-09-29"})["approval"])
        self.assertTrue(pw.normalize({**base, "body": "اعتُمد من المالك مباشرةً بلا معاينة 8500"})["approval"])
        self.assertFalse(pw.normalize({**base, "body": "وصفٌ بلا اعتماد"})["approval"])
        self.assertTrue(pw.normalize({**base, "body": "مزامنةُ خارطةٍ — بلا سطر اعتماد بقرار D-67م"})["exempt"])


class Events(unittest.TestCase):
    def test_first_sight_reports_new_pr(self):
        out = pw.events(None, {1: pr()}, NOW, {})
        self.assertEqual(len(out), 1)
        self.assertIn("طلبٌ جديد #1", out[0])

    def test_pending_to_green_and_to_red(self):
        self.assertIn("أخضرُ الآن", pw.events({1: pr(checks="pending")}, {1: pr(checks="green")}, NOW, {})[0])
        self.assertIn("أحمر", pw.events({1: pr(checks="pending")}, {1: pr(checks="red")}, NOW, {})[0])

    def test_conflict_reported_once_on_change(self):
        out = pw.events({1: pr(merge="CLEAN")}, {1: pr(merge="DIRTY")}, NOW, {})
        self.assertTrue(any("تعارضٌ" in x for x in out))
        self.assertEqual(pw.events({1: pr(merge="DIRTY")}, {1: pr(merge="DIRTY")}, NOW, {}), [])

    def test_missing_approval_after_grace_and_throttled(self):
        alerted = {}
        cur = {1: pr(approval=False, age_min=20)}
        self.assertTrue(any("بلا سطر اعتماد" in x for x in pw.events(cur, cur, NOW, alerted)))
        self.assertEqual(pw.events(cur, cur, NOW + timedelta(minutes=5), alerted), [])  # مخنوق
        self.assertTrue(pw.events(cur, cur, NOW + timedelta(minutes=61), alerted))       # يتكرّر بعد ساعة

    def test_no_alert_for_recent_draft_or_exempt(self):
        self.assertEqual(pw.events({1: pr(approval=False, age_min=3)}, {1: pr(approval=False, age_min=3)}, NOW, {}), [])
        self.assertEqual(pw.events({1: pr(approval=False, age_min=99, draft=True)}, {1: pr(approval=False, age_min=99, draft=True)}, NOW, {}), [])
        self.assertEqual(pw.events({1: pr(approval=False, age_min=99, exempt=True, checks="pending")}, {1: pr(approval=False, age_min=99, exempt=True, checks="pending")}, NOW, {}), [])

    def test_green_approved_waiting_too_long(self):
        cur = {1: pr(age_min=45)}
        self.assertTrue(any("ينتظر الدمج" in x for x in pw.events(cur, cur, NOW, {})))
        self.assertEqual(pw.events({1: pr(age_min=10)}, {1: pr(age_min=10)}, NOW, {}), [])

    def test_closed_pr_is_reported(self):
        self.assertIn("لم يعد مفتوحاً #1", pw.events({1: pr()}, {}, NOW, {})[0])


class LedgerAndHeartbeat(unittest.TestCase):
    def test_pushed_without_pr(self):
        old = (NOW - timedelta(minutes=30)).isoformat()
        items = {"W-1": {"state": "pushed", "state_ts": old, "created": old},
                 "W-2": {"state": "pushed", "state_ts": old, "created": old},
                 "W-3": {"state": "approved", "state_ts": old, "created": old},
                 "W-4": {"state": "pushed", "state_ts": (NOW - timedelta(minutes=3)).isoformat(), "created": old}}
        self.assertEqual(pw.pushed_without_pr(items, ["W-2: طلبٌ"], NOW), ["W-1"])

    def test_heartbeat_age(self):
        path = Path(tempfile.mkdtemp()) / "hb.json"
        self.assertIsNone(pw.heartbeat_age(NOW, path))
        pw.beat(True, 3, path)
        self.assertLess(pw.heartbeat_age(datetime.now(timezone.utc), path), 1)


class WatchOnceIntegration(unittest.TestCase):
    def test_dead_watch_alerts_only_when_stale_and_in_hours(self):
        import watch_once as wo
        day = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)      # 12:00 الدوحة
        night = datetime(2026, 9, 29, 21, 30, tzinfo=timezone.utc)  # 00:30 الدوحة
        self.assertEqual(wo.pr_watch_alerts(day, 10), [])
        self.assertEqual(wo.pr_watch_alerts(day, None), [])
        self.assertEqual(wo.pr_watch_alerts(night, 90), [])
        out = wo.pr_watch_alerts(day, 55)
        self.assertEqual(out[0]["code"], "pr_watch_dead")


if __name__ == "__main__":
    unittest.main()
