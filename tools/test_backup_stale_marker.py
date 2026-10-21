"""علامةُ BACKUP_FAILED.txt الأقدمُ من آخر نسخةٍ ناجحة ليست إنذاراً (W-20260929-008)."""

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import watch_once as wo


def git(repo, *args, date=None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    if date:
        env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = date
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)  # noqa: S603, S607


class Pure(unittest.TestCase):
    def test_no_marker_is_not_a_failure(self):
        self.assertFalse(wo.backup_failure_is_current(None, 1000))

    def test_marker_older_than_the_last_success_is_ignored(self):
        self.assertFalse(wo.backup_failure_is_current(900, 1000))

    def test_marker_newer_than_the_last_success_still_alarms(self):
        self.assertTrue(wo.backup_failure_is_current(1100, 1000))

    def test_marker_with_no_known_success_still_alarms(self):
        self.assertTrue(wo.backup_failure_is_current(500, None))


class Integration(unittest.TestCase):
    """الحالةُ الواقعيّة: فشلٌ 03:00 ثمّ نجاحٌ 06:09 والعلامةُ باقية."""

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        git(self.repo, "init", "-q", "-b", "claude-backup")
        (self.repo / "backups").mkdir()
        self.marker = self.repo / "backups" / "BACKUP_FAILED.txt"
        self.marker.write_text("failed", encoding="utf-8")
        (self.repo / "a.txt").write_text("x", encoding="utf-8")
        git(self.repo, "add", "a.txt")
        self.cfg = {"repo": str(self.repo), "branch": "claude-backup", "max_age_h": 36}

    def _commit_at(self, ts):
        git(self.repo, "commit", "-q", "-m", "backup", date=f"{int(ts)} +0000")

    def test_stale_marker_after_a_later_success_gives_no_alert(self):
        now = time.time()
        os.utime(self.marker, (now - 7200, now - 7200))  # فشلٌ قبل ساعتين
        self._commit_at(now - 3600)  # ونجاحٌ قبل ساعة
        self.assertEqual(wo.backup_alerts(self.cfg), [])

    def test_a_failure_newer_than_the_last_success_still_alerts_high(self):
        now = time.time()
        self._commit_at(now - 7200)  # نجاحٌ قبل ساعتين
        os.utime(self.marker, (now - 600, now - 600))  # وفشلٌ بعده
        out = wo.backup_alerts(self.cfg)
        self.assertEqual([a["severity"] for a in out], ["high"])

    def test_an_old_last_commit_still_alerts_by_age(self):
        now = time.time()
        os.utime(self.marker, (now - 200 * 3600, now - 200 * 3600))
        self._commit_at(now - 100 * 3600)
        self.assertEqual([a["severity"] for a in wo.backup_alerts(self.cfg)], ["high"])


if __name__ == "__main__":
    unittest.main()
