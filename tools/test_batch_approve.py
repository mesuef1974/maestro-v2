"""اختباراتُ الاعتماد الجماعيّ بالرأس:  python -m pytest test_batch_approve.py"""

import unittest

import batch_approve as ba

REP = {
    "included": [{"id": "W-20261015-001", "head": "aaaaaaaa11111111"}, {"id": "W-20261015-002", "head": "bbbbbbbb22222222"}],
    "excluded": [{"id": "W-20261015-003", "why": "يتعارض مع main"}],
}


class Decide(unittest.TestCase):
    def test_named_cards_with_matching_heads_are_accepted(self):
        ok, bad = ba.decide(REP, ["W-20261015-001@aaaaaaaa", "W-20261015-002@bbbbbbbb"])
        self.assertEqual(ok, [("W-20261015-001", "aaaaaaaa"), ("W-20261015-002", "bbbbbbbb")])
        self.assertEqual(bad, [])

    def test_a_changed_head_is_rejected_with_the_current_one(self):
        ok, bad = ba.decide(REP, ["W-20261015-001@cccccccc"])
        self.assertEqual(ok, [])
        self.assertIn("aaaaaaaa", bad[0][1])

    def test_an_excluded_or_unknown_card_is_never_approved(self):
        ok, bad = ba.decide(REP, ["W-20261015-003@aaaaaaaa", "W-20261015-009@aaaaaaaa"])
        self.assertEqual(ok, [])
        self.assertIn("مستبعَدة", bad[0][1])
        self.assertIn("ليست في الدفعة", bad[1][1])

    def test_a_bare_card_without_a_head_is_rejected(self):
        ok, bad = ba.decide(REP, ["W-20261015-001"])
        self.assertEqual((ok, len(bad)), ([], 1))

    def test_one_line_per_card_with_verbatim_quote_and_head(self):
        out = ba.lines([("W-20261015-001", "aaaaaaaa")], "0101", "اعتمد", "نقلاً عن 0101")
        self.assertEqual(len(out), 1)
        self.assertIn("«اعتمد", out[0])
        self.assertIn("W-20261015-001 @aaaaaaaa", out[0])


if __name__ == "__main__":
    unittest.main()
