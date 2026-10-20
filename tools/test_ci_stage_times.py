"""اختباراتُ ci_stage_times (W-20261020-021) — بلا شبكة:  python -m pytest test_ci_stage_times.py"""

import unittest
from pathlib import Path

import ci_stage_times as cs


def run(i, branch, status="completed", conclusion="success", created="2026-10-20T10:00:00Z"):
    return {"databaseId": i, "headBranch": branch, "status": status, "conclusion": conclusion, "createdAt": created}


def job(name, start, end, steps=()):
    return {"name": name, "startedAt": start, "completedAt": end,
            "steps": [{"name": n, "startedAt": a, "completedAt": b} for n, a, b in steps]}


class Pick(unittest.TestCase):
    def test_latest_completed_run_per_branch_newest_first(self):
        runs = [run(1, "a", created="2026-10-20T09:00:00Z"), run(2, "a", created="2026-10-20T11:00:00Z"), run(3, "b", created="2026-10-20T10:00:00Z")]
        self.assertEqual([r["databaseId"] for r in cs.pick_runs(runs, 10)], [2, 3])

    def test_unfinished_and_cancelled_are_skipped_and_limit_applies(self):
        runs = [run(1, "a", status="in_progress"), run(2, "b", conclusion="cancelled"), run(3, "c"), run(4, "d")]
        self.assertEqual([r["databaseId"] for r in cs.pick_runs(runs, 1)], [3])


class Collect(unittest.TestCase):
    def test_seconds_and_unfinished_markers(self):
        self.assertEqual(cs.secs("2026-10-20T10:00:00Z", "2026-10-20T10:01:30Z"), 90)
        self.assertIsNone(cs.secs("2026-10-20T10:00:00Z", "0001-01-01T00:00:00Z"))
        self.assertIsNone(cs.secs(None, "2026-10-20T10:00:00Z"))

    def test_per_job_and_step_times_and_queue(self):
        jobs = [job("tests", "2026-10-20T10:01:00Z", "2026-10-20T10:05:00Z",
                    [("pip install", "2026-10-20T10:01:00Z", "2026-10-20T10:02:00Z"), ("pytest", "2026-10-20T10:02:00Z", "2026-10-20T10:05:00Z")])]
        data = cs.collect([run(1, "a")], lambda _id: jobs)
        self.assertEqual(data["jobs"]["tests"], [240])
        self.assertEqual(data["steps"][("tests", "pytest")], [180])
        self.assertEqual(data["queue"], [60])
        self.assertEqual(data["walls"][0][2], 240)

    def test_in_progress_job_is_ignored(self):
        jobs = [job("x", "2026-10-20T10:01:00Z", "0001-01-01T00:00:00Z")]
        self.assertEqual(cs.collect([run(1, "a")], lambda _id: jobs)["jobs"], {})


class Report(unittest.TestCase):
    def test_report_ranks_steps_and_states_sample_size(self):
        jobs = [job("tests", "2026-10-20T10:01:00Z", "2026-10-20T10:05:00Z",
                    [("fast", "2026-10-20T10:01:00Z", "2026-10-20T10:01:10Z"), ("slow", "2026-10-20T10:01:10Z", "2026-10-20T10:05:00Z")])]
        runs = [run(1, "a")]
        text = cs.report(cs.collect(runs, lambda _id: jobs), runs, "o/r", "w.yml")
        self.assertIn("عيّنة: 1 طلباً", text)
        self.assertLess(text.index("| tests | slow"), text.index("| tests | fast"))
        self.assertIn("ما لم يُقَس", text)

    def test_tool_is_read_only(self):
        src = Path(cs.__file__).read_text(encoding="utf-8")
        for bad in ("workflow run", "run rerun", "run cancel", "pr merge", "--force"):
            self.assertNotIn(bad, src)


if __name__ == "__main__":
    unittest.main()
