"""R2 عبر مسار «جاهزٌ للمعاينة» الحقيقيّ (W-20261014-007): فرعٌ مبنيٌّ على main محلّيٍّ متقدّمٍ بلا دفعٍ يُرفض انتقالُه ولا يُكتب شيءٌ.

الفحصُ المسبق هنا حقيقيٌّ (لا بديل وهميّ): هو الذي أفلت في حادثة 10-19 لأن ready_mark كان يعلّم الرأسَ بإعفاءٍ مدوَّنٍ بلا فحص.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import ledger
import ready_mark as rm

CARD = "W-20261019-777"
ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def git(repo, *a):
    return subprocess.run(
        ["git", "-C", repo, *a],
        capture_output=True,
        encoding="utf-8",
        check=True,
        env=ENV,
    ).stdout.strip()


class R2(unittest.TestCase):
    def build(self, on_local_main_ahead: bool):
        tmp = tempfile.mkdtemp()
        origin, repo = str(Path(tmp) / "o.git"), str(Path(tmp) / "r")
        subprocess.run(
            ["git", "init", "-q", "--bare", "-b", "main", origin], check=True, env=ENV
        )
        subprocess.run(
            ["git", "clone", "-q", origin, repo],
            check=True,
            capture_output=True,
            env=ENV,
        )
        git(repo, "checkout", "-q", "-b", "main")
        (Path(repo) / "a").write_text("1", encoding="utf-8")
        git(repo, "add", "a")
        git(repo, "commit", "-q", "-m", "base")
        git(repo, "push", "-q", "origin", "main")
        if on_local_main_ahead:
            (Path(repo) / "a").write_text("2", encoding="utf-8")
            git(repo, "commit", "-qam", "إيداعٌ محلّيٌّ على main لم يُدفع")
        git(repo, "checkout", "-q", "-b", "claude/task")
        (Path(repo) / "b").write_text("x", encoding="utf-8")
        git(repo, "add", "b")
        git(repo, "commit", "-q", "-m", f"{CARD}: عمل")
        self.repo = repo
        self.head = git(repo, "rev-parse", "--short=8", "HEAD")
        self.ledger = Path(tmp) / "events.jsonl"
        ledger.append_event(
            "created",
            CARD,
            {"problem": "م", "state": "captured", "type": "tool", "files": []},
            self.ledger,
        )
        ledger.append_event(
            "state",
            CARD,
            {"state": "in_progress", "by": "0702", "held_by": "0702"},
            self.ledger,
        )

    def state(self):
        return ledger.reduce_state(ledger.load_events(self.ledger))[CARD]["state"]

    def test_a_branch_on_an_unpushed_local_main_is_refused_and_nothing_is_written(self):
        self.build(on_local_main_ahead=True)
        n = len(ledger.load_events(self.ledger))
        with self.assertRaises(ledger.LedgerError) as cm:
            rm.mark(CARD, self.head, "0702", self.repo, path=self.ledger)
        self.assertIn("ولم يُدفع", str(cm.exception))
        self.assertIn("main", str(cm.exception))
        self.assertEqual(self.state(), "in_progress")
        self.assertEqual(len(ledger.load_events(self.ledger)), n)

    def test_the_same_refusal_comes_from_ledger_move_with_the_tree(self):
        self.build(on_local_main_ahead=True)
        with self.assertRaises(ledger.LedgerError) as cm:
            ledger.move(
                CARD,
                "ready_for_review",
                path=self.ledger,
                by="0702",
                head_now=self.head,
                preflight_repo=self.repo,
            )
        self.assertIn("ولم يُدفع", str(cm.exception))
        self.assertEqual(self.state(), "in_progress")

    def test_a_branch_straight_off_origin_main_is_not_refused_for_r2(self):
        self.build(on_local_main_ahead=False)
        try:
            rm.mark(CARD, self.head, "0702", self.repo, path=self.ledger)
        except (
            ledger.LedgerError
        ) as e:  # قد يفشل لسببٍ آخر في مستودعٍ تجريبيّ (mypy)، لا R2
            self.assertNotIn("ولم يُدفع", str(e))

    def test_an_explicit_waiver_still_skips_the_check_and_is_recorded(self):
        self.build(on_local_main_ahead=True)
        rm.mark(
            CARD,
            self.head,
            "0702",
            self.repo,
            path=self.ledger,
            waive_preflight="سببٌ مكتوب",
        )
        self.assertEqual(self.state(), "ready_for_review")


if __name__ == "__main__":
    unittest.main()
