"""اختباراتُ ledger_at_github بمخرجات gh مسجَّلة:  python -m unittest test_ledger_at_github"""
import tempfile
import unittest
from pathlib import Path

import ledger
import ledger_at_github as g

PRS = [{"headRefOid": "abcdef1234567890", "mergedAt": "2026-10-20T10:03:00Z"}]
ACTS = [
    {"after": "abcdef1234567890", "timestamp": "2026-10-20T09:00:30Z"},
    {"after": "abcdef1234567890", "timestamp": "2026-10-20T09:20:00Z"},
    {"after": "ffffffff00000000", "timestamp": "2026-10-20T08:00:00Z"},
]


def fake(args):
    return PRS if args[0] == "pr" else ACTS


class AtGithub(unittest.TestCase):
    def test_merged_time_is_doha(self):
        self.assertEqual(g.github_time("merged", "abcdef12", fetch=fake), "2026-10-20T13:03:00+03:00")

    def test_pushed_is_first_push_reaching_head(self):
        self.assertEqual(g.github_time("pushed", "abcdef12", "claude/x", fetch=fake), "2026-10-20T12:00:30+03:00")

    def test_unknown_head_refused(self):
        with self.assertRaises(ledger.LedgerError):
            g.github_time("merged", "00000000", fetch=fake)

    def test_other_state_refused(self):
        with self.assertRaises(ledger.LedgerError):
            g.github_time("approved", "abcdef12", fetch=fake)

    def test_record_appends_only_and_is_read_back(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ledger.jsonl"
            ledger.append_event("created", "W-1", {"title": "x"}, p)
            before = p.read_text(encoding="utf-8")
            g.record("W-1", "merged", "abcdef12", "0409", fetch=fake, path=p)
            after = p.read_text(encoding="utf-8")
            self.assertTrue(after.startswith(before))
            self.assertEqual(len(after.splitlines()), len(before.splitlines()) + 1)
            self.assertEqual(g.corrected_times(ledger.load_events(p))["W-1"]["merged"], "2026-10-20T13:03:00+03:00")


if __name__ == "__main__":
    unittest.main()
