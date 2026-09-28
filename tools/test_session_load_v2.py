"""اختباراتُ session_load_v2 — unittest بلا اعتمادٍ خارجيّ:  python -m unittest test_session_load_v2 -v"""

import unittest
from datetime import date

import session_load_v2 as sl


class DohaDay(unittest.TestCase):
    def test_late_utc_evening_is_next_doha_day(self):
        # 21:00 UTC = 00:00 الدوحة من اليوم التالي — كان الأصلُ ينسبه إلى اليوم السابق
        self.assertEqual(sl.doha_day("2026-09-25T21"), date(2026, 9, 26))

    def test_early_utc_is_same_doha_day(self):
        self.assertEqual(sl.doha_day("2026-09-26T05"), date(2026, 9, 26))

    def test_boundary_20_utc_is_still_previous_doha_day(self):
        self.assertEqual(sl.doha_day("2026-09-25T20"), date(2026, 9, 25))

    def test_count_events_buckets(self):
        today = date(2026, 9, 26)
        prefixes = ["2026-09-25T21", "2026-09-26T10", "2026-09-25T10", "2026-09-24T10"]
        self.assertEqual(sl.count_events(prefixes, today), (2, 1))


class Attribution(unittest.TestCase):
    def tree(self, name, ahead=(), reflog=()):
        return {"name": name, "ahead": set(ahead), "reflog": list(reflog)}

    def test_independent_prs_all_attributed_via_reflog(self):
        # ستّة طلباتٍ مستقلّة عند شجرةٍ واحدة: رأسُ الشجرة أسلافُه واحدٌ فقط، والباقي في reflog
        prs = [{"number": n, "headRefOid": f"sha{n}"} for n in range(1, 7)]
        t = self.tree("design", ahead=["sha1"], reflog=[f"sha{n}" for n in range(1, 7)])
        got = sl.attribute_prs(prs, [t, self.tree("other")], {})
        self.assertEqual(set(got.values()), {"design"})

    def test_most_recent_reflog_wins_when_two_trees_saw_it(self):
        prs = [{"number": 1, "headRefOid": "s"}]
        a = self.tree("a", reflog=["x", "y", "s"])
        b = self.tree("b", reflog=["s"])
        self.assertEqual(sl.attribute_prs(prs, [a, b], {})[1], "b")

    def test_reflog_beats_ahead_only(self):
        prs = [{"number": 1, "headRefOid": "s"}]
        a = self.tree("a", ahead=["s"])
        b = self.tree("b", reflog=["s"])
        self.assertEqual(sl.attribute_prs(prs, [a, b], {})[1], "b")

    def test_override_wins(self):
        prs = [{"number": 7, "headRefOid": "s"}]
        self.assertEqual(sl.attribute_prs(prs, [self.tree("a", reflog=["s"])], {"7": "z"})[7], "z")

    def test_unowned_is_none(self):
        prs = [{"number": 9, "headRefOid": "bot"}]
        self.assertIsNone(sl.attribute_prs(prs, [self.tree("a")], {})[9])


class Classify(unittest.TestCase):
    base = {"open_prs": 0, "context_mb": 0}

    def test_four_prs_is_overloaded(self):  # التعريفُ في operating_model: ≥4 طلبات
        r = sl.classify({**self.base, "open_prs": 4}, 3, 40)
        self.assertTrue(r["overloaded"] and r["over_wip"] and not r["assignable"])

    def test_three_prs_is_at_limit_not_overloaded(self):
        r = sl.classify({**self.base, "open_prs": 3}, 3, 40)
        self.assertFalse(r["overloaded"] or r["over_wip"])
        self.assertTrue(r["assignable"])

    def test_heavy_context_alone_overloads(self):
        r = sl.classify({**self.base, "context_mb": 40}, 3, 40)
        self.assertTrue(r["heavy"] and r["overloaded"])

    def test_many_prs_light_context_now_flagged(self):  # الثغرةُ في الأصل: كان يُعلَّم بالحجم فقط
        r = sl.classify({**self.base, "open_prs": 6, "context_mb": 10}, 3, 40)
        self.assertTrue(r["overloaded"])


if __name__ == "__main__":
    unittest.main()
