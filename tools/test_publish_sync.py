"""اختباراتُ publish_sync (W-20261014-013) — unittest بلا شبكةٍ ولا gh:  python -m unittest tools.test_publish_sync"""

import unittest

import publish_sync as ps

HEALTH_OK = '{"status": "ok", "version": "v5.5", "commit": "25cef9a", "checks": {"db": "ok"}, "latency_ms": 6.2}'


class Health(unittest.TestCase):
    def test_commit_is_read(self):
        self.assertEqual(ps.parse_health(HEALTH_OK), "25cef9a")

    def test_unhealthy_production_is_refused(self):
        with self.assertRaises(ps.SyncError):
            ps.parse_health('{"status": "error", "commit": "25cef9a"}')

    def test_missing_or_short_commit_is_refused(self):
        for bad in ('{"status": "ok"}', '{"status": "ok", "commit": "abc"}', "not json"):
            with self.assertRaises(ps.SyncError):
                ps.parse_health(bad)


PRS = {
    "aaaaaaaa": {"number": 10, "merge": "1111111111", "at": "2026-10-14T10:00:00Z"},
    "bbbbbbbb": {"number": 11, "merge": "2222222222", "at": "2026-10-14T11:00:00Z"},
}


def check(merge, prod):
    return merge == "1111111111"  # الأول وحده داخل الإنتاج


class Due(unittest.TestCase):
    def test_only_merged_and_in_production_cards_are_due(self):
        states = {
            "W-1": {"state": "approved", "approved_head": "aaaaaaaa"},
            "W-2": {"state": "pushed", "head": "bbbbbbbb"},  # مدموج لكنه ليس في الإنتاج بعد
            "W-3": {"state": "pushed", "head": "cccccccc"},  # لا طلب مدموج برأسه
            "W-4": {"state": "published", "approved_head": "aaaaaaaa"},  # منقول أصلاً
        }
        rows = ps.due(states, PRS, "25cef9a", check)
        self.assertEqual([r["id"] for r in rows], ["W-1"])
        self.assertEqual(rows[0]["pr"], 10)

    def test_card_without_head_is_skipped(self):
        self.assertEqual(ps.due({"W-5": {"state": "approved"}}, PRS, "25cef9a", check), [])


class Commands(unittest.TestCase):
    def row(self, state):
        return {"id": "W-1", "state": state, "pr": 10, "merge": "111111111", "prod": "25cef9a"}

    def test_chain_starts_after_current_state(self):
        self.assertEqual(len(ps.commands(self.row("approved"))), 3)
        self.assertEqual(len(ps.commands(self.row("pushed"))), 2)
        self.assertEqual(len(ps.commands(self.row("merged"))), 1)
        self.assertIn("move W-1 published", ps.commands(self.row("merged"))[0])

    def test_commands_are_printed_never_executed(self):
        cmds = ps.commands(self.row("approved"))
        self.assertTrue(all(c.startswith("python tools/ledger.py move ") for c in cmds))

    def test_report_text_names_cards_and_prs(self):
        text = ps.report_text([{"id": "W-1", "pr": 10}, {"id": "W-2", "pr": 11}], "25cef9a")
        self.assertIn("W-1 (#10)", text)
        self.assertIn("25cef9a", text)


if __name__ == "__main__":
    unittest.main()
