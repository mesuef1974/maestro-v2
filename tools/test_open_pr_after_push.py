"""اختباراتُ الغلاف open_pr_after_push: تمريرُ الوسائط إلى open_pr.main دون تكرار منطقه."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import open_pr_after_push  # noqa: E402


class OpenAfterPushTest(unittest.TestCase):
    def test_dry_run_by_default(self):
        with mock.patch.object(open_pr_after_push.open_pr, "main", return_value=0) as m:
            code = open_pr_after_push.open_after_push("W-1", "/repo")
        self.assertEqual(code, 0)
        m.assert_called_once_with(["W-1", "--repo", "/repo"])

    def test_branch_and_execute_forwarded(self):
        with mock.patch.object(open_pr_after_push.open_pr, "main", return_value=3) as m:
            code = open_pr_after_push.open_after_push(
                "W-1", "/repo", branch="claude/x", execute=True
            )
        self.assertEqual(code, 3)
        m.assert_called_once_with(
            ["W-1", "--repo", "/repo", "--branch", "claude/x", "--execute"]
        )

    def test_cli_exit_code_is_open_pr_exit_code(self):
        with mock.patch.object(open_pr_after_push.open_pr, "main", return_value=5):
            self.assertEqual(open_pr_after_push.main(["W-1", "--repo", "/r"]), 5)


if __name__ == "__main__":
    unittest.main()
