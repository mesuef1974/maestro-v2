"""اختباراتُ بوّابات مراحل البطاقة:  python -m unittest test_ledger_gates -v"""

import unittest

import ledger


class Gates(unittest.TestCase):
    def test_add_note_appends_note_only_and_validates(self):
        got = []
        orig = (ledger.load_events, ledger.append_event, ledger.reduce_state)
        ledger.load_events = lambda path=None: []
        ledger.reduce_state = lambda ev: {"W-1": {"state": "ready_for_review"}}
        ledger.append_event = lambda kind, i, data, path=None: got.append((kind, i, data))
        try:
            ledger.add_note("W-1", "حزمة الأدلة evidence/W-1/abcd1234/pack.md", "0502")
            self.assertEqual([g[0] for g in got], ["note"])
            with self.assertRaises(ledger.LedgerError):
                ledger.add_note("W-9", "x", "0502")
            with self.assertRaises(ledger.LedgerError):
                ledger.add_note("W-1", "  ", "0502")
        finally:
            ledger.load_events, ledger.append_event, ledger.reduce_state = orig

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
        with self.assertRaises(LedgerError):  # H1: بلا --by يُرفض
            check_recorder("merged", None)
        with self.assertRaises(LedgerError):
            check_recorder("approved", "0405")
        with self.assertRaises(LedgerError):
            check_recorder("merged", "0403")


class TestHolderOnRoute(unittest.TestCase):
    """D-293م: held_by إلزاميٌّ عند التوجيه (W-20261009-015)."""

    def test_route_without_holder_is_rejected(self):
        from ledger import LedgerError, check_holder_on_route
        with self.assertRaises(LedgerError):
            check_holder_on_route({"state": "verified"}, "routed", None)
        with self.assertRaises(LedgerError):
            check_holder_on_route({"state": "verified", "held_by": ""}, "routed", None)

    def test_route_with_param_or_previous_holder_passes(self):
        from ledger import check_holder_on_route
        check_holder_on_route({"state": "verified"}, "routed", "0403")
        check_holder_on_route({"state": "verified", "held_by": "0403"}, "routed", None)

    def test_release_dash_on_route_is_rejected_even_with_previous_holder(self):
        from ledger import LedgerError, check_holder_on_route
        with self.assertRaises(LedgerError):
            check_holder_on_route({"state": "verified", "held_by": "0403"}, "routed", "-")

    def test_other_states_unaffected(self):
        from ledger import check_holder_on_route
        for st in ("in_progress", "ready_for_review", "notes", "closed"):
            check_holder_on_route({"state": "routed"}, st, None)
            check_holder_on_route({"state": "routed"}, st, "-")
