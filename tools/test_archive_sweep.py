"""اختباراتُ archive_sweep — unittest بلا اعتمادٍ خارجيّ:  python -m unittest test_archive_sweep"""

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive_sweep as sw  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 9, 29, 21, 0)
CORE = {"0101 · المايسترو"}


class Candidates(unittest.TestCase):
    def test_only_flexible_non_core_live_sessions(self):
        self.assertTrue(sw.is_candidate({"title": "0405 · إدارة: مهمّة (W-1)"}, CORE))
        self.assertFalse(sw.is_candidate({"title": "0101 · المايسترو"}, CORE))
        self.assertFalse(sw.is_candidate({"title": "0301 · المستشار"}, CORE))
        self.assertFalse(sw.is_candidate({"title": "0405 · إدارة: مهمّة", "isArchived": True}, CORE))
        self.assertFalse(sw.is_candidate({"title": "Qatar advisor security sprint"}, CORE))


class DeployAndRoadmap(unittest.TestCase):
    def check(self, prs, commit, oids, ancestors, mentioned):
        return sw.extra_blockers(prs, commit, lambda n: oids.get(n), lambda oid, c: oid in ancestors, mentioned)

    def test_deployed_and_on_roadmap_is_clean(self):
        b, notes = self.check([1], "abc", {1: "o1"}, {"o1"}, {1})
        self.assertEqual(b, [])
        self.assertTrue(notes)

    def test_merged_but_not_in_live_production_blocks(self):
        b, _ = self.check([1, 2], "abc", {1: "o1", 2: "o2"}, {"o1"}, {1, 2})
        self.assertEqual(b, ["طلبٌ مدموجٌ لم يبلغ الإنتاجَ الحيّ: #2"])

    def test_roadmap_gap_blocks(self):
        b, _ = self.check([1], "abc", {1: "o1"}, {"o1"}, set())
        self.assertEqual(b, ["الخارطةُ لم تذكر: #1 (تنتظر 0702)"])

    def test_unknown_production_blocks_conservatively(self):
        b, _ = self.check([1], None, {1: "o1"}, {"o1"}, {1})
        self.assertTrue(any("تعذّر التحقّق" in x for x in b))

    def test_no_merged_pr_has_no_extra_blockers(self):
        b, notes = self.check([], "abc", {}, set(), set())
        self.assertEqual(b, [])
        self.assertTrue(notes)


class Notes(unittest.TestCase):
    FACTS = {"branch_prs": [736], "branch_status": "merged", "open_prs": [], "dirty_files": 0, "cherry_plus": 3}

    def test_section_names_the_session_and_facts(self):
        text = sw.note_section("0405 · إدارة: مهمّة (W-1)", "tree-x", "claude/x", self.FACTS, ["منشورةٌ"], NOW)
        self.assertIn("«0405 · إدارة: مهمّة (W-1)»", text)
        self.assertIn("#736", text)
        self.assertIn("2026-09-29 21:00", text)

    def test_write_note_new_then_prepend_never_overwrites(self):
        path = Path(tempfile.mkdtemp()) / "tree-x.md"
        self.assertEqual(sw.write_note(path, "A", "# A\n"), "كُتبت")
        self.assertEqual(sw.write_note(path, "B", "# B\n"), "أُلحقت")
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# B") and "# A" in text)
        self.assertEqual(sw.write_note(path, "A", "# A2\n"), "موجودة")


class Record(unittest.TestCase):
    def test_tabs_json_round_trips_without_noise(self):
        raw = (ROOT / "projects/schoolos/tabs.json").read_text(encoding="utf-8")
        self.assertEqual(json.dumps(json.loads(raw), ensure_ascii=False, indent=2) + "\n", raw.replace("\r\n", "\n"))

    def test_record_moves_member_to_archived_log(self):
        tmp = Path(tempfile.mkdtemp()) / "tabs.json"
        tmp.write_text(json.dumps({"tabs": [{"number": "04", "members": ["أ", "ب"]}], "archived_log": []}, ensure_ascii=False), encoding="utf-8")
        done = sw.record_archived(["أ", "غير موجود"], tmp, NOW)
        data = json.loads(tmp.read_text(encoding="utf-8"))
        self.assertEqual(done, ["أ"])
        self.assertEqual(data["tabs"][0]["members"], ["ب"])
        self.assertEqual(data["archived_log"][0]["decision"], "D-62م")


if __name__ == "__main__":
    unittest.main()
