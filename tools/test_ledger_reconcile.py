"""اختبار ledger_reconcile بدفترٍ وطلباتٍ وهميّة (W-20261016-022)."""

import unittest
from unittest import mock

import ledger
import ledger_reconcile as lr


def item(state):
    return {"state": state}


def pr(n, state="MERGED", title="", branch="", body=""):
    return {
        "number": n,
        "state": state,
        "title": title,
        "headRefName": branch,
        "body": body,
    }


class ReconcileTest(unittest.TestCase):
    def test_merged_pr_by_title_suggests_merged_with_evidence(self):
        out = lr.reconcile(
            {"W-20261014-019": item("pushed")}, [pr(1071, title="fix (W-20261014-019)")]
        )
        s = out["suggestions"][0]
        self.assertEqual(
            (s["card"], s["from"], s["to"], s["pr"]),
            ("W-20261014-019", "pushed", "merged", 1071),
        )
        self.assertIn("#1071", s["evidence"])

    def test_branch_code_matches(self):
        out = lr.reconcile(
            {"W-20261016-015": item("approved")},
            [pr(7, "OPEN", branch="claude/w20261016-015-flow-copies")],
        )
        self.assertEqual(out["suggestions"][0]["to"], "pushed")

    def test_incidental_body_mention_does_not_match_913(self):
        body = "بطاقة الدفتر: W-20261009-003.\nتسوية الـ132 المعلّقة W-20261008-020 مستقلّة عنه."
        items = {"W-20261009-003": item("pushed"), "W-20261008-020": item("pushed")}
        out = lr.reconcile(
            items, [pr(913, title="حذف الشبكة (W-20261009-003)", body=body)]
        )
        self.assertEqual([s["card"] for s in out["suggestions"]], ["W-20261009-003"])

    def test_940_other_card_in_body_does_not_match(self):
        body = (
            "## اختبار (W-20261008-021)\nيحلّ محلّ W-20261001-001 ولا يمسّ W-20261002-002"
        )
        items = {"W-20261001-001": item("approved"), "W-20261002-002": item("approved")}
        self.assertEqual(
            lr.reconcile(items, [pr(940, branch="claude/0702-clock", body=body)])[
                "suggestions"
            ],
            [],
        )

    def test_no_evidence_no_suggestion(self):
        out = lr.reconcile(
            {"W-20261016-001": item("approved")}, [pr(5, title="شيء آخر")]
        )
        self.assertEqual(out["suggestions"], [])

    def test_never_moves_backwards_or_to_published(self):
        out = lr.reconcile(
            {"W-20261016-001": item("published")}, [pr(5, title="(W-20261016-001)")]
        )
        self.assertEqual(out["suggestions"], [])

    def test_ledger_ahead_of_github_is_flagged(self):
        out = lr.reconcile(
            {"W-20261014-019": item("published")},
            [pr(9, "OPEN", title="(W-20261014-019)")],
        )
        self.assertEqual(out["ahead"][0]["card"], "W-20261014-019")

    def test_published_without_any_pr_is_not_flagged(self):
        self.assertEqual(
            lr.reconcile({"W-20261016-001": item("published")}, [])["ahead"], []
        )

    def test_merged_card_is_unconfirmed_for_published(self):
        out = lr.reconcile({"W-20261016-001": item("merged")}, [])
        self.assertEqual(out["unconfirmed"][0]["card"], "W-20261016-001")

    def test_gh_missing_prints_unmeasured_and_does_not_write(self):
        with (
            mock.patch.object(lr, "fetch_prs", return_value=None),
            mock.patch.object(ledger, "append_event") as w,
            mock.patch("sys.argv", ["x"]),
            mock.patch("builtins.print") as pr_,
        ):
            self.assertEqual(lr.main(), 0)
        w.assert_not_called()
        self.assertIn("غير مقيس", pr_.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
