"""اختباراتُ فرض سياسة waive-head «وثائقُ فقط» (W-20261003-040):  python -m unittest test_ledger_waive -v

الاستثناءُ التافهُ لا يمرّ إن مسّ الفرقُ ملفّاً **حاكماً** (CLAUDE.md، `.claude/**`، `docs/governance/flow.md`)؛ والمساراتُ تُطبَّع (`\\`←`/`، حذفُ `./`،
حروفٌ صغيرة) قبل المطابقة؛ وقائمةُ `changed` الممرَّرةُ لا تُغني عن `git diff` الحقيقيّ — تُؤخذ اتّحاداً معه فلا يتجاوز الفحصَ من يمرّر قائمةً حميدة.
جدولُ الأمثلة من المواصفة docs/w040_waive_head_governing_paths_spec.md.
"""

import unittest
from unittest import mock

import ledger

ITEM = "W-20261003-999"
APPROVED = "a" * 40
NEW = "bbbbbbbb"


def waive(changed, *, git_diff=None, kind="docs", by="0501"):
    """يستدعي waive_head بدفترٍ مزيَّف: `git_diff` ما يردّه `git diff --name-only` الحقيقيُّ (None = تعذّرت القراءة كما في الاختبار)."""
    events = []
    state = {ITEM: {"approved_head": APPROVED, "state": "approved"}}

    def fake_git(cmd):
        if git_diff is None:
            raise ledger.LedgerError("لا مستودع في الاختبار")
        return "\n".join(git_diff)

    with (
        mock.patch.object(ledger, "load_events", return_value=[]),
        mock.patch.object(ledger, "reduce_state", return_value=state),
        mock.patch.object(ledger, "_git_read", side_effect=fake_git),
        mock.patch.object(ledger, "append_event", side_effect=lambda *a, **k: events.append(a)),
    ):
        ledger.waive_head(ITEM, NEW, by, "سببُ الاختبار", changed=changed, kind=kind)
    return events


class AcceptedDocs(unittest.TestCase):
    def test_plain_documents_are_accepted(self):
        for path in (
            "docs/adr/0010-x.md",
            "docs/deployment/session_server.md",
            "README.md",
            "docs/governance/regression_guards.md",
        ):
            with self.subTest(path=path):
                self.assertTrue(waive([path]))  # يُسجَّل حدثان: الحالةُ والملاحظة


class RejectedGoverning(unittest.TestCase):
    def assertRejected(self, changed, **kw):
        with self.assertRaises(ledger.LedgerError) as caught:
            waive(changed, **kw)
        self.assertIn("حاكمة", str(caught.exception))

    def test_root_constitution(self):
        self.assertRejected(["CLAUDE.md"])

    def test_normalisation_dot_slash_and_backslash_and_case(self):
        for path in ("./CLAUDE.md", "Claude.md", "CLAUDE.MD", ".\\CLAUDE.md"):
            with self.subTest(path=path):
                self.assertRejected([path])

    def test_flow_file(self):
        self.assertRejected(["docs/governance/flow.md"])
        self.assertRejected(["DOCS\\Governance\\Flow.md"])

    def test_claude_folder(self):
        self.assertRejected([".claude/rules/dashboards.md"])
        self.assertRejected([".claude/settings.json"])
        self.assertRejected([".claude/hooks/x.sh"])

    def test_nested_constitution(self):
        self.assertRejected(["services/CLAUDE.md"])
        self.assertRejected(["app/sub/claude.md"])

    def test_one_governing_file_is_enough_among_plain_ones(self):
        self.assertRejected(["docs/a.md", "CLAUDE.md"])

    def test_message_lists_the_first_five_governing_files(self):
        files = [f"pkg{i}/CLAUDE.md" for i in range(8)]
        with self.assertRaises(ledger.LedgerError) as caught:
            waive(files)
        text = str(caught.exception)
        self.assertIn("pkg0/CLAUDE.md", text)
        self.assertIn("pkg4/CLAUDE.md", text)
        self.assertNotIn("pkg5/CLAUDE.md", text)

    def test_empty_diff_still_rejected(self):
        with self.assertRaises(ledger.LedgerError):
            waive([])

    def test_non_document_still_rejected(self):
        with self.assertRaises(ledger.LedgerError):
            waive(["core/views.py"])


class PassedListCannotBypassTheRealDiff(unittest.TestCase):
    def test_a_benign_passed_list_does_not_hide_a_governing_file_in_the_real_diff(self):
        with self.assertRaises(ledger.LedgerError) as caught:
            waive(["docs/a.md"], git_diff=["docs/a.md", "CLAUDE.md"])
        self.assertIn("حاكمة", str(caught.exception))

    def test_no_passed_list_reads_the_real_diff(self):
        with self.assertRaises(ledger.LedgerError):
            waive(None, git_diff=["docs/governance/flow.md"])
        self.assertTrue(waive(None, git_diff=["docs/a.md"]))

    def test_a_passed_list_alone_is_still_checked_when_git_is_unavailable(self):
        with self.assertRaises(ledger.LedgerError):
            waive(["CLAUDE.md"], git_diff=None)


class OtherKindsUntouched(unittest.TestCase):
    def test_main_merge_is_not_covered_by_the_governing_filter(self):
        with mock.patch.object(ledger, "check_main_merge", return_value=["CLAUDE.md"]) as check:
            self.assertTrue(waive(["CLAUDE.md"], kind="main-merge"))
        check.assert_called_once()

    def test_tests_only_is_not_covered_by_the_governing_filter(self):
        with mock.patch.object(ledger, "check_tests_only", return_value=None) as check:
            self.assertTrue(waive(["tests/test_x.py"], kind="tests-only"))
        check.assert_called_once()

    def test_only_the_waiver_signer_may_waive(self):
        with self.assertRaises(ledger.LedgerError):
            waive(["docs/a.md"], by="0406")


if __name__ == "__main__":
    unittest.main()


class RenameVisibilityTest(unittest.TestCase):
    """0102: `git diff --name-only` يعرض الاسمَ الجديدَ وحدَه للمُعاد تسميتُه — فنقلُ ملفٍّ حاكمٍ لا يُرى اسمُه القديم؛ لذا يلزم `--no-renames`."""

    def test_docs_diff_uses_no_renames(self):
        calls = []

        def fake(cmd, *a, **k):
            calls.append(cmd)
            return "docs/a.md"

        with mock.patch.object(ledger, "_git_read", side_effect=fake):
            ledger._docs_changed_files(APPROVED, NEW, None)
        self.assertTrue(any("--no-renames" in c for c in calls), calls)
