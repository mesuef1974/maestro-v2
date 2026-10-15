"""اختباراتُ batch_preview — unittest بلا اعتمادٍ خارجيّ:  python -m unittest test_batch_preview"""

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import batch_preview as bp


def run(repo, *args, env=None):
    e = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
         "GIT_COMMITTER_EMAIL": "t@t", **(env or {})}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, encoding="utf-8", check=True, env=e).stdout.strip()


def commit(repo, branch, card, path, text, when):
    run(repo, "checkout", "-q", branch)
    (Path(repo) / path).parent.mkdir(parents=True, exist_ok=True)
    (Path(repo) / path).write_text(text, encoding="utf-8")
    run(repo, "add", path)
    stamp = f"{int(when)} +0000"
    run(repo, "commit", "-q", "-m", f"{card}: عمل", env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})
    return run(repo, "rev-parse", "HEAD")


def card(item_id, state="ready_for_review", files=("templates/",), notes=(), held="0402"):
    return {"id": item_id, "state": state, "files": list(files), "type": "ui", "held_by": held, "problem": "م",
            "notes": [{"ts": "2026-10-15T10:00:00+03:00", "text": t} for t in notes]}


class Batch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = self.tmp
        run(self.repo, "init", "-q", "-b", "main")
        (Path(self.repo) / "a.html").write_text("سطر\n", encoding="utf-8")
        run(self.repo, "add", "a.html")
        run(self.repo, "commit", "-q", "-m", "base")
        self.now = time.time()

    def branch(self, name, from_="main"):
        run(self.repo, "checkout", "-q", "-b", name, from_)

    def test_three_cards_one_conflicting_is_excluded_with_reason(self):
        self.branch("a")
        commit(self.repo, "a", "W-1", "a.html", "سطر A\n", self.now - 3600)
        self.branch("b")
        commit(self.repo, "b", "W-2", "b.html", "ب\n", self.now - 1800)
        self.branch("c")
        commit(self.repo, "c", "W-3", "a.html", "سطر C\n", self.now - 600)
        items = {i["id"]: i for i in (card("W-1"), card("W-2"), card("W-3"))}
        rep = bp.plan(items, self.repo, "main", 48, now=self.now)
        self.assertEqual([r["id"] for r in rep["included"]], ["W-1", "W-2"])
        self.assertEqual([r["id"] for r in rep["excluded"]], ["W-3"])
        self.assertIn("يتعارض", rep["excluded"][0]["why"])

    def test_a_card_conflicting_with_main_is_excluded_with_rebase_hint(self):
        self.branch("a")
        commit(self.repo, "a", "W-1", "a.html", "سطر A\n", self.now - 3600)
        commit(self.repo, "main", "main-change", "a.html", "سطر main\n", self.now - 1000)
        rep = bp.plan({"W-1": card("W-1")}, self.repo, "main", 48, now=self.now)
        self.assertIn("إعادةَ أساس", rep["excluded"][0]["why"])

    def test_a_card_without_a_commit_has_no_head(self):
        rep = bp.plan({"W-9": card("W-9")}, self.repo, "main", 48, now=self.now)
        self.assertIn("لا إيداعَ", rep["excluded"][0]["why"])

    def test_an_idle_branch_is_excluded(self):
        self.branch("a")
        commit(self.repo, "a", "W-1", "b.html", "x\n", self.now - 100 * 3600)
        rep = bp.plan({"W-1": card("W-1")}, self.repo, "main", 48, now=self.now)
        self.assertIn("خاملٌ", rep["excluded"][0]["why"])

    def test_only_ready_ui_cards_are_listed(self):
        self.branch("a")
        commit(self.repo, "a", "W-1", "b.html", "x\n", self.now - 100)
        items = {"W-1": card("W-1"), "W-2": card("W-2", state="routed"),
                 "W-3": {**card("W-3", files=("tools/",)), "type": "tools"}}
        rep = bp.plan(items, self.repo, "main", 48, now=self.now)
        self.assertEqual({r["id"] for r in rep["included"] + rep["excluded"]}, {"W-1"})

    def test_link_role_and_account_come_from_the_card_notes(self):
        self.branch("a")
        commit(self.repo, "a", "W-1", "b.html", "x\n", self.now - 100)
        it = card("W-1", notes=["جاهزٌ للمعاينة http://localhost:8500/dashboard/ الدور principal"])
        reg = [{"role": "principal", "national_id": "99900001"}]
        row = bp.plan({"W-1": it}, self.repo, "main", 48, now=self.now, registry=reg)["included"][0]
        self.assertEqual((row["link"], row["role"], row["account"]), ("http://localhost:8500/dashboard/", "principal", "99900001"))

    def test_an_empty_batch_still_lists_every_exclusion_with_its_reason(self):
        self.branch("a")
        commit(self.repo, "a", "W-1", "b.html", "x\n", self.now - 100 * 3600)
        rep = bp.plan({"W-1": card("W-1"), "W-3": {**card("W-3", files=("tools/",)), "type": "tools"}}, self.repo, "main", 48, now=self.now)
        text = bp.render_text(rep)
        self.assertIn("الدفعة فارغة", text)
        self.assertIn("W-1", text)
        self.assertIn("خاملٌ", text)
        self.assertIn("W-3", text)  # غيرُ الواجهيّة تُعدّ وتُسمّى لا تُخفى
        self.assertIn("خاملٌ", bp.render_html(rep))

    def test_a_missing_ledger_fails_loudly_instead_of_reading_empty(self):
        old = os.environ.get("LEDGER_PATH")
        os.environ["LEDGER_PATH"] = str(Path(self.tmp) / "none.jsonl")
        try:
            self.assertEqual(bp.main(["--repo", self.repo, "--base", "main"]), 2)
        finally:
            if old is None:
                os.environ.pop("LEDGER_PATH", None)
            else:
                os.environ["LEDGER_PATH"] = old

    def test_the_planning_is_read_only(self):
        self.branch("a")
        commit(self.repo, "a", "W-1", "b.html", "x\n", self.now - 100)
        before = run(self.repo, "for-each-ref", "--format=%(refname) %(objectname)"), run(self.repo, "status", "--short")
        rep = bp.plan({"W-1": card("W-1")}, self.repo, "main", 48, now=self.now)
        bp.render_text(rep), bp.render_html(rep)
        after = run(self.repo, "for-each-ref", "--format=%(refname) %(objectname)"), run(self.repo, "status", "--short")
        self.assertEqual(before, after)
        src = Path(bp.__file__).read_text(encoding="utf-8")
        for forbidden in ("push", "append_event", "reset", "checkout"):
            self.assertNotIn(f'"{forbidden}"', src)


if __name__ == "__main__":
    unittest.main()
