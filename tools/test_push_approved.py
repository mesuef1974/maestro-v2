"""اختباراتُ push_approved (W-20261015-004) — بلا شبكةٍ ولا git حقيقيّ:  python -m unittest tools.test_push_approved"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import push_approved as pa  # noqa: E402

HEAD = "a" * 40
ITEMS = {"W-1": {"state": "approved", "approved_head": "aaaaaaaa"}}


def fake_git(head=HEAD, dirty="", push_rc=0, remote=None):
    calls = []

    def git(repo, *args):
        calls.append(args)
        if args[0] == "rev-parse":
            return 0, head + "\n"
        if args[0] == "status":
            return 0, dirty
        if args[0] == "push":
            return push_rc, "boom" if push_rc else ""
        if args[0] == "ls-remote":
            return 0, f"{remote or head}\trefs/heads/x\n"
        return 0, ""

    git.calls = calls
    return git


def ok(card, head):
    return True


class Guard(unittest.TestCase):
    def test_passes_when_everything_matches(self):
        self.assertEqual(pa.guard("W-1", "claude/x", ".", ITEMS, fake_git(), ok), HEAD)

    def test_refuses_main_and_foreign_branches(self):
        for b in ("main", "master", "claude/../main", "feature/x", "claude/"):
            with self.assertRaises(pa.PushRefused):
                pa.guard("W-1", b, ".", ITEMS, fake_git(), ok)

    def test_refuses_head_mismatch(self):
        with self.assertRaises(pa.PushRefused):
            pa.guard("W-1", "claude/x", ".", ITEMS, fake_git(head="b" * 40), ok)

    def test_refuses_dirty_tracked_files(self):
        with self.assertRaises(pa.PushRefused):
            pa.guard("W-1", "claude/x", ".", ITEMS, fake_git(dirty=" M a.py\n"), ok)

    def test_refuses_when_not_approved_or_no_head(self):
        for item in ({"state": "routed", "approved_head": "aaaaaaaa"}, {"state": "approved"}):
            with self.assertRaises(pa.PushRefused):
                pa.guard("W-1", "claude/x", ".", {"W-1": item}, fake_git(), ok)

    def test_refuses_when_approval_check_fails(self):
        with self.assertRaises(pa.PushRefused):
            pa.guard("W-1", "claude/x", ".", ITEMS, fake_git(), lambda c, h: False)

    def test_unknown_card(self):
        with self.assertRaises(pa.PushRefused):
            pa.guard("W-9", "claude/x", ".", ITEMS, fake_git(), ok)


class Push(unittest.TestCase):
    def setUp(self):
        self._items, self._load = pa.ledger.reduce_state, pa.ledger.load_events
        pa.ledger.reduce_state = lambda ev: ITEMS
        pa.ledger.load_events = lambda path=None: []
        self.notes, self.moves = [], []
        self._note, self._move = pa.ledger.add_note, pa.ledger.move
        pa.ledger.add_note = lambda *a, **k: self.notes.append(a)
        pa.ledger.move = lambda *a, **k: self.moves.append((a, k))

    def tearDown(self):
        pa.ledger.reduce_state, pa.ledger.load_events = self._items, self._load
        pa.ledger.add_note, pa.ledger.move = self._note, self._move

    def test_dry_run_pushes_nothing(self):
        g = fake_git()
        msg = pa.push("W-1", "claude/x", ".", False, git=g, approved=ok)
        self.assertIn("عرض", msg)
        self.assertFalse([c for c in g.calls if c[0] == "push"])
        self.assertEqual(self.moves, [])

    def test_apply_pushes_head_refspec_without_force_and_records(self):
        g = fake_git()
        pa.push("W-1", "claude/x", ".", True, git=g, approved=ok)
        pushes = [c for c in g.calls if c[0] == "push"]
        self.assertEqual(pushes, [("push", "origin", "HEAD:refs/heads/claude/x")])
        self.assertEqual(len(self.notes), 1)
        self.assertEqual(self.moves[0][0][:2], ("W-1", "pushed"))

    def test_remote_mismatch_after_push_is_not_recorded(self):
        with self.assertRaises(pa.PushRefused):
            pa.push("W-1", "claude/x", ".", True, git=fake_git(remote="c" * 40), approved=ok)
        self.assertEqual(self.moves, [])

    def test_push_failure_is_not_recorded(self):
        with self.assertRaises(pa.PushRefused):
            pa.push("W-1", "claude/x", ".", True, git=fake_git(push_rc=1), approved=ok)
        self.assertEqual(self.moves, [])


if __name__ == "__main__":
    unittest.main()
