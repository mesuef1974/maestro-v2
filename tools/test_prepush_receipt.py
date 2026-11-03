"""اختباراتُ قائمة ما قبل «جاهز»: إيصالُ prepush وحداثةُ main (W-20261017-014)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402
from ledger import LedgerError  # noqa: E402


def fake_git(gitdir: str, head="abcd1234", lag="0"):
    def g(*a):
        if a[:2] == ("rev-parse", "--short=8"):
            return head
        if a[:2] == ("rev-parse", "--absolute-git-dir"):
            return gitdir
        if a[:2] == ("rev-list", "--count"):
            return lag
        return ""

    return g


class Receipt(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)

    def write(self, **kw):
        (Path(self.d.name) / ledger.RECEIPT_NAME).write_text(json.dumps(kw), encoding="utf-8")

    def check(self, **kw):
        return ledger.check_prepush_receipt("x", git=fake_git(self.d.name, **kw))

    def enforced(self):
        os.environ["PREPUSH_RECEIPT_ENFORCE"] = "1"
        self.addCleanup(os.environ.pop, "PREPUSH_RECEIPT_ENFORCE", None)

    def test_good_receipt_and_fresh_head_pass(self):
        self.write(head="abcd1234", ok=True)
        self.enforced()
        self.assertIn("سليمان", self.check())

    def test_missing_receipt_refuses_when_enforced(self):
        self.enforced()
        with self.assertRaises(LedgerError) as cm:
            self.check()
        self.assertIn("make prepush", str(cm.exception))

    def test_receipt_for_other_head_refuses(self):
        self.write(head="deadbeef", ok=True)
        self.enforced()
        with self.assertRaises(LedgerError):
            self.check()

    def test_failed_receipt_refuses(self):
        self.write(head="abcd1234", ok=False)
        self.enforced()
        with self.assertRaises(LedgerError):
            self.check()

    def test_lag_over_limit_refuses_and_at_limit_passes(self):
        self.write(head="abcd1234", ok=True)
        self.enforced()
        with self.assertRaises(LedgerError) as cm:
            self.check(lag=str(ledger.MAIN_LAG_MAX + 1))
        self.assertIn("origin/main", str(cm.exception))
        self.assertIn("سليمان", self.check(lag=str(ledger.MAIN_LAG_MAX)))

    def test_missing_receipt_refuses_by_default(self):  # قرار المالك 2026-10-20: الإلزامُ افتراضيّ
        with self.assertRaises(LedgerError):
            self.check()

    def test_shadow_warns_without_refusing(self):
        os.environ["PREPUSH_RECEIPT_ENFORCE"] = "0"
        self.addCleanup(os.environ.pop, "PREPUSH_RECEIPT_ENFORCE", None)
        self.assertIn("إنذار (الظلّ)", self.check())

    def test_waiver_and_p0_unchanged(self):
        card = {"id": "W-1", "priority": "P1"}
        self.assertIn("استثناءُ", ledger.check_preflight_ready(card, "ready_for_review", "x", "سبب"))
        self.assertIsNone(ledger.check_preflight_ready({"id": "W-1", "priority": "P0"}, "ready_for_review", "x", None))


if __name__ == "__main__":
    unittest.main()


def test_governance_repo_has_no_receipt_producer_so_no_receipt_is_required(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "ledger.py").write_text("", encoding="utf-8")
    assert ledger.check_prepush_receipt(str(tmp_path)) is None


def test_governance_repo_needs_no_premerge_fingerprint(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "ledger.py").write_text("", encoding="utf-8")
    assert ledger.check_premerge_fingerprint({"type": "feature"}, "ready_for_review", None, "abcd1234", None, str(tmp_path)) is None


def test_old_platform_tree_without_prepush_tool_uses_root_scripts(tmp_path):
    """W-20261028-022 (D-499م R6): منصّةٌ أقدمُ من أداة prepush تُفحص بسكربتات الجذر لا «غير مقيس (أداة غائبة)»."""
    import flow_pump as fp

    root, tree = tmp_path / "root", tmp_path / "tree"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "prepush_check.py").write_text("x", encoding="utf-8")
    tree.mkdir()
    (tree / "manage.py").write_text("x", encoding="utf-8")
    assert fp.root_prepush_scripts(str(tree), str(root)) == str(root / "scripts")
    cmd = fp.prepush_command(str(tree), str(tree / ".git"), str(tree / ".git"), "n", "net", str(root / "scripts"))
    assert f"{root / 'scripts'}:/rootscripts:ro" in cmd and "PREPUSH_ROOT_SCRIPTS=/rootscripts" in cmd
    assert "PREPUSH_ROOT_SCRIPTS=/rootscripts" not in fp.prepush_command(str(tree), str(tree / ".git"), str(tree / ".git"), "n", "net")


def test_root_scripts_not_used_when_tree_has_its_own_tool_or_is_not_platform_or_root_lacks_it(tmp_path):
    import flow_pump as fp

    root, own, gov, bare = tmp_path / "root", tmp_path / "own", tmp_path / "gov", tmp_path / "bare"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "prepush_check.py").write_text("x", encoding="utf-8")
    (own / "scripts").mkdir(parents=True)
    (own / "scripts" / "prepush_check.py").write_text("x", encoding="utf-8")
    (own / "manage.py").write_text("x", encoding="utf-8")
    gov.mkdir()  # مستودعُ حوكمة: بلا manage.py ⇒ الإيصالُ البديل لا الجذر
    bare.mkdir()
    (bare / "manage.py").write_text("x", encoding="utf-8")
    assert fp.root_prepush_scripts(str(own), str(root)) is None
    assert fp.root_prepush_scripts(str(gov), str(root)) is None
    assert fp.root_prepush_scripts(str(bare), str(tmp_path / "empty-root")) is None
