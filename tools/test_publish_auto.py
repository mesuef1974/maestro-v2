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

    def test_published_note_carries_pr_link_as_evidence(self):
        _, calls = self.run_apply([row("merged")])
        self.assertIn("/pull/10", calls[0][2]["note"])
        self.assertIn("25cef9a", calls[0][2]["note"])

    def test_missing_health_prints_unmeasured_and_moves_nothing(self):
        import io
        from contextlib import redirect_stderr
        from unittest import mock

        err = io.StringIO()
        with (
            mock.patch.object(pu.ps, "fetch_health", side_effect=pu.ps.SyncError("تعذّر قراءة /health/")),
            mock.patch.object(pu.ledger, "move") as mv,
            redirect_stderr(err),
        ):
            rc = pu.main(["--apply"])
        self.assertEqual(rc, 2)
        self.assertIn("غير مقيس", err.getvalue())
        mv.assert_not_called()

    def test_one_message_per_owner(self):
        rows = [row("merged", "W-1"), row("merged", "W-2"), row("merged", "W-3")]
        states = {"W-1": {"held_by": "0702"}, "W-2": {"held_by": "0702"}, "W-3": {}}
        out = pu.ps.messages_by_owner(rows, states, "25cef9a")
        self.assertEqual(sorted(out), ["0701", "0702"])
        self.assertIn("W-1", out["0702"])
        self.assertIn("W-2", out["0702"])

    def test_nothing_due_nothing_moved(self):
        out, calls = self.run_apply([])
        self.assertEqual((out, calls), ([], []))


if __name__ == "__main__":
    unittest.main()
