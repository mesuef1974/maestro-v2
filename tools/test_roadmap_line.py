"""اختباراتُ roadmap_line (W-20261016-027) — بلا شبكةٍ ولا دفتر:  python -m unittest tools.test_roadmap_line"""

import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import roadmap_line as rl  # noqa: E402

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
PR = {"number": 7, "merge": "abcdef1234", "at": "2026-10-16T11:30:00Z"}


def card(**kw):
    return {"state": "merged", "head": "aaaaaaaa", "problem": "x", "accept": "اختبار أخضر", **kw}


class Lines(unittest.TestCase):
    def test_merged_pr_gives_complete_line(self):
        ln = rl.build_line("W-1", card(), PR, NOW)
        for k in ("card", "item", "pr", "merge", "status", "progress", "measured", "remaining"):
            self.assertTrue(ln[k], k)
        self.assertFalse(ln["late"])

    def test_unmerged_pr_gives_no_line(self):
        self.assertIsNone(rl.build_line("W-1", card(), {}, NOW))
        self.assertIsNone(rl.build_line("W-1", card(), {"number": 7, "merge": ""}, NOW))

    def test_item_resolution_order(self):
        self.assertEqual(rl.find_item(card(roadmap_item="N-5"))[0], "N-5")
        self.assertEqual(rl.find_item(card(problem="يخصّ N-12 الأمني"))[0], "N-12")
        self.assertEqual(rl.find_item(card())[0], "N-جديد")

    def test_late_flag_after_an_hour(self):
        late = dict(PR, at="2026-10-16T09:00:00Z")
        self.assertTrue(rl.build_line("W-1", card(), late, NOW)["late"])

    def test_collect_skips_seen_and_non_merged(self):
        states = {"W-1": card(), "W-2": card(state="approved"), "W-3": card()}
        out = rl.collect(states, {"aaaaaaaa": PR}, {"W-3"}, NOW)
        self.assertEqual([x["card"] for x in out], ["W-1"])


class Cli(unittest.TestCase):
    def test_missing_ledger_or_gh_prints_unmeasured(self):
        with (
            mock.patch.object(rl.ps, "merged_prs", side_effect=rl.ps.SyncError("فشل gh")),
            mock.patch.object(rl.ledger, "load_events", return_value=[]),
            mock.patch("sys.stderr") as err,
        ):
            rc = rl.main([])
        self.assertEqual(rc, 2)
        self.assertIn("غير مقيس", "".join(c.args[0] for c in err.write.call_args_list))

    def test_seen_cards_read_back_from_output_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "p.md"
            p.write_text("- بطاقة W-20261016-027 ← البند N-1", encoding="utf-8")
            self.assertEqual(rl.seen_cards(p), {"W-20261016-027"})


if __name__ == "__main__":
    unittest.main()
