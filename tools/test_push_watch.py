"""اختباراتُ push_watch (W-20261019-016) — بلا شبكةٍ ولا git حقيقيّ:  python -m pytest test_push_watch.py"""

import tempfile
import unittest
from pathlib import Path

import ledger
import push_watch as pw

HEAD = "a" * 40
PORCELAIN = (
    "worktree C:/repo\nHEAD {h}\nbranch refs/heads/main\n\n"
    "worktree C:/repo/wt1\nHEAD {h}\nbranch refs/heads/claude/task-one\n\n"
    "worktree C:/repo/wt2\nHEAD {o}\nbranch refs/heads/claude/other\n\n"
    "worktree C:/repo/wt3\nHEAD {h}\ndetached\n"
).format(h=HEAD, o="b" * 40)


def fake_git(porcelain=PORCELAIN, has_card=True, head=HEAD, push_rc=0, dirty=""):
    calls = []

    def git(repo, *args):
        calls.append((repo, args))
        if args[0] == "worktree":
            return 0, porcelain
        if args[0] == "log":
            return 0, (HEAD + "\n") if has_card else ""
        if args[0] == "rev-parse":
            return 0, head + "\n"
        if args[0] == "status":
            return 0, dirty
        if args[0] == "push":
            return push_rc, "boom" if push_rc else ""
        if args[0] == "ls-remote":
            return 0, f"{head}\trefs/heads/claude/task-one\n"
        return 0, ""

    git.calls = calls
    return git


def ok(card, head):
    return True


class FindTree(unittest.TestCase):
    def test_worktrees_are_parsed(self):
        trees = pw.worktrees("C:/repo", fake_git())
        self.assertEqual([t.get("branch") for t in trees], ["main", "claude/task-one", "claude/other", None])

    def test_only_the_claude_branch_on_the_exact_head_with_the_card_matches(self):
        tree, why = pw.find_tree("W-1", "aaaaaaaa", ["C:/repo"], fake_git())
        self.assertEqual(tree["branch"], "claude/task-one")
        self.assertEqual(why, "")

    def test_no_tree_when_the_card_is_not_in_the_commits(self):
        tree, why = pw.find_tree("W-1", "aaaaaaaa", ["C:/repo"], fake_git(has_card=False))
        self.assertIsNone(tree)
        self.assertIn(pw.QUIET, why)

    def test_no_tree_when_the_head_differs(self):
        tree, why = pw.find_tree("W-1", "cccccccc", ["C:/repo"], fake_git())
        self.assertIsNone(tree)
        self.assertIn(pw.QUIET, why)

    def test_main_is_never_a_target(self):
        only_main = "worktree C:/repo\nHEAD {h}\nbranch refs/heads/main\n".format(h=HEAD)
        self.assertIsNone(pw.find_tree("W-1", "aaaaaaaa", ["C:/repo"], fake_git(only_main))[0])

    def test_two_trees_on_the_same_head_are_ambiguous_not_guessed(self):
        twice = PORCELAIN + "\nworktree C:/repo/wt4\nHEAD {h}\nbranch refs/heads/claude/twin\n".format(h=HEAD)
        tree, why = pw.find_tree("W-1", "aaaaaaaa", ["C:/repo"], fake_git(twice))
        self.assertIsNone(tree)
        self.assertIn("التباس", why)

    def test_the_same_tree_seen_through_two_repos_is_counted_once(self):
        tree, _ = pw.find_tree("W-1", "aaaaaaaa", ["C:/repo", "C:/repo"], fake_git())
        self.assertEqual(tree["branch"], "claude/task-one")


