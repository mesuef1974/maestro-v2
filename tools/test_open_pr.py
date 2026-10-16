"""اختباراتُ open_pr بـgh ومُحضِّرٍ وهميّين."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import open_pr  # noqa: E402

LINE = "اعتُمد من المالك على 8500 — 2026-10-16 — الرأس ae94aa3f"


def fake(prep_code=0, prep_out=LINE, listing="[]"):
    def runner(cmd, cwd=None):
        if "pr_open_prep.py" in " ".join(map(str, cmd)):
            return prep_code, prep_out
        if cmd[:3] == ["gh", "pr", "list"]:
            return 0, listing
        raise AssertionError(f"أمرٌ غير متوقَّع: {cmd}")

    return runner


class OpenPrTest(unittest.TestCase):
    def plan(self, **kw):
        with mock.patch.object(
            open_pr.pr_open_prep,
            "ledger_card",
            return_value={"problem": "فتح الطلب آلياً"},
        ):
            return open_pr.plan(
                "W-1", ".", "claude/x", "origin/main", None, True, fake(**kw)
            )

    def test_unapproved_head_refused(self):
        code, cmds, msg = self.plan(prep_code=3, prep_out="الاعتمادُ غيرُ ثابتٍ")
        self.assertEqual((code, cmds), (3, []))
        self.assertIn("غيرُ ثابتٍ", msg)

    def test_approved_generates_line_and_commands(self):
        code, cmds, msg = self.plan()
        self.assertEqual(code, 0)
        create, queue = cmds
        self.assertEqual(msg, LINE)
        self.assertIn(LINE, create[create.index("--body") + 1])
        self.assertEqual(create[create.index("--base") + 1], "main")
        self.assertIn("--auto", queue)
        self.assertNotIn("--admin", queue)

    def test_existing_open_pr_refused(self):
        code, cmds, msg = self.plan(listing='[{"url":"https://x/pull/9"}]')
        self.assertEqual((code, cmds), (7, []))
        self.assertIn("pull/9", msg)

    def test_conflict_and_unpushed_codes_pass_through(self):
        for rc in (4, 5):
            self.assertEqual(self.plan(prep_code=rc, prep_out="x")[0], rc)

    def test_shadow_does_not_execute(self):
        with (
            mock.patch.object(
                open_pr, "plan", return_value=(0, [["gh", "pr", "create"]], LINE)
            ),
            mock.patch.object(open_pr, "run") as r,
            mock.patch.dict("os.environ", {}, clear=False),
        ):
            self.assertEqual(open_pr.main(["W-1", "--branch", "claude/x"]), 0)
            self.assertEqual(
                open_pr.main(["W-1", "--branch", "claude/x", "--execute"]), 0
            )
            r.assert_not_called()

    def test_title_trim(self):
        self.assertEqual(
            len(open_pr.make_title({"problem": "ا" * 200}, "W-1", None)),
            open_pr.TITLE_MAX,
        )


if __name__ == "__main__":
    unittest.main()
