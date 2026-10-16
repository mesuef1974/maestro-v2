"""اختباراتُ session_scorecard بدفترٍ مصطنع."""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import session_scorecard as sc  # noqa: E402

NOW = datetime(2026, 10, 16, 18, 0, tzinfo=timezone(timedelta(hours=3)))


def ts(minutes_ago: int) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat()


def created(i, mins):
    return {"ts": ts(mins), "kind": "created", "id": i, "data": {"problem": "x"}}


def state(i, mins, st, by, held=None, head=None):
    d = {"state": st, "by": by}
    if held is not None:
        d["held_by"] = held
    if head:
        d["head"] = head
    return {"ts": ts(mins), "kind": "state", "id": i, "data": d}


class ScorecardTest(unittest.TestCase):
    def rows(self, events, root=Path("/nonexistent")):
        return {r["session"]: r for r in sc.score(events, NOW, root)}

    def test_compliant(self):
        ev = [
            created("A", 300),
            state("A", 20, "ready_for_review", "0401", "0401"),
            {"ts": ts(5), "kind": "note", "id": "A", "data": {"text": "(0401) تقدّم"}},
        ]
        self.assertEqual(self.rows(ev)["0401"]["verdict"], sc.OK)

    def test_overdue_watch_and_severe_account(self):
        ev = [
            created("A", 400),
            state("A", 90, "ready_for_review", "0401", "0401"),
            {"ts": ts(2), "kind": "note", "id": "A", "data": {"text": "(0401) ح"}},
        ]
        self.assertEqual(self.rows(ev)["0401"]["verdict"], sc.WATCH)
        ev2 = [
            created("A", 400),
            state("A", 150, "ready_for_review", "0401", "0401"),
            {"ts": ts(2), "kind": "note", "id": "A", "data": {"text": "(0401) ح"}},
        ]
        self.assertEqual(self.rows(ev2)["0401"]["verdict"], sc.ACCOUNT)

    def test_pushed_without_ready_flagged(self):
        ev = [
            created("A", 400),
            state("A", 10, "pushed", "0402", "0402"),
            {"ts": ts(2), "kind": "note", "id": "A", "data": {"text": "(0402) ح"}},
        ]
        r = self.rows(ev)["0402"]
        self.assertEqual(r["skipped_ready"], ["A"])
        self.assertEqual(r["verdict"], sc.WATCH)

    def test_reapproval_counts_changed_heads(self):
        ev = [
            created("A", 400),
            state("A", 200, "approved", "0501", "0403", "aaaa1111"),
            state("A", 100, "approved", "0501", "0403", "bbbb2222"),
        ]
        self.assertEqual(sc.reapprovals(ev, "A"), 1)

    def test_silent_with_open_cards_watch(self):
        ev = [created("A", 900), state("A", 700, "in_progress", "0403", "0403")]
        self.assertEqual(self.rows(ev)["0403"]["verdict"], sc.WATCH)

    def test_weekly_cap_and_unmeasured(self):
        rows = [{"session": "0401", "suggestions": ["a", "b"]}]
        st = {}
        self.assertEqual(sc.apply_weekly_cap(rows, st, NOW)[0]["suggestions"], ["a"])
        rows2 = [{"session": "0401", "suggestions": ["a"]}]
        self.assertEqual(sc.apply_weekly_cap(rows2, st, NOW)[0]["suggestions"], [])
        ev = [created("A", 10), state("A", 5, "ready_for_review", "0401", "0401")]
        self.assertEqual(self.rows(ev)["0401"]["owner_bypass"], "غير مقيس")

    def test_heavy_context_suggestion(self):
        ev = [created("A", 10), state("A", 5, "ready_for_review", "0401", "0401")]
        r = sc.score(ev, NOW, Path("/nonexistent"), {"0401": 150_000})[0]
        self.assertTrue(any("140k" in s for s in r["suggestions"]))

    def test_html_renders(self):
        ev = [created("A", 10), state("A", 5, "ready_for_review", "0401", "0401")]
        out = sc.render_html(sc.score(ev, NOW, Path("/nonexistent")), NOW)
        self.assertIn("dir='rtl'", out)
        self.assertIn("0401", out)


if __name__ == "__main__":
    unittest.main()