class Scan(unittest.TestCase):
    def setUp(self):
        self.path = str(Path(tempfile.mkdtemp()) / "e.jsonl")
        self.card = ledger.add_item("owner", "tool", "م", "أ", "ق", start="2026-10-19T08:00", priority="P2", path=self.path, held_by="0702")
        ledger.move(self.card, "approved", path=self.path, note="اعتمد المالك على 8500", head="aaaaaaaa", by="0501", waive_spec="اختبار")
        self.card = self.card

    def run_scan(self, **kw):
        git = kw.pop("git", None) or fake_git()
        approved = kw.pop("approved", ok)
        items = ledger.reduce_state(ledger.load_events(self.path))
        res = pw.scan(items, ["C:/repo"], path=self.path, git=git, approved=approved, **kw)
        return res, git

    def state(self):
        return ledger.reduce_state(ledger.load_events(self.path))[self.card]["state"]

    def test_an_approved_card_is_pushed_without_force_and_recorded(self):
        res, git = self.run_scan()
        self.assertEqual([(r["status"], r["branch"]) for r in res], [("pushed", "claude/task-one")])
        pushes = [a for _, a in git.calls if a[0] == "push"]
        self.assertEqual(pushes, [("push", "origin", "HEAD:refs/heads/claude/task-one")])
        self.assertNotIn("--force", pushes[0])
        self.assertEqual(self.state(), "pushed")

    def test_no_repeat_after_the_card_is_pushed(self):
        self.run_scan()
        res, git = self.run_scan()
        self.assertEqual(res, [])
        self.assertFalse([a for _, a in git.calls if a[0] == "push"])

    def test_dry_run_pushes_nothing(self):
        res, git = self.run_scan(apply=False)
        self.assertEqual(res[0]["status"], "dry")
        self.assertFalse([a for _, a in git.calls if a[0] == "push"])
        self.assertEqual(self.state(), "approved")

    def test_a_changed_head_is_refused_and_not_pushed(self):
        res, git = self.run_scan(git=fake_git(head="d" * 40))
        # الشجرةُ وُجدت بالرأس المسجَّل لكنّ HEAD الفعليّ تغيّر فيرفض الحارس
        self.assertEqual(res[0]["status"], "refused")
        self.assertFalse([a for _, a in git.calls if a[0] == "push"])

    def test_a_dirty_tree_is_refused_by_the_guard(self):
        res, git = self.run_scan(git=fake_git(dirty=" M a.py\n"))
        self.assertEqual(res[0]["status"], "refused")
        self.assertFalse([a for _, a in git.calls if a[0] == "push"])
        self.assertEqual(self.state(), "approved")

    def test_a_failing_approval_check_is_refused(self):
        res, git = self.run_scan(approved=lambda c, h: False)
        self.assertEqual(res[0]["status"], "refused")
        self.assertFalse([a for _, a in git.calls if a[0] == "push"])

    def test_a_non_claude_branch_is_never_pushed(self):
        feature = "worktree C:/repo/wt1\nHEAD {h}\nbranch refs/heads/feature/x\n".format(h=HEAD)
        res, git = self.run_scan(git=fake_git(feature))
        self.assertEqual(res[0]["status"], "skipped")
        self.assertFalse([a for _, a in git.calls if a[0] == "push"])


class Messages(unittest.TestCase):
    DIRECTORY = {"0601": {"id": "local_601"}, "0702": {"id": "local_702"}}

    def test_a_push_hands_over_to_0601_without_opening_a_pr(self):
        res = [{"card": "W-1", "status": "pushed", "branch": "claude/x", "head": "aaaaaaaa", "holder": "0702", "reason": ""}]
        (to, sid, text), = pw.messages(res, self.DIRECTORY, set())
        self.assertEqual((to, sid), ("0601", "local_601"))
        self.assertIn("claude/x", text)
        self.assertIn("aaaaaaaa", text)
        self.assertIn("الدفتر", text)

    def test_a_refusal_goes_to_the_holder_once(self):
        res = [{"card": "W-1", "status": "refused", "branch": "claude/x", "head": "aaaaaaaa", "holder": "0702", "reason": "شجرةٌ متّسخة"}]
        seen: set = set()
        first = pw.messages(res, self.DIRECTORY, seen)
        self.assertEqual(first[0][0], "0702")
        self.assertEqual(pw.messages(res, self.DIRECTORY, seen), [])

    def test_a_skipped_card_is_silent(self):
        res = [{"card": "W-1", "status": "skipped", "branch": "", "head": "aaaaaaaa", "holder": "0702", "reason": pw.QUIET}]
        self.assertEqual(pw.messages(res, self.DIRECTORY, set()), [])


if __name__ == "__main__":
    unittest.main()
