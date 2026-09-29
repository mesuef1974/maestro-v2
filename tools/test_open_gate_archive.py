"""اختباراتُ بوّابة الفتح ومرشّحي الأرشفة:  python -m unittest test_open_gate_archive -v"""

import unittest

import archive_candidates as acd
import open_gate as og

OK = {"ok": True, "blockers": []}


class Gate(unittest.TestCase):
    def test_blockers_stop_everything(self):
        self.assertEqual(og.decide({"ok": False, "blockers": ["x"]}, [], "green", "P0")["verdict"], "لا تفتح")

    def test_assign_beats_open_even_when_p0_and_red(self):
        s = [{"session": "0404 · إدارة: أ (W-1)", "assignable": True, "wip": 1, "context_mb": 5}]
        self.assertEqual(og.decide(OK, s, "red", "P0")["verdict"], "أسنِد")

    def test_red_waits_unless_p0(self):
        self.assertEqual(og.decide(OK, [], "red", "P2")["verdict"], "انتظر")
        self.assertEqual(og.decide(OK, [], "critical", "P0")["verdict"], "افتح بحذر")

    def test_green_opens(self):
        self.assertEqual(og.decide(OK, [], "green", "P1")["verdict"], "افتح الآن")

    def test_tag_filter_reads_name_and_assignable(self):
        rows = [{"session": "0402 · جدول: أ (W-1)", "assignable": True},
                {"session": "0404 · واجهة: ب (W-2)", "assignable": True},
                {"session": "0405 · واجهة: ج (W-3)", "assignable": False}]
        self.assertEqual([r["session"] for r in og.assignable_with_tag(rows, "واجهة")], ["0404 · واجهة: ب (W-2)"])


class Archive(unittest.TestCase):
    def test_stopped_hours(self):
        self.assertEqual(acd.stopped_hours("Exited (0) 3 hours ago"), 3)
        self.assertEqual(acd.stopped_hours("Exited (137) About an hour ago"), 1)
        self.assertEqual(acd.stopped_hours("Exited (0) 2 days ago"), 48)
        self.assertIsNone(acd.stopped_hours("Up 12 hours (healthy)"))

    def test_running_or_recent_container_blocks(self):
        rows = [("schoolos-t-web-1", "Up 1 hour"), ("schoolos-t-worker-1", "Exited (0) 30 minutes ago"),
                ("schoolos-t-old-1", "Exited (0) 5 hours ago"), ("schoolos-other-web-1", "Up 1 hour")]
        self.assertEqual(len(acd.containers_of("t", rows, 2)), 2)

    def test_final_states_only(self):
        self.assertTrue({"merged", "closed"} <= acd.FINAL_STATES)
        self.assertFalse({"verified", "in_progress"} & acd.FINAL_STATES)


if __name__ == "__main__":
    unittest.main()
