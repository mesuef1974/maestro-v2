"""اختباراتُ batch_capture — unittest بلا اعتمادٍ خارجيّ:  python -m unittest test_batch_capture"""

import tempfile
import time
import unittest
from pathlib import Path

import batch_capture as bc
import visual_gate as vg
from test_batch_preview import commit, run


def row(card_id, head, link="http://localhost:8500/students/", role="admin"):
    return {"id": card_id, "head": head, "link": link, "role": role}


class Capture(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.evidence = Path(tempfile.mkdtemp())
        run(self.repo, "init", "-q", "-b", "main")
        (Path(self.repo) / "a.html").write_text("سطر\n", encoding="utf-8")
        run(self.repo, "add", "a.html")
        run(self.repo, "commit", "-q", "-m", "base")
        self.now = time.time()
        run(self.repo, "checkout", "-q", "-b", "a")
        self.head_a = commit(self.repo, "a", "W-1", "b.html", "ب\n", self.now - 600)
        run(self.repo, "checkout", "-q", "main")
        run(self.repo, "checkout", "-q", "-b", "c")
        self.head_c = commit(self.repo, "c", "W-2", "c.html", "ج\n", self.now - 300)
        self.served = self.head_a[:7]

    def plan(self, rows, served=None):
        return bc.plan_capture({"included": rows}, self.repo, self.served if served is None else served, self.evidence)

    def test_a_head_inside_the_served_commit_is_captured_now(self):
        step = self.plan([row("W-1", self.head_a)])[0]
        self.assertEqual(step["status"], bc.CAPTURE)
        self.assertEqual(step["entries"], [{"path": "/students/", "role": "admin"}])

    def test_a_head_not_inside_the_served_commit_is_never_captured(self):
        self.assertEqual(self.plan([row("W-2", self.head_c)])[0]["status"], bc.NOT_SERVED)

    def test_an_unreachable_server_captures_nothing(self):
        self.assertEqual(self.plan([row("W-1", self.head_a)], served="")[0]["status"], bc.NOT_SERVED)

    def test_a_card_without_a_page_path_is_refused_not_invented(self):
        self.assertEqual(self.plan([row("W-1", self.head_a, link="")])[0]["status"], bc.NO_PAGE)

    def test_a_missing_role_falls_back_to_anonymous(self):
        self.assertEqual(bc.entries_for(row("W-1", self.head_a, role="—"))[0]["role"], "anonymous")

    def test_approval_evidence_is_refused_for_an_uncaptured_head_and_for_another_head(self):
        ok, _ = vg.evidence_status("W-1", self.head_a[:8], self.evidence)
        self.assertFalse(ok)
        folder = self.evidence / "W-1" / "deadbeef"
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text('{"head": "deadbeef", "pages": []}', encoding="utf-8")
        ok, _ = vg.evidence_status("W-1", self.head_a[:8], self.evidence)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
