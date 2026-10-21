"""تصنيفُ الفروع المحلية (W-20261020-002): الأربع قوائم، السحقُ، وقائمةُ الحذف المقترحة لا تشمل شجرةً حيّة."""

import unittest

import branch_status as bs
import branch_triage as bt


def pr(n, state, head, merge=None):
    return {"number": n, "state": state, "headRefOid": head, "mergeCommit": {"oid": merge} if merge else None}


class Triage(unittest.TestCase):
    def run_triage(self, branches, prs, ahead=None, contains=None, cm=None, elsewhere=None, checked_out=frozenset()):
        return bt.triage(
            branches, lambda n: (ahead or {}).get(n, 1), prs, contains or (lambda a, b: a == b), cm, elsewhere, checked_out
        )

    def test_four_lists_and_other(self):
        branches = {"m": "a" * 40, "anc": "b" * 40, "nopr": "c" * 40, "closed": "d" * 40, "open": "e" * 40, "main": "f" * 40}
        prs = {
            "m": [pr(1, "MERGED", "a" * 40, "x1")],
            "closed": [pr(2, "CLOSED", "d" * 40)],
            "open": [pr(3, "OPEN", "e" * 40)],
        }
        out = self.run_triage(branches, prs, elsewhere=lambda h: [9] if h == "b" * 40 else [])
        self.assertEqual([r["branch"] for r in out["merged_pr"]], ["m"])
        self.assertEqual([r["branch"] for r in out["merged_ancestor"]], ["anc"])
        self.assertEqual([r["branch"] for r in out["no_pr"]], ["nopr"])
        self.assertEqual([r["branch"] for r in out["closed_unmerged"]], ["closed"])
        self.assertEqual([r["branch"] for r in out["other"]], ["open"])
        self.assertNotIn("main", [r["branch"] for v in out.values() for r in v])

    def test_squash_merged_by_content_counts_as_merged(self):
        out = self.run_triage(
            {"sq": "a" * 40}, {"sq": [pr(1, "MERGED", "z" * 40, "mc")]}, cm=lambda head, m: m == "mc"
        )
        self.assertEqual([r["branch"] for r in out["merged_pr"]], ["sq"])

    def test_deletion_candidates_exclude_branches_in_live_worktrees(self):
        branches = {"done": "a" * 40, "live": "b" * 40}
        prs = {"done": [pr(1, "MERGED", "a" * 40)], "live": [pr(2, "MERGED", "b" * 40)]}
        out = self.run_triage(branches, prs, checked_out=frozenset({"live"}))
        self.assertEqual([r["branch"] for r in bt.deletion_candidates(out)], ["done"])

    def test_elsewhere_is_only_evaluated_for_branches_without_pr_and_with_commits(self):
        calls = []
        self.run_triage(
            {"a": "a" * 40, "b": "b" * 40},
            {"a": [pr(1, "MERGED", "a" * 40)]},
            ahead={"b": 0},
            elsewhere=lambda h: calls.append(h) or [],
        )
        self.assertEqual(calls, [])

    def test_render_has_counts_and_never_mentions_a_delete_command(self):
        out = self.run_triage({"m": "a" * 40}, {"m": [pr(1, "MERGED", "a" * 40)]})
        text = bt.render(out, "repo")
        self.assertIn("| (أ) مدموجٌ بطلبه | 1 |", text)
        self.assertNotIn("branch -D", text)
        self.assertIn(bs.MERGED, {r["status"] for r in out["merged_pr"]})


if __name__ == "__main__":
    unittest.main()
