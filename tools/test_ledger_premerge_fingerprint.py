"""اختباراتُ ربط بصمة make premerge بنقل الدفتر إلى «جاهزٌ للمعاينة» (W-20261016-021)."""

import os
import unittest

import ledger
from ledger import LedgerError

CARD = {"id": "W-1", "priority": "P1", "type": "ui"}
GOOD = "ab12cd34:0123456789abcdef"


class Fingerprint(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("PREMERGE_GATE_ENFORCE", None)

    def test_other_states_untouched(self):
        self.assertIsNone(ledger.check_premerge_fingerprint(CARD, "in_progress", None))

    def test_docs_type_exempt_by_declared_type(self):
        self.assertIsNone(ledger.check_premerge_fingerprint({**CARD, "type": "docs"}, "ready_for_review", None))

    def test_missing_warns_in_shadow(self):
        os.environ["PREMERGE_GATE_ENFORCE"] = "0"
        self.assertIn("إنذار", ledger.check_premerge_fingerprint(CARD, "ready_for_review", None))

    def test_missing_refuses_by_default(self):  # قرار المالك 2026-10-20: الإلزامُ افتراضيّ
        with self.assertRaises(LedgerError):
            ledger.check_premerge_fingerprint(CARD, "ready_for_review", None)

    def test_p0_only_warns_even_by_default(self):
        self.assertIn("إنذار", ledger.check_premerge_fingerprint({**CARD, "priority": "P0"}, "ready_for_review", None))

    def test_preflight_waiver_covers_repos_without_premerge(self):
        self.assertIn("استثناءُ بصمة premerge", ledger.check_premerge_fingerprint(CARD, "ready_for_review", None, None, "maestro-v2 بلا make premerge"))

    def test_waiver_does_not_excuse_a_wrong_fingerprint(self):
        with self.assertRaises(LedgerError):
            ledger.check_premerge_fingerprint(CARD, "ready_for_review", GOOD, "ffffffff00", "سبب")

    def test_missing_refuses_when_enforced(self):
        os.environ["PREMERGE_GATE_ENFORCE"] = "1"
        with self.assertRaises(LedgerError):
            ledger.check_premerge_fingerprint(CARD, "ready_for_review", None)

    def test_wrong_head_warns_then_refuses(self):
        os.environ["PREMERGE_GATE_ENFORCE"] = "0"
        self.assertIn("رأسٍ مخالف", ledger.check_premerge_fingerprint(CARD, "ready_for_review", GOOD, "ffffffff00"))
        os.environ["PREMERGE_GATE_ENFORCE"] = "1"
        with self.assertRaises(LedgerError):
            ledger.check_premerge_fingerprint(CARD, "ready_for_review", GOOD, "ffffffff00")

    def test_matching_passes_and_is_noted(self):
        os.environ["PREMERGE_GATE_ENFORCE"] = "1"
        self.assertIn(GOOD, ledger.check_premerge_fingerprint(CARD, "ready_for_review", GOOD, "ab12cd34ef"))

    def test_printed_line_format_accepted(self):
        out = ledger.check_premerge_fingerprint(CARD, "ready_for_review", "head=ab12cd34 sha256=0123456789abcdef", "ab12cd34")
        self.assertNotIn("إنذار", out)

    def test_garbage_format_is_flagged(self):
        os.environ["PREMERGE_GATE_ENFORCE"] = "0"
        self.assertIn("غير مفهومة", ledger.check_premerge_fingerprint(CARD, "ready_for_review", "xyz"))


if __name__ == "__main__":
    unittest.main()
