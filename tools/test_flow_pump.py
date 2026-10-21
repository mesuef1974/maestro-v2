"""اختباراتُ مضخّة التدفّق:  python -m pytest test_flow_pump.py"""

import os
import tempfile
import time
import unittest
from pathlib import Path
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
        tmp = Path(tempfile.mkdtemp())
        with (
            mock.patch.object(fp, "LOCK", tmp / "p.lock"),
            mock.patch.object(fp, "LOG", tmp / "p.log"),
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


class HeadPattern(unittest.TestCase):
    def test_the_three_phrasings_are_read(self):
        for phrase in ("بالرأس", "للرأس", "الرأس"):
            self.assertEqual(fp.ready_head(_item("ready_for_review", f"{phrase} deadbeef99")), "deadbeef")

    def test_a_full_forty_hex_head_is_cut_to_eight(self):
        self.assertEqual(fp.ready_head(_item("ready_for_review", "الرأس " + "a1" * 20)), "a1a1a1a1")


class Lock(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [
            mock.patch.object(fp, "LOCK", self.tmp / "p.lock"),
            mock.patch.object(fp, "LOG", self.tmp / "p.log"),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_a_free_lock_is_taken_once(self):
        self.assertTrue(fp._lock())
        self.assertFalse(fp._lock())

    def test_a_stale_lock_is_treated_as_dead_and_replaced(self):
        fp.LOCK.write_text("")
        old = time.time() - fp.STALE_LOCK_S - 5
        os.utime(fp.LOCK, (old, old))
        self.assertTrue(fp._lock())

    def test_a_fresh_lock_makes_the_cycle_skip_without_touching_the_ledger(self):
        fp.LOCK.write_text("")
        with mock.patch.object(fp, "_run") as run:
            self.assertEqual(fp.main([]), 0)
        run.assert_not_called()
        self.assertTrue(fp.LOCK.exists())  # قفلُ غيرِها لا يُحذف

    def test_the_lock_is_released_even_if_the_cycle_raises(self):
        with mock.patch.object(fp, "_run", side_effect=RuntimeError("x")):
            with self.assertRaises(RuntimeError):
                fp.main([])
        self.assertFalse(fp.LOCK.exists())


class PublishStage(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        for name in ("LOCK", "LOG"):
            p = mock.patch.object(fp, name, tmp / name)
            p.start()
            self.addCleanup(p.stop)

    def _run(self, argv):
        real_move = fp.ledger.move
        seen = {}

        def cycle(apply, n):
            fp.ledger.move("W-1", "published", note="x")
            return 0

        with (
            mock.patch.object(fp.ledger, "load_events", return_value=[]),
            mock.patch.object(fp.ledger, "reduce_state", return_value={}),
            mock.patch.object(fp.ledger, "move", side_effect=lambda *a, **k: seen.update(k)) as mv,
            mock.patch.object(fp.ledger_sync, "cycle", side_effect=cycle),
        ):
            code = fp.main(argv)
        self.assertIsNotNone(real_move)
        return code, seen, mv

    def test_every_ledger_sync_move_carries_the_pump_identity(self):
        code, seen, _ = self._run(["--apply"])
        self.assertEqual(code, 0)
        self.assertEqual(seen["by"], fp.SENDER)

    def test_an_explicit_by_is_not_overridden(self):
        called = {}
        with (
            mock.patch.object(fp.ledger, "load_events", return_value=[]),
            mock.patch.object(fp.ledger, "reduce_state", return_value={}),
            mock.patch.object(fp.ledger, "move", side_effect=lambda *a, **k: called.update(k)),
            mock.patch.object(
                fp.ledger_sync, "cycle", side_effect=lambda apply, n: fp.ledger.move("W-1", "merged", by="0601") and 0
            ),
        ):
            fp.main(["--apply"])
        self.assertEqual(called["by"], "0601")

    def test_a_dry_run_writes_no_log_line(self):
        with (
            mock.patch.object(fp.ledger, "load_events", return_value=[]),
            mock.patch.object(fp.ledger, "reduce_state", return_value={}),
            mock.patch.object(fp.ledger_sync, "cycle", return_value=0),
        ):
            fp.main([])
        self.assertFalse(fp.LOG.exists())

    def test_an_applied_cycle_appends_one_log_line_with_the_result(self):
        with (
            mock.patch.object(fp.ledger, "load_events", return_value=[]),
            mock.patch.object(fp.ledger, "reduce_state", return_value={}),
            mock.patch.object(fp.ledger_sync, "cycle", return_value=0),
        ):
            fp.main(["--apply"])
        self.assertIn("rc=0", fp.LOG.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
