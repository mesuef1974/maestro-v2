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
