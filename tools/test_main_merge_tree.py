"""D-154م الموسَّع (قرار المالك 2026-10-09): دمجُ main الآليُّ النظيف يُعفى، وكلُّ ما سواه يُرفض."""
import os
import subprocess
import tempfile
import unittest

import ledger


def g(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, encoding="utf-8", check=True).stdout.strip()


def commit(cwd, name, text, msg):
    with open(os.path.join(cwd, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    g(cwd, "add", name)
    g(cwd, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", msg)
    return g(cwd, "rev-parse", "HEAD")


class MainMergeTree(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        g(self.d, "init", "-q", "-b", "main")
        self.base = commit(self.d, "a.txt", "1\n2\n3\n4\n5\n6\n7\n8\n9\n", "base")
        g(self.d, "update-ref", "refs/remotes/origin/main", self.base)

    def _branch_edit_top_main_edit_bottom(self):
        g(self.d, "checkout", "-qb", "feat")
        approved = commit(self.d, "a.txt", "ONE\n2\n3\n4\n5\n6\n7\n8\n9\n", "feat")
        g(self.d, "checkout", "-q", "main")
        main2 = commit(self.d, "a.txt", "1\n2\n3\n4\n5\n6\n7\n8\nNINE\n", "main")
        g(self.d, "update-ref", "refs/remotes/origin/main", main2)
        g(self.d, "checkout", "-q", "feat")
        return approved, main2

    def test_clean_automatic_merge_is_waived(self):
        approved, main2 = self._branch_edit_top_main_edit_bottom()
        g(self.d, "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-edit", main2)
        new = g(self.d, "rev-parse", "HEAD")
        self.assertEqual(ledger.check_main_merge(approved, new, self.d), ["a.txt"])

    def test_short_approved_head_prefix_is_accepted(self):
        """الدفترُ يخزّن الرأسَ المعتمَد بثماني خانات: لا يُرفض الدمجُ الآليُّ النظيفُ لاختلاف الطول (#906)."""
        approved, main2 = self._branch_edit_top_main_edit_bottom()
        g(self.d, "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-edit", main2)
        new = g(self.d, "rev-parse", "HEAD")
        self.assertEqual(ledger.check_main_merge(approved[:8], new, self.d), ["a.txt"])

    def test_manual_extra_line_is_rejected(self):
        approved, main2 = self._branch_edit_top_main_edit_bottom()
        g(self.d, "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-commit", "--no-edit", main2)
        with open(os.path.join(self.d, "a.txt"), "a", encoding="utf-8", newline="\n") as f:
            f.write("EXTRA\n")
        g(self.d, "add", "a.txt")
        g(self.d, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "merge+extra")
        new = g(self.d, "rev-parse", "HEAD")
        with self.assertRaises(ledger.LedgerError):
            ledger.check_main_merge(approved, new, self.d)

    def test_second_parent_not_in_main_is_rejected(self):
        approved, main2 = self._branch_edit_top_main_edit_bottom()
        g(self.d, "update-ref", "refs/remotes/origin/main", self.base)  # main2 لم يعد في main
        g(self.d, "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-edit", main2)
        new = g(self.d, "rev-parse", "HEAD")
        with self.assertRaises(ledger.LedgerError):
            ledger.check_main_merge(approved, new, self.d)


if __name__ == "__main__":
    unittest.main()
