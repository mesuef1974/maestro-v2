"""اختباراتُ بوّابة الفحص المسبق قبل «جاهزٌ للمعاينة» (W-20261014-022)."""

import os
import unittest

import ledger
from ledger import LedgerError

CARD = {"id": "W-1", "priority": "P1"}


class Gate(unittest.TestCase):
    def test_other_states_untouched(self):
        self.assertIsNone(ledger.check_preflight_ready(CARD, "in_progress", None, None))

    def test_p0_exempt(self):
        self.assertIsNone(ledger.check_preflight_ready({"id": "W-1", "priority": "P0"}, "ready_for_review", None, None))

    def test_missing_repo_warns_by_default(self):
        self.assertIn("لم يُشغَّل الفحصُ المسبق", ledger.check_preflight_ready(CARD, "ready_for_review", None, None))

    def test_missing_repo_refuses_when_enforced(self):
        os.environ["PREFLIGHT_ENFORCE"] = "1"
        try:
            with self.assertRaises(LedgerError):
                ledger.check_preflight_ready(CARD, "ready_for_review", None, None)
        finally:
            del os.environ["PREFLIGHT_ENFORCE"]

    def test_failure_refuses_with_output(self):
        with self.assertRaises(LedgerError) as cm:
            ledger.check_preflight_ready(CARD, "ready_for_review", "D:/x", None, runner=lambda c, r: (6, "✘ أساسٌ غير مدفوع"))
        self.assertIn("أساسٌ غير مدفوع", str(cm.exception))

    def test_pass_is_silent(self):
        self.assertIn("إنذار (الظلّ)", ledger.check_preflight_ready(CARD, "ready_for_review", "D:/x", None, runner=lambda c, r: (0, "ok")))  # الإيصال غائب في المسار الوهميّ (W-20261017-014)

    def test_waiver_is_recorded_without_running(self):
        def boom(c, r):
            raise AssertionError("لا يجوز التشغيل مع الاستثناء")
        self.assertIn("سبب", ledger.check_preflight_ready(CARD, "ready_for_review", "D:/x", "سبب", runner=boom))


if __name__ == "__main__":
    unittest.main()
