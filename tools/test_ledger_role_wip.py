"""اختباراتُ إنذار العمل الجاري لكل دور (W-20261014-011): تحذيرٌ لا رفض، P0 معفى، والنشرُ والتسليمُ يخرجان من العدّ."""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

import ledger
import my_state
from ledger import LedgerError


def card(cid, state, held_by, priority="P1"):
    return {"id": cid, "state": state, "held_by": held_by, "priority": priority, "state_ts": cid}


def items_of(*cards):
    return {c["id"]: c for c in cards}


THREE = [card("A", "in_progress", "0401"), card("B", "ready_for_review", "0402"), card("C", "approved", "0403")]


class RoleOf(unittest.TestCase):
    def test_flex_sessions_share_a_role_others_are_alone(self):
        self.assertEqual(ledger.role_of("0417"), "04")
        self.assertEqual(ledger.role_of("0501"), "0501")
        self.assertNotEqual(ledger.role_of("0101"), ledger.role_of("0102"))


class Check(unittest.TestCase):
    def test_under_limit_no_warning(self):
        items = items_of(*THREE[:2], card("N", "routed", "0404"))
        self.assertIsNone(ledger.check_role_wip(items, "N", "0404"))

    def test_over_limit_warns_with_pending_cards(self):
        items = items_of(*THREE, card("N", "routed", "0404"))
        msg = ledger.check_role_wip(items, "N", "0404")
        self.assertIn("A [in_progress]", msg)
        self.assertIn("C [approved]", msg)
        self.assertIn("الحدّ 3", msg)

    def test_p0_is_exempt(self):
        items = items_of(*THREE, card("N", "routed", "0404", "P0"))
        self.assertIsNone(ledger.check_role_wip(items, "N", "0404"))

    def test_published_and_handed_over_leave_the_count(self):
        items = items_of(card("A", "published", "0401"), card("B", "ready_for_review", "0501"), card("C", "approved", "0403"),
                         card("N", "routed", "0404"))
        self.assertIsNone(ledger.check_role_wip(items, "N", "0404"))

    def test_other_roles_are_not_counted(self):
        items = items_of(*THREE, card("N", "routed", "0501"))
        self.assertIsNone(ledger.check_role_wip(items, "N", "0501"))

    def test_enforce_switch_turns_warning_into_refusal(self):
        items = items_of(*THREE, card("N", "routed", "0404"))
        os.environ["ROLE_WIP_ENFORCE"] = "1"
        try:
            with self.assertRaises(LedgerError):
                ledger.check_role_wip(items, "N", "0404")
        finally:
            del os.environ["ROLE_WIP_ENFORCE"]

    def test_limit_is_configurable(self):
        items = items_of(THREE[0], card("N", "routed", "0404"))
        os.environ["ROLE_WIP_LIMIT"] = "1"
        try:
            self.assertIsNotNone(ledger.check_role_wip(items, "N", "0404"))
        finally:
            del os.environ["ROLE_WIP_LIMIT"]


class MoveDoesNotRefuse(unittest.TestCase):
    def test_fourth_card_starts_with_warning_and_note(self):
        p = Path(tempfile.mkdtemp()) / "events.jsonl"
        ids = []
        for n in range(4):
            cid = f"W-R-{n}"
            ledger.append_event("created", cid, {"priority": "P1", "type": "ui", "problem": "p"}, p)
            ids.append(cid)
        for cid, sess in zip(ids[:3], ("0401", "0402", "0403")):
            ledger.move(cid, "in_progress", p, by=sess, held_by=sess, waive_spec="اختبار", waive_wip="اختبار")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            ledger.move(ids[3], "in_progress", p, by="0404", held_by="0404", waive_spec="اختبار")
        self.assertIn("إنذار العمل الجاري", err.getvalue())
        events = ledger.reduce_state(ledger.load_events(p))
        self.assertEqual(events[ids[3]]["state"], "in_progress")
        notes = [e["data"]["text"] for e in ledger.load_events(p) if e["id"] == ids[3] and e["kind"] == "note"]
        self.assertTrue(any("إنذار العمل الجاري" in n for n in notes))


class MyState(unittest.TestCase):
    def test_line_only_when_over_limit(self):
        items = items_of(*THREE)
        self.assertIsNone(my_state.role_wip_line(items, "0404"))
        items = items_of(*THREE, card("D", "pushed", "0404"))
        self.assertIn("للدور 04 4 بطاقاتٍ", my_state.role_wip_line(items, "0404"))


if __name__ == "__main__":
    unittest.main()
