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


class PublishedAndBranchTest(unittest.TestCase):
    def test_merged_card_becomes_published_when_deploy_contains_head(self):
        out = lr.reconcile(
            {"W-20261016-001": item("merged")},
            [pr(5, title="(W-20261016-001)")],
            published=lambda p: (True, "رأس الدمج abc محتوًى في آخر نشر"),
        )
        s = out["suggestions"][0]
        self.assertEqual((s["from"], s["to"]), ("merged", "published"))
        self.assertEqual(out["unconfirmed"], [])

    def test_published_false_or_unmeasured_stays_unconfirmed(self):
        for verdict in (False, None):
            out = lr.reconcile(
                {"W-20261016-001": item("merged")},
                [pr(5, title="(W-20261016-001)")],
                published=lambda p, v=verdict: (v, "x"),
            )
            self.assertEqual(out["suggestions"], [])
            self.assertEqual(out["unconfirmed"][0]["card"], "W-20261016-001")

    def test_branch_on_origin_suggests_pushed(self):
        out = lr.reconcile(
            {"W-20261016-015": item("in_progress"), "W-20261016-016": item("approved"), "W-20261016-017": item("pushed")},
            [],
            branches=["claude/w20261016-015-x", "claude/w20261016-016-y", "claude/w20261016-017-z"],
        )
        cards = {s["card"]: s["to"] for s in out["suggestions"]}
        self.assertEqual(cards, {"W-20261016-015": "pushed", "W-20261016-016": "pushed"})

    def test_approved_is_never_a_target(self):
        out = lr.reconcile(
            {"W-20261016-001": item("ready_for_review")}, [pr(5, "OPEN", title="(W-20261016-001)")]
        )
        self.assertNotIn("approved", [s["to"] for s in out["suggestions"]])

    def test_report_writes_files_but_not_ledger(self):
        import tempfile
        from pathlib import Path

        res = {"suggestions": [], "ahead": [], "unconfirmed": [], "unmeasured": ["branches"]}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ledger, "append_event") as w:
            day = lr.write_report(res, Path(d))
            self.assertTrue((Path(d) / "ledger" / "reconcile_latest.json").is_file())
            self.assertIn("غير مقيس", day.read_text(encoding="utf-8"))
        w.assert_not_called()


if __name__ == "__main__":
    unittest.main()
