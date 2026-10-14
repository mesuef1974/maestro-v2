"""اختباراتُ ledger_stale — unittest بلا اعتمادٍ خارجيّ:  python -m unittest test_ledger_stale"""

import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ledger
import ledger_stale as ls

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone(timedelta(hours=3)))


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat()


def made(item, days_ago, problem="مشكلةٌ ما", state=None, by=None, notes=()):
    evs = [{"ts": iso(days_ago), "id": item, "kind": "created", "data": {"problem": problem}}]
    if state:
        data = {"state": state}
        if by:
            data["held_by"] = by
        evs.append({"ts": iso(days_ago), "id": item, "kind": "state", "data": data})
    for d, text in notes:
        evs.append({"ts": iso(d), "id": item, "kind": "note", "data": {"text": text}})
    return evs


def ids(rows):
    return {r["id"] for r in rows}


class Stale(unittest.TestCase):
    def test_the_seven_day_boundary(self):
        evs = made("A", 7.5, state="routed") + made("B", 6.5, state="routed") + made("C", 7.5)
        rep = ls.collect(evs, NOW)
        self.assertEqual(ids(rep["stale"]), {"A", "C"})

    def test_only_routed_and_captured_count(self):
        evs = made("A", 30, state="routed") + made("B", 30, state="published") + made("C", 30, state="deferred")
        self.assertEqual(ids(ls.collect(evs, NOW)["stale"]), {"A"})

    def test_a_recent_note_moves_the_card_to_active_work(self):
        evs = made("A", 20, state="routed", notes=[(1, "قيد العمل")]) + made("B", 20, state="routed", notes=[(10, "قديمة")])
        rep = ls.collect(evs, NOW)
        self.assertEqual(ids(rep["active"]), {"A"})
        self.assertEqual(ids(rep["stale"]), {"B"})

    def test_red_line_card_is_marked_exempt(self):
        evs = made("A", 20, problem="تعديل الجدول المعتمد الحيّ", state="routed")
        self.assertIn("خطٌّ أحمر", ls.collect(evs, NOW)["stale"][0]["fate"])

    def test_deferred_with_decision_vs_without(self):
        with_dec = made("A", 20, state="routed", notes=[(15, "أُجّل بقرار D-178م")])
        without = made("B", 20, problem="مشكلةٌ أخرى", state="routed", notes=[(15, "تأجيلٌ")])
        rep = ls.collect(with_dec + without, NOW)
        fates = {r["id"]: r["fate"] for r in rep["stale"]}
        self.assertEqual(fates["A"], "مؤجَّل بقرار")
        self.assertIn("بلا قرارٍ", fates["B"])

    def test_duplicate_problem_text_is_flagged_but_not_closed(self):
        evs = made("A", 20, problem="نفسُ النص تماماً", state="routed") + made("B", 20, problem="نفسُ النص تماماً", state="routed")
        rows = ls.collect(evs, NOW)["stale"]
        self.assertTrue(all("مكرَّر" in r["fate"] for r in rows))

    def test_holder_means_follow_the_executor(self):
        evs = made("A", 20, state="routed", by="0702")
        self.assertEqual(ls.collect(evs, NOW)["stale"][0]["fate"], "متابعة المنفّذ")

    def test_proof_accompanies_every_fate(self):
        evs = made("A", 20, state="routed") + made("B", 20, problem="س")
        self.assertTrue(all(r["proof"] for r in ls.collect(evs, NOW)["stale"]))

    def test_the_tool_is_read_only_and_does_not_touch_the_ledger(self):
        import os
        import tempfile

        tmp = Path(tempfile.mkdtemp()) / "events.jsonl"
        tmp.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in made("A", 20, state="routed")), encoding="utf-8")
        path = tmp
        os.environ["LEDGER_PATH"] = str(tmp)
        self.addCleanup(os.environ.pop, "LEDGER_PATH", None)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        rep = ls.collect(ledger.load_events(), datetime.now(ledger.DOHA))
        ls.render_text(rep, 7)
        ls.render_html(rep, 7)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
        src = Path(ls.__file__).read_text(encoding="utf-8")
        self.assertNotIn("append_event", src)
        self.assertNotIn("sendmessage", src.lower())

    def test_json_output_is_serializable(self):
        json.dumps(ls.collect(made("A", 20, state="routed"), NOW), ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
