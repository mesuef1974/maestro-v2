"""اختباراتُ W-20261022-008: لا انتقالَ إلى «جاهزٌ للمعاينة» بلا رأسٍ معلَن (يبقى ready_head فارغاً فتتوقّف البطاقة)."""

import inspect
import unittest

import ledger

CARD = {"id": "W-1", "priority": "P1", "type": "ui"}


class ReadyHead(unittest.TestCase):
    def test_other_states_untouched(self):
        self.assertIsNone(ledger.check_ready_head(CARD, "in_progress", None))

    def test_missing_head_is_refused_with_pointer_to_ready_mark(self):
        msg = ledger.check_ready_head(CARD, "ready_for_review", None)
        self.assertIn("ready_mark", msg)

    def test_malformed_head_is_refused(self):
        self.assertIsNotNone(ledger.check_ready_head(CARD, "ready_for_review", "zz"))

    def test_valid_head_passes(self):
        self.assertIsNone(ledger.check_ready_head(CARD, "ready_for_review", "ab12cd34"))

    def test_docs_type_exempt(self):
        self.assertIsNone(ledger.check_ready_head({**CARD, "type": "docs"}, "ready_for_review", None))


class Wiring(unittest.TestCase):
    def test_move_calls_the_gate_before_writing(self):
        text = inspect.getsource(ledger)  # من المصدر لا من الدالة: اختباراتٌ أخرى تلفّ ledger.move بغلاف
        start = text.index("\ndef move(")
        src = text[start : text.index("\ndef ", start + 1)]
        self.assertIn("check_ready_head(", src)
        self.assertLess(src.index("check_ready_head("), src.index('append_event("state"'))


if __name__ == "__main__":
    unittest.main()
