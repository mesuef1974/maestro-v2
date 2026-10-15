"""اختباراتُ ready_mark — unittest بلا اعتمادٍ خارجيّ:  python -m unittest test_ready_mark"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import ledger
import ready_mark as rm

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, encoding="utf-8", check=True, env=ENV).stdout.strip()


class ReadyMark(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = str(Path(self.tmp) / "r")
        Path(self.repo).mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        (Path(self.repo) / "a").write_text("x", encoding="utf-8")
        git(self.repo, "add", "a")
        git(self.repo, "commit", "-q", "-m", "base")
        git(self.repo, "checkout", "-q", "-b", "w")
        (Path(self.repo) / "b").write_text("y", encoding="utf-8")
        git(self.repo, "add", "b")
        git(self.repo, "commit", "-q", "-m", "W-20261015-777: عمل")
        self.head = git(self.repo, "rev-parse", "--short=8", "HEAD")
        self.ledger = Path(self.tmp) / "events.jsonl"
        self.card = "W-20261015-777"
        ledger.append_event("created", self.card, {"problem": "م", "state": "captured", "type": "ui", "files": ["templates/"]}, self.ledger)
        ledger.append_event("state", self.card, {"state": "in_progress", "by": "0702", "held_by": "0702"}, self.ledger)

    def mark(self, head=None, **kw):
        return rm.mark(self.card, head or self.head, "0702", self.repo, base="main", path=self.ledger, **kw)

    def item(self):
        return ledger.reduce_state(ledger.load_events(self.ledger))[self.card]

    def test_moves_to_ready_for_review_with_the_head_in_a_note_only(self):
        self.mark(link="http://localhost:8500/x/", role="principal")
        it = self.item()
        self.assertEqual(it["state"], "ready_for_review")
        self.assertEqual(rm.declared_head(it), self.head)
        self.assertIn("http://localhost:8500/x/", it["notes"][-1]["text"])
        # لا اعتمادَ ينتحله الرأس: حقلُ approved_head يُكتب للاعتماد وحدَه
        self.assertNotIn("approved_head", it)

    def test_repeating_with_the_same_head_is_a_no_op(self):
        self.mark()
        n = len(ledger.load_events(self.ledger))
        self.assertIn("لا تغيير", self.mark())
        self.assertEqual(len(ledger.load_events(self.ledger)), n)

    def test_a_new_head_re_marks_the_card(self):
        self.mark()
        (Path(self.repo) / "c").write_text("z", encoding="utf-8")
        git(self.repo, "add", "c")
        git(self.repo, "commit", "-q", "-m", "W-20261015-777: تعديل")
        new = git(self.repo, "rev-parse", "--short=8", "HEAD")
        self.mark(head=new)
        self.assertEqual(rm.declared_head(self.item()), new)

    def test_a_head_of_another_card_is_refused(self):
        git(self.repo, "checkout", "-q", "-b", "o", "main")
        (Path(self.repo) / "d").write_text("q", encoding="utf-8")
        git(self.repo, "add", "d")
        git(self.repo, "commit", "-q", "-m", "W-20261015-888: غيرها")
        other = git(self.repo, "rev-parse", "--short=8", "HEAD")
        with self.assertRaises(ledger.LedgerError):
            self.mark(head=other)

    def test_an_unknown_head_is_refused(self):
        with self.assertRaises(ledger.LedgerError):
            self.mark(head="deadbeef")

    def test_an_approved_card_is_not_moved_back(self):
        ledger.append_event("state", self.card, {"state": "approved", "by": "0501", "head": self.head}, self.ledger)
        with self.assertRaises(ledger.LedgerError):
            self.mark()

    def test_dry_run_writes_nothing(self):
        n = len(ledger.load_events(self.ledger))
        self.assertIn("[dry]", self.mark(dry=True))
        self.assertEqual(len(ledger.load_events(self.ledger)), n)

    def test_a_missing_ledger_exits_2_with_the_same_message_as_batch_preview(self):
        import io
        from contextlib import redirect_stderr

        old = os.environ.get("LEDGER_PATH")
        os.environ["LEDGER_PATH"] = str(Path(self.tmp) / "none.jsonl")
        buf = io.StringIO()
        try:
            with redirect_stderr(buf):
                rc = rm.main([self.card, "--head", self.head, "--by", "0702", "--repo", self.repo])
        finally:
            if old is None:
                os.environ.pop("LEDGER_PATH", None)
            else:
                os.environ["LEDGER_PATH"] = old
        self.assertEqual(rc, 2)
        self.assertIn("لا دفترَ في", buf.getvalue())
        self.assertNotIn("غيرُ موجودة", buf.getvalue())

    def test_unknown_card_is_refused(self):
        with self.assertRaises(ledger.LedgerError):
            rm.mark("W-20261015-000", self.head, "0702", self.repo, base="main", path=self.ledger)


if __name__ == "__main__":
    unittest.main()
