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


def node(num, state, pos=1):
    return {"position": pos, "state": state, "pullRequest": {"number": num}}


class MergeQueue(unittest.TestCase):
    def test_entry_joining_is_announced_with_position(self):
        out = pw.queue_events(None, [node(7, "QUEUED", 2)])
        self.assertEqual(out, ["طابور الدمج: #7 دخل في الموقع 2 (الحالة QUEUED)"])

    def test_state_change_and_exit_are_announced(self):
        prev = {7: "QUEUED", 8: "QUEUED"}
        out = pw.queue_events(prev, [node(7, "MERGEABLE", 1)])
        self.assertIn("طابور الدمج: #7 تغيّرت حالتُه من QUEUED إلى MERGEABLE", out)
        self.assertIn("طابور الدمج: #8 غادر الطابور (دُمج أو أُخرج)", out)

    def test_unchanged_queue_is_silent(self):
        self.assertEqual(pw.queue_events({7: "QUEUED"}, [node(7, "QUEUED")]), [])


class MainRed(unittest.TestCase):
    HEAD = "abcdef1234567890"

    def run_(self, name, conclusion, sha=HEAD, status="completed", rid=1):
        return {"databaseId": rid, "name": name, "conclusion": conclusion, "headSha": sha, "status": status}

    def test_failure_on_main_head_is_red(self):
        out = pw.main_red_events([self.run_("quality-gate", "failure")], self.HEAD)
        self.assertEqual(len(out), 1)
        self.assertIn("quality-gate", out[0])

    def test_latest_run_wins_over_older_failure(self):
        runs = [self.run_("quality-gate", "success", rid=2), self.run_("quality-gate", "failure", rid=1)]
        self.assertEqual(pw.main_red_events(runs, self.HEAD), [])

    def test_other_head_and_running_runs_are_ignored(self):
        runs = [self.run_("quality-gate", "failure", sha="0000000000"),
                self.run_("security", "failure", status="in_progress")]
        self.assertEqual(pw.main_red_events(runs, self.HEAD), [])

    def test_cancelled_is_not_red(self):
        self.assertEqual(pw.main_red_events([self.run_("quality-gate", "cancelled")], self.HEAD), [])


class ProdLag(unittest.TestCase):
    def test_health_error_is_announced(self):
        out = pw.prod_lag_events(None, "تعذّر قراءة /health/", None, {}, NOW)
        self.assertEqual(out, ["نشرُ الإنتاج: تعذّر قراءة /health/"])

    def test_lag_under_threshold_is_silent_then_alerts(self):
        state = {}
        self.assertEqual(pw.prod_lag_events("25cef9a1", None, "ahead", state, NOW), [])
        later = NOW + timedelta(minutes=pw.PROD_LAG_MIN)
        out = pw.prod_lag_events("25cef9a1", None, "ahead", state, later)
        self.assertEqual(len(out), 1)
        self.assertIn("متأخّرٌ عن main", out[0])

    def test_catching_up_clears_the_clock(self):
        state = {"lag_since": NOW.isoformat(timespec="seconds")}
        pw.prod_lag_events("25cef9a1", None, "identical", state, NOW)
        self.assertNotIn("lag_since", state)

    def test_diverged_always_alerts(self):
        out = pw.prod_lag_events("25cef9a1", None, "diverged", {}, NOW)
        self.assertTrue(any("diverged" in line for line in out))


class HeartbeatHonesty(unittest.TestCase):
    def test_failed_run_is_not_masked_by_fresh_timestamp(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "hb.json"
            pw.beat(False, 0, path)
            self.assertFalse(pw.heartbeat_ok(path))
            pw.beat(True, 3, path)
            self.assertTrue(pw.heartbeat_ok(path))

    def test_missing_heartbeat_is_not_ok(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(pw.heartbeat_ok(Path(d) / "none.json"))


class GhRetry(unittest.TestCase):
    def test_transient_failure_is_retried_until_success(self):
        from unittest import mock

        bad = mock.Mock(returncode=1, stdout="", stderr="HTTP 504")
        good = mock.Mock(returncode=0, stdout="[]", stderr="")
        sleeps = []
        with mock.patch.object(pw.subprocess, "run", side_effect=[bad, bad, good]) as run:
            p = pw._run_gh(["pr", "list"], sleep=sleeps.append)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(sleeps, list(pw.GH_RETRY_DELAYS))

    def test_persistent_failure_is_reported_after_all_attempts(self):
        from unittest import mock

        bad = mock.Mock(returncode=1, stdout="", stderr="x")
        with mock.patch.object(pw.subprocess, "run", return_value=bad) as run:
            p = pw._run_gh(["pr", "list"], sleep=lambda s: None)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(run.call_count, len(pw.GH_RETRY_DELAYS) + 1)


class StatePersistence(unittest.TestCase):
    def test_round_trip_restores_types_and_throttle_clock(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            prev = {7: {"n": 7, "merge": "CLEAN"}}
            ops = {"queue": {7: "QUEUED"}, "lag_since": NOW.isoformat(timespec="seconds")}
            alerted = {(7, "approval"): NOW}
            ops_alerted = {("prod", "نشرُ الإنتاج: تعذّر"): NOW}
            pw.save_state(prev, ops, alerted, ops_alerted, path)
            p2, o2, a2, oa2 = pw.load_state(path)
        self.assertEqual(p2, prev)
        self.assertEqual(o2["queue"], {7: "QUEUED"})
        self.assertEqual(a2, alerted)
        self.assertEqual(oa2, ops_alerted)

    def test_missing_state_starts_fresh(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(pw.load_state(Path(d) / "none.json"), (None, {}, {}, {}))

    def test_corrupt_state_starts_fresh_without_crashing(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(pw.load_state(path), (None, {}, {}, {}))

if __name__ == "__main__":
    unittest.main()
