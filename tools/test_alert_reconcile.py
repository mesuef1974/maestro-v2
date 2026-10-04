"""اختباراتُ تسوية تنبيهات code-scanning مع الدفتر:  python -m unittest test_alert_reconcile"""

import json
import unittest

import alert_reconcile as ar


class Refs(unittest.TestCase):
    def test_extracts_alert_numbers_not_pr_numbers(self):
        self.assertEqual(ar.alert_numbers("تنبيهُ فحص الشيفرة #106 (py/url-redirection)"), {106})
        self.assertEqual(ar.alert_numbers("تنبيهات #106/#110 مفتوحة"), {106, 110})
        self.assertEqual(ar.alert_numbers("دُمج في الطلب #725 فقط"), set())


class Reconcile(unittest.TestCase):
    ITEMS = {
        "W-1": {"id": "W-1", "state": "captured", "problem": "تنبيهُ فحص الشيفرة #106", "notes": []},
        "W-2": {"id": "W-2", "state": "in_progress", "problem": "x", "notes": [{"text": "يخصّ تنبيه #110"}]},
        "W-3": {"id": "W-3", "state": "closed", "problem": "تنبيه #106", "notes": []},
        "W-4": {"id": "W-4", "state": "captured", "problem": "تنبيه #200", "notes": []},
    }
    ALERTS = [{"number": 106, "state": "fixed", "rule": {"id": "py/url-redirection"}, "fixed_at": "2026-10-01"},
              {"number": 110, "state": "dismissed", "dismissed_reason": "false positive"},
              {"number": 200, "state": "open"}]

    def test_open_cards_of_closed_alerts_only(self):
        rows = ar.reconcile(self.ITEMS, self.ALERTS)
        self.assertEqual([(r["card"], r["alert"]) for r in rows], [("W-1", 106), ("W-2", 110)])

    def test_read_only(self):
        before = json.dumps(self.ITEMS, sort_keys=True)
        ar.reconcile(self.ITEMS, self.ALERTS)
        self.assertEqual(before, json.dumps(self.ITEMS, sort_keys=True))

    def test_fetch_uses_injected_runner_and_merges_pages(self):
        class P:
            def __init__(self, out): self.stdout, self.stderr, self.returncode = out, "", 0
        calls = []
        def runner(cmd, **kw):
            calls.append(cmd[-1])
            return P('[{"number":1,"state":"dismissed"}][{"number":2,"state":"dismissed"}]' if "dismissed" in cmd[-1]
                     else '[{"number":3,"state":"fixed"}]')
        got = ar.fetch_closed_alerts("o/r", runner)
        self.assertEqual([a["number"] for a in got], [1, 2, 3])
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
