"""اختباراتُ publish_auto (W-20261015-005) — بلا شبكةٍ ولا دفتر حقيقيّ:  python -m unittest tools.test_publish_auto"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402
import publish_auto as pu  # noqa: E402


def row(state, cid="W-1"):
    return {"id": cid, "state": state, "head": "aaaaaaaa", "pr": 10, "merge": "1111111", "prod": "25cef9a"}


class Apply(unittest.TestCase):
    def run_apply(self, rows):
        calls = []

        def move(cid, step, **kw):
            calls.append((cid, step, kw))

        return pu.apply_rows(rows, "25cef9a1234", move=move), calls

    def test_chain_is_walked_from_current_state(self):
        _, calls = self.run_apply([row("approved")])
        self.assertEqual([c[1] for c in calls], ["pushed", "merged", "published"])
        _, calls = self.run_apply([row("merged")])
        self.assertEqual([c[1] for c in calls], ["published"])

    def test_only_pushed_step_waives_remote_check_and_published_carries_note(self):
        _, calls = self.run_apply([row("approved")])
        by_step = {c[1]: c[2] for c in calls}
        self.assertIn("waive_remote_check", by_step["pushed"])
        self.assertNotIn("waive_remote_check", by_step["merged"])
        self.assertIn("آلياً (publish_auto)", by_step["published"]["note"])

    def test_never_claims_to_be_0601(self):
        _, calls = self.run_apply([row("pushed")])
        self.assertTrue(all("by" not in c[2] for c in calls))

    def test_one_failure_does_not_stop_the_rest(self):
        def move(cid, step, **kw):
            if cid == "W-1":
                raise ledger.LedgerError("boom")

        out = pu.apply_rows([row("merged", "W-1"), row("merged", "W-2")], "25cef9a1234", move=move)
        self.assertIn("✘", out[0])
        self.assertIn("W-2 ← published", out[1])

    def test_nothing_due_nothing_moved(self):
        out, calls = self.run_apply([])
        self.assertEqual((out, calls), ([], []))


if __name__ == "__main__":
    unittest.main()
