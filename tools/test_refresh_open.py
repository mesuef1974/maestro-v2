"""اختباراتُ refresh_open بـgh وهميّ."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import refresh_open as ro  # noqa: E402

PRS = [
    {"number": 1, "headRefName": "a", "mergeStateStatus": "BEHIND", "isDraft": False},
    {"number": 2, "headRefName": "b", "mergeStateStatus": "DIRTY", "isDraft": False},
    {"number": 3, "headRefName": "c", "mergeStateStatus": "CLEAN", "isDraft": False},
    {"number": 4, "headRefName": "d", "mergeStateStatus": "BEHIND", "isDraft": True},
]


class RefreshOpenTest(unittest.TestCase):
    def test_classify(self):
        g = ro.classify(PRS)
        self.assertEqual([p["number"] for p in g["update"]], [1])
        self.assertEqual([p["number"] for p in g["conflict"]], [2])
        self.assertEqual([p["number"] for p in g["leave"]], [3, 4])

    def test_actions_only_update_branch_never_merge(self):
        cmds = ro.actions(ro.classify(PRS), "o/r")
        self.assertEqual(cmds, [["gh", "pr", "update-branch", "1", "--repo", "o/r"]])

    def test_list_open_handles_failure(self):
        self.assertIsNone(ro.list_open(None, lambda c: (1, "")))
        self.assertEqual(ro.list_open(None, lambda c: (0, json.dumps(PRS))), PRS)

    def test_shadow_runs_nothing(self):
        with (
            mock.patch.object(ro, "list_open", return_value=PRS),
            mock.patch.object(ro, "run") as r,
            mock.patch.dict("os.environ", {}, clear=True),
        ):
            self.assertEqual(ro.main(["--execute"]), 0)
            r.assert_not_called()

    def test_enforced_executes_updates(self):
        with (
            mock.patch.object(ro, "list_open", return_value=PRS),
            mock.patch.object(ro, "run", return_value=(0, "ok")) as r,
            mock.patch.dict("os.environ", {"REFRESH_OPEN_ENFORCE": "1"}),
        ):
            self.assertEqual(ro.main(["--execute"]), 0)
            r.assert_called_once()


if __name__ == "__main__":
    unittest.main()
