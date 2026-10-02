"""اختباراتُ بوّابات مراحل البطاقة:  python -m unittest test_ledger_gates -v"""

import unittest

import ledger


class Gates(unittest.TestCase):
    def test_no_push_without_approval(self):
        with self.assertRaises(ledger.LedgerError):
            ledger.check_transition("in_progress", "pushed", None)
        ledger.check_transition("approved", "pushed", None)

    def test_no_merge_without_push_and_no_publish_without_merge(self):
        with self.assertRaises(ledger.LedgerError):
            ledger.check_transition("approved", "merged", None)
        with self.assertRaises(ledger.LedgerError):
            ledger.check_transition("pushed", "published", None)
        ledger.check_transition("pushed", "merged", None)
        ledger.check_transition("merged", "published", None)

    def test_approval_needs_a_note(self):
        with self.assertRaises(ledger.LedgerError):
            ledger.check_transition("ready_for_review", "approved", None)
        ledger.check_transition("captured", "approved", "اعتمادٌ مباشرٌ من المالك 09-29")

    def test_free_states_stay_free(self):
        for st in ("routed", "in_progress", "ready_for_review", "notes", "deferred", "closed"):
            ledger.check_transition("captured", st, None)


if __name__ == "__main__":
    unittest.main()


class TestRecorders(unittest.TestCase):
    def test_duplicate_approval_is_rejected(self):
        from ledger import ALREADY_APPROVED, LedgerError, check_transition
        for cur in ALREADY_APPROVED:
            with self.assertRaises(LedgerError):
                check_transition(cur, "approved", "اعتمد المالك")

    def test_only_allowed_sessions_record_states(self):
        from ledger import LedgerError, check_recorder
        check_recorder("approved", "0501")
        check_recorder("merged", None)  # بلا --by: انتقالٌ لطيف
        with self.assertRaises(LedgerError):
            check_recorder("approved", "0408")
        with self.assertRaises(LedgerError):
            check_recorder("merged", "0404")
