"""اختباراتُ my_state — unittest بلا اعتمادٍ خارجيّ:  python -m unittest test_my_state"""

import unittest
from datetime import datetime

import ledger
import my_state

NOW = datetime.fromisoformat("2026-10-03T12:00:00+03:00")


def created(card, ts="2026-10-01T08:00:00+03:00", start="2026-10-01T09:00+03:00"):
    return {"ts": ts, "id": card, "kind": "created", "data": {"problem": f"مشكلة {card}", "priority": "P2", "start": start}}


def state(card, value, ts, by="0101", head=None):
    data = {"state": value, "by": by}
    if head:
        data["head"] = head
    return {"ts": ts, "id": card, "kind": "state", "data": data}


def note(card, text, ts):
    return {"ts": ts, "id": card, "kind": "note", "data": {"text": text}}


class Owner(unittest.TestCase):
    def test_owner_from_a_note_prefix(self):
        events = [created("W-1"), note("W-1", "0403: 4c163edc على الفرع", "2026-10-01T10:00:00+03:00")]
        self.assertEqual(my_state.infer_owners(events), {"W-1": "0403"})

    def test_coordinators_never_own(self):
        events = [
            created("W-1"),
            state("W-1", "approved", "2026-10-01T10:00:00+03:00", by="0501"),
            state("W-1", "merged", "2026-10-01T11:00:00+03:00", by="0601"),
        ]
        self.assertEqual(my_state.infer_owners(events), {})

    def test_owner_from_a_working_session_state_by(self):
        events = [created("W-1"), state("W-1", "in_progress", "2026-10-01T10:00:00+03:00", by="0402")]
        self.assertEqual(my_state.infer_owners(events), {"W-1": "0402"})

    def test_the_latest_working_session_wins(self):
        events = [
            created("W-1"),
            note("W-1", "0403: بدأتُ", "2026-10-01T10:00:00+03:00"),
            note("W-1", "0414: أكملتُها بقرار المالك", "2026-10-02T10:00:00+03:00"),
        ]
        self.assertEqual(my_state.infer_owners(events), {"W-1": "0414"})

    def test_a_session_named_mid_sentence_is_not_an_owner(self):
        events = [created("W-1"), note("W-1", "اعتمد المالك في محادثة 0403", "2026-10-01T10:00:00+03:00")]
        self.assertEqual(my_state.infer_owners(events), {})


class Actions(unittest.TestCase):
    def owned(self, *more):
        return [created("W-1"), note("W-1", "0403: بدأتُ", "2026-10-01T10:00:00+03:00"), *more]

    def action(self, events):
        items = ledger.reduce_state(events)
        late = {i["id"] for i in ledger.late_items(items, now=NOW)}
        return my_state.classify(items["W-1"], events, late)

    def test_merged_without_a_roadmap_note_asks_for_0701(self):
        events = self.owned(state("W-1", "merged", "2026-10-02T10:00:00+03:00", by="0601"))
        self.assertEqual(self.action(events), "roadmap")

    def test_a_roadmap_note_after_the_merge_clears_it(self):
        events = self.owned(
            state("W-1", "merged", "2026-10-02T10:00:00+03:00", by="0601"),
            note("W-1", "أُبلغت 0701 برقم الطلب", "2026-10-02T10:05:00+03:00"),
        )
        self.assertIsNone(self.action(events))

    def test_a_roadmap_note_before_the_merge_does_not_count(self):
        events = self.owned(
            note("W-1", "سيُحدَّث في الخارطة لاحقاً", "2026-10-02T09:00:00+03:00"),
            state("W-1", "merged", "2026-10-02T10:00:00+03:00", by="0601"),
        )
        self.assertEqual(self.action(events), "roadmap")

    def test_approved_means_push_with_its_head(self):
        events = self.owned(state("W-1", "approved", "2026-10-02T10:00:00+03:00", by="0501", head="4c163edc"))
        self.assertEqual(self.action(events), "push")
        item = ledger.reduce_state(events)["W-1"]
        self.assertIn("4c163edc", my_state.describe(item))

    def test_review_and_pushed_wait_for_others(self):
        for value in ("ready_for_review", "pushed"):
            events = self.owned(state("W-1", value, "2026-10-02T10:00:00+03:00"))
            self.assertEqual(self.action(events), "waiting", value)

    def test_owner_notes_are_work_now(self):
        events = self.owned(state("W-1", "notes", "2026-10-02T10:00:00+03:00", by="0501"))
        self.assertEqual(self.action(events), "now")

    def test_a_routed_card_past_its_start_is_late(self):
        events = self.owned(state("W-1", "routed", "2026-10-01T09:30:00+03:00"))
        self.assertEqual(self.action(events), "late")

    def test_published_is_finished(self):
        events = self.owned(state("W-1", "published", "2026-10-02T10:00:00+03:00", by="0601"))
        self.assertIsNone(self.action(events))


class Report(unittest.TestCase):
    def test_only_the_sessions_cards_are_listed_and_marked_inferred(self):
        events = [
            created("W-1"),
            note("W-1", "0403: بدأتُ", "2026-10-01T10:00:00+03:00"),
            state("W-1", "merged", "2026-10-02T10:00:00+03:00", by="0601"),
            created("W-2"),
            note("W-2", "0402: لي", "2026-10-01T10:00:00+03:00"),
            state("W-2", "in_progress", "2026-10-01T11:00:00+03:00", by="0402"),
        ]
        text = my_state.report("0403", events, now=NOW)
        self.assertIn("W-1", text)
        self.assertNotIn("W-2", text)
        self.assertIn("أبلغي 0701", text)
        self.assertIn("(مستنتَج)", text)

    def test_finished_cards_appear_only_with_all(self):
        events = [
            created("W-1"),
            note("W-1", "0403: بدأتُ", "2026-10-01T10:00:00+03:00"),
            state("W-1", "published", "2026-10-02T10:00:00+03:00", by="0601"),
        ]
        self.assertNotIn("W-1", my_state.report("0403", events, now=NOW))
        self.assertIn("W-1", my_state.report("0403", events, show_all=True, now=NOW))


if __name__ == "__main__":
    unittest.main()
