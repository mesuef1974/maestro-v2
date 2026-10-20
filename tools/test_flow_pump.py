"""اختباراتُ مضخّة التدفّق:  python -m pytest test_flow_pump.py"""

import unittest
from types import SimpleNamespace
from unittest import mock

import flow_pump as fp


def _item(state="ready_for_review", *texts):
    return {"state": state, "notes": [{"text": t} for t in texts]}


class ReadyHead(unittest.TestCase):
    def test_the_last_announced_head_wins(self):
        item = _item("ready_for_review", "جاهزٌ للمعاينة بالرأس aaaaaaaa11", "رأسٌ جديد: الرأس bbbbbbbb22")
        self.assertEqual(fp.ready_head(item), "bbbbbbbb")

    def test_a_card_without_an_announced_head_has_none(self):
        self.assertIsNone(fp.ready_head(_item("ready_for_review", "ملاحظةٌ بلا رأس")))
        self.assertIsNone(fp.ready_head({"state": "ready_for_review"}))

    def test_a_head_shorter_than_eight_hex_is_not_taken(self):
        self.assertIsNone(fp.ready_head(_item("ready_for_review", "بالرأس abc123")))


class ApprovePass(unittest.TestCase):
    STATES = {
        "W-1": _item("ready_for_review", "جاهزٌ للمعاينة بالرأس aaaaaaaa"),
        "W-2": _item("ready_for_review", "بلا رأس"),
        "W-3": _item("approved", "بالرأس cccccccc"),
    }

    def test_only_ready_cards_are_considered(self):
        with mock.patch.object(fp, "approval_ok", return_value=False) as ok:
            lines = fp.approve_pass(self.STATES, apply=False)
        self.assertEqual(ok.call_count, 1)  # W-1 وحدَها لها رأس
        self.assertEqual(len(lines), 2)

    def test_a_card_without_approval_proof_waits_and_is_never_moved(self):
        with (
            mock.patch.object(fp, "approval_ok", return_value=False),
            mock.patch.object(fp.subprocess, "run") as run,
        ):
            lines = fp.approve_pass({"W-1": self.STATES["W-1"]}, apply=True)
        run.assert_not_called()
        self.assertIn("ينتظر", lines[0])

    def test_dry_run_reports_but_does_not_move(self):
        with (
            mock.patch.object(fp, "approval_ok", return_value=True),
            mock.patch.object(fp.subprocess, "run") as run,
        ):
            lines = fp.approve_pass({"W-1": self.STATES["W-1"]}, apply=False)
        run.assert_not_called()
        self.assertIn("(عرض)", lines[0])

    def test_apply_moves_with_the_proven_head(self):
        done = SimpleNamespace(returncode=0, stdout="ok", stderr="")
        with (
            mock.patch.object(fp, "approval_ok", return_value=True),
            mock.patch.object(fp.subprocess, "run", return_value=done) as run,
        ):
            lines = fp.approve_pass({"W-1": self.STATES["W-1"]}, apply=True)
        cmd = run.call_args.args[0]
        self.assertIn("approved", cmd)
        self.assertEqual(cmd[cmd.index("--head") + 1], "aaaaaaaa")
        self.assertTrue(lines[0].endswith("✔"))

    def test_a_ledger_refusal_is_reported_not_forced(self):
        refused = SimpleNamespace(returncode=1, stdout="", stderr="مرفوض: دليلٌ بصريّ ناقص")
        with (
            mock.patch.object(fp, "approval_ok", return_value=True),
            mock.patch.object(fp.subprocess, "run", return_value=refused),
        ):
            lines = fp.approve_pass({"W-1": self.STATES["W-1"]}, apply=True)
        self.assertIn("✘", lines[0])
        self.assertIn("دليلٌ بصريّ", lines[0])


class Main(unittest.TestCase):
    def test_skip_excludes_cards_from_both_stages(self):
        seen = {}

        def fake_pass(states, apply):
            seen["approve"] = sorted(states)
            return []

        fake_states = {"W-1": _item(), "W-2": _item()}
        with (
            mock.patch.object(fp.ledger, "load_events", return_value=[]),
            mock.patch.object(fp.ledger, "reduce_state", return_value=fake_states),
            mock.patch.object(fp, "approve_pass", side_effect=fake_pass),
            mock.patch.object(fp.ledger_sync, "plan", side_effect=lambda st, *r, **k: sorted(st)) as plan,
            mock.patch.object(fp.ledger_sync, "cycle", side_effect=lambda apply, n: (fp.ledger_sync.plan(fake_states), 0)[1]),
        ):
            code = fp.main(["--skip", "W-1"])
        self.assertEqual(code, 0)
        self.assertEqual(seen["approve"], ["W-2"])
        self.assertTrue(plan.called)


if __name__ == "__main__":
    unittest.main()
