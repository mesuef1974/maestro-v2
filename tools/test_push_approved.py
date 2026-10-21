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


def test_same_head_uses_common_prefix_of_at_least_seven():
    pa = __import__("push_approved")
    assert pa.same_head("3e60cdd1ff914e31", "3e60cdd")
    assert pa.same_head("3e60cdd", "3e60cdd1")
    assert pa.same_head("C149E527", "c149e527aa")
    assert not pa.same_head("3e60cdd1", "3e60cde1")
    assert not pa.same_head("3e60cd", "3e60cd"), "أقلّ من ٧ أحرف لا يكفي"
    assert not pa.same_head("", "")


def test_guard_accepts_seven_char_ledger_head_and_passes_it_unchanged_to_approval():
    seven = {"W-1": {"state": "approved", "approved_head": "aaaaaaa"}}
    seen = []
    assert pa.guard("W-1", "claude/x", ".", seven, fake_git(), lambda c, h: seen.append(h) or True) == HEAD
    assert seen == ["aaaaaaa"], "approval_check يتلقّى الرأس كما سُجّل في الدفتر لا مقتطعاً"


def test_pump_branches_are_claude_or_w_and_never_main():
    for b in ("claude/x", "w20261020-001-x", "w0702-chart"):
        assert pa.PUMP_BRANCH_RE.match(b), b
    for b in ("main", "master", "feature/x", "claude/", "W/x"):
        assert not pa.PUMP_BRANCH_RE.match(b), b
    assert pa.guard("W-1", "w0702-chart", ".", ITEMS, fake_git(), ok, branch_re=pa.PUMP_BRANCH_RE) == HEAD
    try:
        pa.guard("W-1", "w0702-chart", ".", ITEMS, fake_git(), ok)
    except pa.PushRefused:
        pass
    else:
        raise AssertionError("الافتراضُ claude/* وحدَه")


def receipt_git(gitdir):
    base = fake_git()

    def git(repo, *args):
        if args[:2] == ("rev-parse", "--absolute-git-dir"):
            return 0, f"{gitdir}\n"
        return base(repo, *args)

    return git


def test_the_receipt_must_be_ok_and_for_the_same_head(tmp_path):
    import json

    f = tmp_path / pa.ledger.RECEIPT_NAME
    assert "prepush" in pa.receipt_problem(".", HEAD, receipt_git(tmp_path))
    for bad in ({"head": "bbbbbbbb", "ok": True}, {"head": "aaaaaaaa", "ok": False}):
        f.write_text(json.dumps(bad), encoding="utf-8")
        assert pa.receipt_problem(".", HEAD, receipt_git(tmp_path))
    f.write_text(json.dumps({"head": "aaaaaaaa", "ok": True}), encoding="utf-8")
    assert pa.receipt_problem(".", HEAD, receipt_git(tmp_path)) is None
    assert pa.guard("W-1", "claude/x", ".", ITEMS, receipt_git(tmp_path), ok, require_receipt=True) == HEAD
    f.unlink()
    try:
        pa.guard("W-1", "claude/x", ".", ITEMS, receipt_git(tmp_path), ok, require_receipt=True)
    except pa.PushRefused as exc:
        assert "prepush" in str(exc)
    else:
        raise AssertionError("بلا إيصالٍ لا دفع")


def test_guard_still_rejects_a_head_that_differs_within_the_shared_prefix():
    seven = {"W-1": {"state": "approved", "approved_head": "aaaaaab"}}
    try:
        pa.guard("W-1", "claude/x", ".", seven, fake_git(), lambda c, h: True)
    except pa.PushRefused:
        return
    raise AssertionError("رأسٌ مخالف يجب أن يُرفض")

