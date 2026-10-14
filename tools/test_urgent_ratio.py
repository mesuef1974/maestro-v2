"""اختباراتُ urgent_ratio — unittest بلا اعتمادٍ خارجيّ:  python -m unittest test_urgent_ratio"""

import hashlib
import unittest
from pathlib import Path
from unittest import mock

import ledger
import urgent_ratio as ur


def card(item, urgent=False, state="published", owner_order="", notes=()):
    data = {"problem": "م", "urgent": urgent}
    if owner_order:
        data["owner_order"] = owner_order
    evs = [{"ts": "2026-10-01T10:00:00+03:00", "id": item, "kind": "created", "data": data},
           {"ts": "2026-10-02T10:00:00+03:00", "id": item, "kind": "state", "data": {"state": state}}]
    evs += [{"ts": "2026-10-02T11:00:00+03:00", "id": item, "kind": "note", "data": {"text": t}} for t in notes]
    return evs


class Ratio(unittest.TestCase):
    def test_ratio_counts_urgent_cards(self):
        rep = ur.card_ratio(card("A", True) + card("B") + card("C") + card("D"))
        self.assertEqual((rep["urgent"], rep["all_cards"], rep["published"]), (1, 4, 4))
        self.assertEqual(rep["ratio_of_all"], 0.25)

    def test_urgent_without_reason_is_counted(self):
        rep = ur.card_ratio(card("A", True) + card("B", True, owner_order="«أمر المالك»"))
        self.assertEqual(rep["without_reason"], 1)
        row = {r["id"]: r for r in rep["rows"]}
        self.assertEqual(row["A"]["reason"], "بلا سبب")
        self.assertEqual(row["B"]["source"], "أمر المالك")

    def test_a_note_citing_a_decision_counts_as_reason(self):
        rep = ur.card_ratio(card("A", True, notes=["عاجل بقرار D-433م"]))
        self.assertEqual(rep["without_reason"], 0)

    def test_missing_gh_does_not_break_the_output(self):
        with mock.patch("urgent_ratio.subprocess.run", side_effect=OSError):
            self.assertIsNone(ur.gh_merged(10))
        rep = {"cards": ur.card_ratio(card("A", True)), "prs": ur.pr_ratio(None)}
        self.assertIn("غير مقيسة", ur.render(rep))

    def test_pr_ratio_reads_the_label(self):
        prs = [{"number": 1, "labels": [{"name": "نشر-عاجل"}]}, {"number": 2, "labels": []}, {"number": 3, "labels": [{"name": "x"}]}]
        rep = ur.pr_ratio(prs)
        self.assertEqual((rep["urgent"], rep["merged"], rep["urgent_numbers"]), (1, 3, [1]))

    def test_it_never_blocks_or_rejects_and_never_writes(self):
        path = Path(ledger.ledger_path())
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        ur.card_ratio(ledger.load_events())
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
        src = Path(ur.__file__).read_text(encoding="utf-8")
        for forbidden in ("append_event", "sys.exit(1)", "raise SystemExit(1)"):
            self.assertNotIn(forbidden, src)


if __name__ == "__main__":
    unittest.main()
