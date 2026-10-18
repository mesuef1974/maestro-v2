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


class Digest(unittest.TestCase):
    ROWS = [
        {"id": "W-1", "state": "approved", "head": "aaaaaaaa", "pr": 10, "merge": "1111111"},
        {"id": "W-2", "state": "merged", "head": "bbbbbbbb", "pr": 11, "merge": "2222222"},
    ]
    STATES = {"W-1": {"held_by": "0417"}, "W-2": {"held_by": "0417"}, "W-3": {}}

    def test_digest_note_carries_whole_batch(self):
        text = ps.digest_note(self.ROWS[0], self.ROWS, "331f3ae")
        self.assertIn("#10", text)
        self.assertIn("W-2 (#11)", text)

    def test_one_message_per_owner(self):
        msgs = ps.messages_by_owner(self.ROWS, self.STATES, "331f3ae")
        self.assertEqual(list(msgs), ["0417"])
        self.assertIn("W-1 (#10)", msgs["0417"])
        self.assertIn("W-2 (#11)", msgs["0417"])

    def test_no_owner_goes_to_0701(self):
        msgs = ps.messages_by_owner([{"id": "W-3", "pr": 12}], self.STATES, "331f3ae")
        self.assertEqual(list(msgs), ["0701"])

    def test_write_notes_only_writes_notes(self):
        calls = []
        done = ps.write_notes(self.ROWS, "331f3ae", "0601", add_note=lambda *a: calls.append(a))
        self.assertEqual(done, ["W-1", "W-2"])
        self.assertEqual([c[0] for c in calls], ["W-1", "W-2"])
        self.assertTrue(all(c[2] == "0601" for c in calls))


class CliWiring(unittest.TestCase):
    """أعلام --digest و--write-notes يجب أن تنفّذ فعلاً (كانت تُقبل وتُهمل)."""

    ROWS = Digest.ROWS
    STATES = Digest.STATES

    def run_main(self, argv):
        import contextlib
        import io
        from unittest import mock

        out = io.StringIO()
        with mock.patch.object(ps, "due", return_value=[dict(r) for r in self.ROWS]), \
                mock.patch.object(ps.ledger, "reduce_state", return_value=self.STATES), \
                mock.patch.object(ps.ledger, "load_events", return_value=[]), \
                mock.patch.object(ps, "merged_prs", return_value={}), \
                contextlib.redirect_stdout(out):
            code = ps.main(argv)
        return code, out.getvalue()

    def test_write_notes_writes_batch_note_per_card(self):
        from unittest import mock

        with mock.patch.object(ps.ledger, "add_note") as add:
            code, out = self.run_main(["--commit", "331f3aeb", "--write-notes", "--by", "0601"])
        self.assertEqual(code, 0)
        self.assertEqual([c.args[0] for c in add.call_args_list], ["W-1", "W-2"])
        self.assertIn("W-1، W-2", out)

    def test_write_notes_requires_by(self):
        code, _ = self.run_main(["--commit", "331f3aeb", "--write-notes"])
        self.assertEqual(code, 2)

    def test_digest_prints_without_writing(self):
        from unittest import mock

        with mock.patch.object(ps.ledger, "add_note") as add:
            code, out = self.run_main(["--commit", "331f3aeb", "--digest"])
        self.assertEqual(code, 0)
        add.assert_not_called()
        self.assertIn("#10", out)
        self.assertIn("إلى 0417", out)


if __name__ == "__main__":
    unittest.main()
