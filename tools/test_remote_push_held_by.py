"""اختباراتُ فحص البعيد لـpushed وحقل held_by وتحذير my_state — بلا شبكة:  python -m unittest test_remote_push_held_by"""

import os
import tempfile
import unittest

import ledger
import my_state


def fresh():
    path = os.path.join(tempfile.mkdtemp(), "e.jsonl")
    cid = ledger.add_item("owner", "tool", "م", "أ", "ق", start="2026-10-04T08:00", priority="P2", path=path)
    ledger.move(cid, "approved", path=path, note="اعتمد المالك على 8500", head="abcdef12", by="0501", waive_spec="اختبارُ الدفع لا المواصفة")
    return path, cid


class RemoteCheck(unittest.TestCase):
    def test_rejects_when_branch_missing(self):
        path, cid = fresh()
        with self.assertRaises(ledger.LedgerError):
            ledger.move(cid, "pushed", path=path, branch="claude/x", remote_lookup=lambda b: None)
        self.assertEqual(ledger.reduce_state(ledger.load_events(path))[cid]["state"], "approved")

    def test_rejects_without_branch(self):
        path, cid = fresh()
        with self.assertRaises(ledger.LedgerError):
            ledger.move(cid, "pushed", path=path, remote_lookup=lambda b: "abcdef12")

    def test_rejects_head_mismatch(self):
        path, cid = fresh()
        with self.assertRaises(ledger.LedgerError):
            ledger.move(cid, "pushed", path=path, branch="b", head="11111111", remote_lookup=lambda b: "abcdef1234")

    def test_accepts_and_records_branch(self):
        path, cid = fresh()
        ledger.move(cid, "pushed", path=path, branch="b", head="abcdef12", remote_lookup=lambda b: "abcdef1234")
        it = ledger.reduce_state(ledger.load_events(path))[cid]
        self.assertEqual((it["state"], it["branch"]), ("pushed", "b"))

    def test_waiver_is_noted(self):
        path, cid = fresh()
        ledger.move(cid, "pushed", path=path, waive_remote_check="الشبكة مقطوعة", remote_lookup=lambda b: None)
        it = ledger.reduce_state(ledger.load_events(path))[cid]
        self.assertEqual(it["state"], "pushed")
        self.assertIn("استثناءُ فحص البعيد", it["notes"][-1]["text"])


class HeldBy(unittest.TestCase):
    def setUp(self):
        # الاختبارُ للحامل لا للمواصفة: نُعطّل تشديدَ البطاقات الجديدة (W-20261016-012)
        self.addCleanup(setattr, ledger, "SPEC_STRICT_FROM", ledger.SPEC_STRICT_FROM)
        ledger.SPEC_STRICT_FROM = "2999-01-01"

    def test_add_set_and_clear(self):
        path = os.path.join(tempfile.mkdtemp(), "e.jsonl")
        cid = ledger.add_item("owner", "tool", "م", "أ", "ق", start="2026-10-04T08:00", priority="P2", path=path, held_by="0402")

        def get():
            return ledger.reduce_state(ledger.load_events(path))[cid]

        self.assertEqual(get()["held_by"], "0402")
        ledger.move(cid, "in_progress", path=path, held_by="0405")
        self.assertEqual(get()["held_by"], "0405")
        ledger.move(cid, "notes", path=path, held_by="-")
        self.assertEqual(get()["held_by"], "")

    def test_terminal_states_release(self):
        for st in ("closed", "deferred"):
            path = os.path.join(tempfile.mkdtemp(), "e.jsonl")
            cid = ledger.add_item("owner", "tool", "م", "أ", "ق", start="2026-10-04T08:00", priority="P2", path=path, held_by="0402")
            ledger.move(cid, st, path=path)
            self.assertEqual(ledger.reduce_state(ledger.load_events(path))[cid]["held_by"], "")

    def test_bad_session_rejected_and_old_events_ok(self):
        with self.assertRaises(ledger.LedgerError):
            ledger.check_session("abc")
        old = [{"ts": "2026-10-01T08:00:00+03:00", "id": "W-1", "kind": "created", "data": {"problem": "x"}}]
        self.assertNotIn("held_by", ledger.reduce_state(old)["W-1"])


class MyStateWarning(unittest.TestCase):
    EVENTS = [
        {"ts": "2026-10-01T08:00:00+03:00", "id": "W-1", "kind": "created",
         "data": {"problem": "م", "priority": "P2", "start": "2026-10-01T09:00+03:00", "held_by": "0402"}},
        {"ts": "2026-10-01T10:00:00+03:00", "id": "W-1", "kind": "state", "data": {"state": "pushed", "by": "0402", "branch": "b1"}},
    ]

    def test_warning_listed_when_remote_missing(self):
        out = my_state.report("0402", self.EVENTS, remote_lookup=lambda b: None)
        self.assertTrue(out.startswith("!! تحذير: بطاقات pushed بلا فرع بعيد"))
        self.assertIn("W-1", out.splitlines()[0])
        self.assertIn("محجوزةٌ باسمكِ", out)

    def test_held_cards_show_their_state_one_per_line(self):
        out = my_state.report("0402", self.EVENTS)
        self.assertIn("W-1 [pushed] P2 م", out)

    def test_no_warning_by_default_or_when_present(self):
        self.assertNotIn("تحذير", my_state.report("0402", self.EVENTS))
        self.assertNotIn("تحذير", my_state.report("0402", self.EVENTS, remote_lookup=lambda b: "abc"))


if __name__ == "__main__":
    unittest.main()
