"""اختباراتُ حزمة المايسترو — unittest بلا اعتمادٍ خارجيّ:  python -m unittest test_package -v"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import archive_check as ac
import branch_status as bs
import evidence_pack as ep
import ledger
import review_window as rw
import risk_tier as rt
import routing as ro
import validate_registry as vr
import watch_once as wo

ROOT = Path(__file__).resolve().parent.parent
TABS = json.loads((ROOT / "projects/schoolos/tabs.json").read_text(encoding="utf-8"))
ROUTING = json.loads((ROOT / "projects/schoolos/routing.json").read_text(encoding="utf-8"))
TH = json.loads((ROOT / "projects/schoolos/thresholds.json").read_text(encoding="utf-8"))


class RiskTier(unittest.TestCase):
    def test_migration_is_high(self):
        self.assertEqual(rt.classify_paths(["operations/migrations/0042_x.py", "operations/models.py"])["tier"], "high")

    def test_roadmap_data_migration_is_light_not_high(self):
        self.assertEqual(rt.classify_paths(["roadmap/migrations/0041_sync.py"])["tier"], "light")

    def test_global_css_is_at_least_medium_and_flagged(self):
        r = rt.classify_paths(["static/css/custom/20-components.css"])
        self.assertIn("global_css", r["flags"])
        self.assertEqual(r["tier"], "medium")

    def test_docs_and_tests_are_light(self):
        self.assertEqual(rt.classify_paths(["docs/a.md", "tests/test_a.py"])["tier"], "light")

    def test_hot_file_flagged(self):
        self.assertIn("hot_file", rt.classify_paths(["docs/governance/regression_guards.md"])["flags"])

    def test_empty_paths_safe(self):
        self.assertEqual(rt.classify_paths([])["tier"], "low")

    def test_sensitive_files_are_high_and_base_templates_flagged(self):
        # مسارات المنصّة الفعليّة: أمنُ الصفوف ومحوُ البيانات والاحتفاظ والإعدادات خطورتُها عالية لا متوسّطة
        for path in ("core/middleware_rls.py", "governance/retention.py", "governance/erasure_service.py",
                     "core/management/commands/purge_parent_consents.py", "core/models/permission_audit.py",
                     "shschool/settings/production.py", "shschool/settings/base.py"):
            self.assertEqual(rt.classify_paths([path])["tier"], "high", path)
        self.assertEqual(rt.classify_paths(["shschool/settings/development.py"])["tier"], "medium")
        self.assertEqual(rt.classify_paths(["operations/services/schedule.py"])["tier"], "medium")
        # القالبُ الأساسيّ في templates/base/ يحمل علامةَ الأثر الواسع ويُرفَع إلى المتوسّطة على الأقلّ
        info = rt.classify_paths(["templates/base/base.html"])
        self.assertIn("base_template", info["flags"])
        self.assertIn("base_template", rt.classify_paths(["templates/auth/login.html"])["flags"])


class Ledger(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "e.jsonl"

    def add(self, **kw):
        base = dict(source="owner", problem_type="ui", problem="زرٌّ مقصوص", impact="صفحةٌ واحدة", accept="يظهر كاملاً", path=self.path,
                    start="2026-09-29T08:00", priority="P2")
        base.update(kw)
        return ledger.add_item(**base)

    def test_lifecycle_and_ids(self):
        a, b = self.add(), self.add()
        self.assertNotEqual(a, b)
        ledger.move(a, "in_progress", path=self.path)
        st = ledger.reduce_state(ledger.load_events(self.path))
        self.assertEqual(st[a]["state"], "in_progress")
        self.assertEqual(st[b]["state"], "captured")

    def test_rejects_long_text(self):
        with self.assertRaises(ledger.LedgerError):
            self.add(problem="س" * 300)

    def test_rejects_id_numbers_and_email(self):
        with self.assertRaises(ledger.LedgerError):
            self.add(problem="رقمٌ 12345678901 ظاهر")
        with self.assertRaises(ledger.LedgerError):
            self.add(impact="راسل a.b@example.com")

    def test_rejects_unknown_source_and_state(self):
        with self.assertRaises(ledger.LedgerError):
            self.add(source="whatsapp")
        with self.assertRaises(ledger.LedgerError):
            ledger.move(self.add(), "flying", path=self.path)

    def test_start_and_priority_are_mandatory(self):
        with self.assertRaises(ledger.LedgerError):
            self.add(start="")
        with self.assertRaises(ledger.LedgerError):
            self.add(priority="")
        with self.assertRaises(ledger.LedgerError):
            self.add(start="غداً")
        with self.assertRaises(ledger.LedgerError):
            self.add(urgent=True, priority="P2")  # الاستعجالُ P0

    def test_start_normalized_to_doha(self):
        item_id = self.add(start="2026-09-29T05:00+00:00")
        st = ledger.reduce_state(ledger.load_events(self.path))[item_id]
        self.assertEqual(st["start"], "2026-09-29T08:00+03:00")

    def test_order_priority_then_start(self):
        a = {"priority": "P2", "start": "2026-09-29T08:00+03:00"}; b = {"priority": "P1", "start": "2026-10-05T08:00+03:00"}
        c = {"priority": "P1", "start": "2026-09-30T08:00+03:00"}
        self.assertEqual(sorted([a, b, c], key=ledger.order_key), [c, b, a])

    def test_late_items(self):
        from datetime import datetime
        i = self.add(start="2026-09-01T08:00")
        late = ledger.late_items(ledger.reduce_state(ledger.load_events(self.path)), now=datetime.fromisoformat("2026-09-28T12:00+03:00"))
        self.assertEqual([x["id"] for x in late], [i])
        ledger.move(i, "in_progress", path=self.path)
        self.assertEqual(ledger.late_items(ledger.reduce_state(ledger.load_events(self.path)), now=datetime.fromisoformat("2026-09-28T12:00+03:00")), [])

    def test_wsjf_urgent_raises_urgency(self):
        base = {"scores": {"value": 3, "urgency": 1, "risk": 3, "size": 3}}
        self.assertLess(ledger.wsjf(base), ledger.wsjf({**base, "urgent": True}))

    def test_wsjf_smaller_size_ranks_higher(self):
        self.assertGreater(ledger.wsjf({"scores": {"size": 1}}), ledger.wsjf({"scores": {"size": 5}}))


class Routing(unittest.TestCase):
    def row(self, name, prs=0, over=False, mb=10):
        return {"session": name, "open_prs": prs, "overloaded": over, "unmerged_commits": 0, "context_mb": mb, "assignable": not over}

    def test_assign_least_loaded_executor(self):
        rows = [self.row("بصريّ · تخطيط لوحة المدير", 2), self.row("بصريّ · محور الجوال", 0)]
        r = ro.route("ui", rows, ROUTING)
        self.assertEqual((r["decision"], r["seat"]), ("assign", "بصريّ · محور الجوال"))

    def test_all_overloaded_requests_spawn_in_tab(self):
        rows = [self.row("بصريّ · تخطيط لوحة المدير", 5, True), self.row("بصريّ · محور الجوال", 4, True)]
        r = ro.route("ui", rows, ROUTING)
        self.assertEqual((r["decision"], r["tab"]), ("request_spawn", "exec_ui"))

    def test_missing_session_wakes_or_spawns(self):
        self.assertEqual(ro.route("schedule", [], ROUTING)["decision"], "wake_or_spawn")

    def test_file_owner_and_unknown(self):
        self.assertEqual(ro.route("qa_docs", [], ROUTING)["decision"], "file_owner")
        self.assertEqual(ro.route("nope", [], ROUTING)["decision"], "unknown_type")

    def test_guess_type_from_paths(self):
        self.assertEqual(ro.guess_type(["templates/a.html", "static/x.css"], ROUTING), "ui")
        self.assertIsNone(ro.guess_type(["zzz/none.txt"], ROUTING))


class ReviewWindow(unittest.TestCase):
    def item(self, i, tier, cat, area, pr, urgent=False, size=3, priority="P2"):
        return {"id": i, "tier": tier, "category": cat, "area": area, "pr": pr, "urgent": urgent, "priority": priority,
                "created": "2026-09-26T10:00:00+03:00", "scores": {"size": size}}

    def test_priority_orders_bundles_first(self):
        items = [self.item("low", "medium", "backend", "a", 1, priority="P3", size=1), self.item("hi", "medium", "backend", "b", 2, priority="P1", size=5)]
        self.assertEqual(rw.build_bundles(items)[0]["items"], ["hi"])

    def test_light_items_form_single_bundle(self):
        items = [self.item(f"L{n}", "light", "docs_only", "docs", n) for n in range(5)]
        b = rw.build_bundles(items)
        self.assertEqual((len(b), b[0]["light"], len(b[0]["items"])), (1, True, 5))

    def test_bundles_by_category_and_area_and_urgent_first(self):
        items = [self.item("A", "medium", "visible_ui", "templates", 1), self.item("B", "medium", "visible_ui", "templates", 2),
                 self.item("C", "high", "migration", "operations", 3, urgent=True)]
        b = rw.build_bundles(items)
        self.assertEqual(b[0]["items"], ["C"])
        self.assertEqual(sorted(b[1]["items"]), ["A", "B"])

    def test_cap_limits_window_and_reports_overflow(self):
        items = [self.item(f"I{n}", "medium", "backend", f"app{n}", n) for n in range(9)]
        md, mapping = rw.render(items, "normal")
        self.assertEqual(len(mapping), TH["owner_capacity"]["normal"]["per_window"])
        self.assertIn("للنافذة التالية", md)
        _, mapping_hi = rw.render(items, "elevated")
        self.assertEqual(len(mapping_hi), 9)

    def test_parse_reply_basic(self):
        r = rw.parse_reply("اعتمد: 1 2 4 | ملاحظات: 3 (لون الزر)، 5: الحجم | أجّل: 6", 6)
        self.assertEqual(r["approve"], [1, 2, 4])
        self.assertEqual(r["notes"], {3: "لون الزر", 5: "الحجم"})
        self.assertEqual(r["defer"], [6])

    def test_parse_reply_arabic_digits_and_all_except(self):
        self.assertEqual(rw.parse_reply("اعتمد: ١ ٢", 3)["approve"], [1, 2])
        r = rw.parse_reply("اعتمد الكلّ عدا 3 | ملاحظات: 3 (تعديل)", 4)
        self.assertEqual(r["approve"], [1, 2, 4])
        self.assertEqual(r["notes"], {3: "تعديل"})

    def test_approve_all_never_covers_high_tier(self):
        r = rw.parse_reply("اعتمد الكل", 4, high={2})
        self.assertEqual(r["approve"], [1, 3, 4])
        self.assertEqual(rw.parse_reply("اعتمد الكل | اعتمد: 2", 4, high={2})["approve"], [1, 2, 3, 4])

    def test_render_marks_high_bundles(self):
        items = [self.item("H", "high", "migration", "operations", 1), self.item("M", "medium", "backend", "core", 2)]
        md, _ = rw.render(items, "normal")
        self.assertIn("خطورةٌ عالية", md)

    def test_parse_reply_ignores_garbage_and_out_of_range(self):
        r = rw.parse_reply("مرحباً | اعتمد: 9 1", 3)
        self.assertEqual(r["approve"], [1])

    def test_apply_reply_records_trail(self):
        path = Path(tempfile.mkdtemp()) / "e.jsonl"
        a = ledger.add_item("owner", "ui", "س", "ص", "ع", path=path, start="2026-09-29T08:00", priority="P1")
        b = ledger.add_item("owner", "ui", "س", "ص", "ع", path=path, start="2026-09-29T08:00", priority="P2")
        done = rw.apply_reply({"approve": [1], "notes": {2: "غيّر اللون"}, "defer": []}, {"1": [a], "2": [b]}, path)
        st = ledger.reduce_state(ledger.load_events(path))
        self.assertEqual((st[a]["state"], st[b]["state"]), ("approved", "notes"))
        self.assertEqual(st[a]["approvals"][0]["by"], "owner")
        self.assertEqual(st[b]["notes"][0]["text"], "غيّر اللون")
        self.assertEqual(done["approved"], [a])


class EvidencePack(unittest.TestCase):
    PR = {"number": 700, "isDraft": False, "mergeStateStatus": "CLEAN", "additions": 10, "deletions": 2, "changedFiles": 2,
          "body": "اعتُمد من المالك على 8500 — 2026-09-26",
          "files": [{"path": "templates/wings/record.html"}, {"path": "static/css/custom/20-components.css"}],
          "statusCheckRollup": [{"conclusion": "SUCCESS", "name": "a"}, {"conclusion": "FAILURE", "name": "b"}, {"status": "IN_PROGRESS", "name": "c"}]}

    def test_pack_contents(self):
        md = ep.build_pack(self.PR)
        self.assertIn("#700", md)
        self.assertIn("متوسّطة", md)
        self.assertIn("1 خضراء، 1 فاشلة، 1 جارية", md)
        self.assertIn("الفاشل: b", md)
        self.assertIn("سطرُ اعتماد المالك في الوصف:** موجود", md)
        self.assertIn("غيرُ مقيس", md)  # لا أرقامَ مخترَعة
        self.assertIn("كلُّ الصفحات (CSS عامّ)", md)

    def test_missing_approval_line_flagged(self):
        md = ep.build_pack({**self.PR, "body": "لا شيء"})
        self.assertIn("غائب — لا يُدمج", md)

    def test_migration_adds_high_risk_section(self):
        pr = {**self.PR, "files": [{"path": "operations/migrations/0009_x.py"}]}
        self.assertIn("خطورةٌ عالية", ep.build_pack(pr))


class ArchiveCheck(unittest.TestCase):
    FACTS = {"title": "بصريّ · محور الجوال", "tree": "t", "open_prs": [], "cherry_plus": 0, "dirty_files": 0,
             "running": False, "handover_saved": True, "shared_with": 0}

    def test_parse_cherry(self):
        self.assertEqual(ac.parse_cherry("+ abc\n- def\n+ ghi\n"), (2, 1))
        self.assertEqual(ac.parse_cherry(""), (0, 0))

    def test_eligible_when_all_clear(self):
        r = ac.evaluate(self.FACTS, ac.permanent_titles(TABS))
        self.assertTrue(r["eligible"])
        self.assertIn("unarchive_session", r["reason"])

    def test_each_blocker_blocks(self):
        blocked = ac.permanent_titles(TABS)
        for patch in ({"open_prs": [5]}, {"cherry_plus": 1}, {"dirty_files": 2}, {"running": True}, {"handover_saved": False}, {"shared_with": 1}):
            r = ac.evaluate({**self.FACTS, **patch}, blocked)
            self.assertFalse(r["eligible"], patch)

    def test_only_core_sessions_are_blocked(self):
        blocked = ac.permanent_titles(TABS)
        self.assertEqual(set(blocked), set(TABS["session_policy"]["core_sessions"]))
        self.assertIn("0101 · المايسترو", blocked)
        self.assertNotIn("مسار Backend والبيانات", blocked)
        self.assertFalse(ac.evaluate({**self.FACTS, "title": "0601 · النشر على الإنتاج والدمج"}, blocked)["eligible"])


class BranchStatus(unittest.TestCase):
    """حالاتُ الحكم بطلب الفرع — ومنها حالةُ السحق التي كانت تُنتج إنذاراتٍ كاذبة (09-28)."""

    # تاريخٌ خطّيّ مصطنع: a ← b ← c ← d ؛ contains(x, y) = x سلفُ y
    ORDER = ["a", "b", "c", "d"]

    def contains(self, x, y):
        return x in self.ORDER and y in self.ORDER and self.ORDER.index(x) <= self.ORDER.index(y)

    def pr(self, n, state, head):
        return {"number": n, "state": state, "headRefOid": head}

    def judge(self, head, prs, ahead=4, dirty=0):
        return bs.classify_tree(head, "claude/x", ahead, dirty, prs, self.contains)

    def test_squash_merged_is_not_pending(self):
        # الحالةُ الحقيقيّة: vision-footer ← #714 — 4 إيداعاتٍ «خارج main» بالعدّ، لكنّ رأسها رأسُ طلبٍ مدموج
        r = self.judge("d", [self.pr(714, "MERGED", "d")])
        self.assertEqual((r["status"], r["prs"]), (bs.MERGED, [714]))
        self.assertNotIn(r["status"], bs.PENDING)

    def test_head_behind_merged_pr_is_merged(self):
        self.assertEqual(self.judge("b", [self.pr(1, "MERGED", "d")])["status"], bs.MERGED)

    def test_commits_after_merge_are_pending(self):
        r = self.judge("d", [self.pr(1, "MERGED", "b")])
        self.assertEqual((r["status"], r["prs"]), (bs.WORK_AFTER_MERGE, [1]))
        self.assertIn(r["status"], bs.PENDING)

    def test_merged_with_dirty_files(self):
        self.assertEqual(self.judge("d", [self.pr(1, "MERGED", "d")], dirty=3)["status"], bs.MERGED_DIRTY)

    def test_open_pr_wins(self):
        r = self.judge("d", [self.pr(1, "MERGED", "b"), self.pr(2, "OPEN", "d")])
        self.assertEqual((r["status"], r["prs"]), (bs.OPEN_PR, [2]))

    def test_closed_unmerged(self):
        r = self.judge("d", [self.pr(715, "CLOSED", "d")], ahead=1)
        self.assertEqual((r["status"], r["prs"]), (bs.CLOSED_UNMERGED, [715]))

    def test_no_pr_with_commits_is_orphan(self):
        self.assertEqual(self.judge("d", [], ahead=1)["status"], bs.NO_PR)
        self.assertEqual(self.judge("d", [], ahead=0, dirty=2)["status"], bs.NO_PR)

    def test_nothing_is_clean(self):
        self.assertEqual(self.judge("d", [], ahead=0)["status"], bs.CLEAN)

    def test_unknown_commit_is_not_ancestor(self):
        # رأسُ طلبٍ مدموجٍ غيرُ موجودٍ محلّياً لا يُحسب تغطية
        self.assertEqual(self.judge("d", [self.pr(1, "MERGED", "zzz")], ahead=1)["status"], bs.NO_PR)

    def test_merged_via_other_branch_is_not_pending(self):
        # الحالةُ الحقيقيّة: print-frame-migration-tmp بلا طلب، ورأسُه داخل #714 (فرعٌ آخر)
        r = bs.classify_tree("d", "claude/tmp", 6, 0, [], self.contains, elsewhere=[714])
        self.assertEqual((r["status"], r["prs"]), (bs.MERGED_ELSEWHERE, [714]))
        self.assertNotIn(r["status"], bs.PENDING)

    def test_merged_elsewhere_with_dirty_files_still_flags(self):
        r = bs.classify_tree("d", "claude/tmp", 6, 2, [], self.contains, elsewhere=[714])
        self.assertIn(r["status"], bs.PENDING)

    def test_own_open_pr_beats_elsewhere(self):
        r = bs.classify_tree("d", "claude/x", 3, 0, [self.pr(9, "OPEN", "d")], self.contains, elsewhere=[714])
        self.assertEqual(r["status"], bs.OPEN_PR)

    def test_branch_of(self):
        self.assertEqual(bs.branch_of({"branch": "refs/heads/claude/x"}), "claude/x")
        self.assertEqual(bs.branch_of({"detached": ""}), "")

    def test_describe_mentions_pr(self):
        self.assertIn("#714", bs.describe({"status": bs.MERGED, "prs": [714]}, 4, 0))


class ArchiveWithBranchStatus(unittest.TestCase):
    FACTS = {**ArchiveCheck.FACTS, "cherry_plus": 4}

    def test_squash_merged_tree_is_eligible_despite_cherry(self):
        r = ac.evaluate({**self.FACTS, "branch_status": bs.MERGED, "branch_prs": [714]}, ac.permanent_titles(TABS))
        self.assertTrue(r["eligible"], r["blockers"])
        self.assertIn("#714", r["reason"])

    def test_pending_statuses_block(self):
        for status in (bs.WORK_AFTER_MERGE, bs.CLOSED_UNMERGED, bs.NO_PR):
            r = ac.evaluate({**self.FACTS, "branch_status": status, "branch_prs": [9]}, ac.permanent_titles(TABS))
            self.assertFalse(r["eligible"], status)

    def test_unknown_status_falls_back_to_cherry(self):
        r = ac.evaluate({**self.FACTS, "branch_status": None, "branch_prs": []}, ac.permanent_titles(TABS))
        self.assertFalse(r["eligible"])
        self.assertTrue(any("git cherry" in b for b in r["blockers"]))


class Watch(unittest.TestCase):
    def test_memory_bands(self):
        th = TH["memory_free_gb"]
        self.assertEqual([wo.memory_band(x, th) for x in (3, 1.5, 0.7, 0.19)], ["green", "yellow", "red", "critical"])

    def test_age_and_wip(self):
        th = TH["flow"]
        self.assertEqual((wo.age_severity(2, th["oldest_open_pr_age_h"]), wo.age_severity(9, th["oldest_open_pr_age_h"]), wo.age_severity(30, th["oldest_open_pr_age_h"])), (None, "warn", "high"))
        self.assertIsNone(wo.wip_severity(8, th["system_wip_target"]))
        self.assertEqual(wo.wip_severity(11, th["system_wip_target"]), "warn")

    def test_backup_age_severity(self):
        self.assertIsNone(wo.backup_age_severity(5, False, 36))
        self.assertEqual(wo.backup_age_severity(40, False, 36), "high")
        self.assertEqual(wo.backup_age_severity(1, True, 36), "high")
        self.assertEqual(wo.backup_age_severity(None, False, 36), "high")  # الحالةُ التي بقيت صامتةً 4.5 أشهر

    def test_offline_collect_runs(self):
        self.assertIsInstance(wo.collect(TH, live=False), list)


class Registry(unittest.TestCase):
    def test_shipped_registry_is_consistent(self):
        self.assertEqual(vr.validate(TABS, ROUTING), [])

    def test_detects_duplicate_member_and_unknown_route(self):
        bad = json.loads(json.dumps(TABS))
        bad["tabs"][1]["members"].append("0101 · المايسترو")
        bad["tabs"][1]["live_cap"] = 9
        self.assertTrue(any("في تبويبَين" in p for p in vr.validate(bad, ROUTING)))
        bad_route = json.loads(json.dumps(ROUTING))
        bad_route["problem_types"]["ui"]["tab"] = "no_such_tab"
        self.assertTrue(any("تبويبٌ غيرُ موجود" in p for p in vr.validate(TABS, bad_route)))

    def test_session_name_carries_tab_number_and_core_must_exist(self):
        bad = json.loads(json.dumps(TABS))
        ui = next(t for t in bad["tabs"] if t["id"] == "reference")
        ui["members"] += ["جلسةٌ بلا رقم", "0405 · في غير مرحلتها", "0300 · تسلسلٌ صفريّ", "0309 · " + "اسمٌ طويلٌ جدّاً " * 4]; ui["live_cap"] = 9
        probs = vr.validate(bad, ROUTING)
        self.assertTrue(any("أربع خانات" in p for p in probs))
        self.assertTrue(any("لا تطابقان رقمَ مرحلته 03" in p for p in probs))
        self.assertTrue(any("يبدأ من 01" in p for p in probs))
        self.assertTrue(any("أطولُ من 40" in p for p in probs))
        bad2 = json.loads(json.dumps(TABS))
        bad2["tabs"][0]["members"].remove("0103 · الحوكمة")
        self.assertTrue(any("جلسةُ النواة" in p for p in vr.validate(bad2, ROUTING)))

    def test_empty_tab_is_allowed(self):
        # المرحلةُ 04 تحمل من 0 إلى 10 جلساتٍ مرنة (D-51م)، فإفراغُها سليم؛ والمراحلُ الأخرى فيها نواةٌ ثابتةٌ لا تُفرَغ
        tabs = json.loads(json.dumps(TABS)); next(t for t in tabs["tabs"] if t.get("number") == "04")["members"] = []
        self.assertEqual(vr.validate(tabs, ROUTING), [])

    def test_flexible_sessions_live_in_04_only(self):
        tabs = json.loads(json.dumps(TABS))
        review = next(t for t in tabs["tabs"] if t["id"] == "review")
        review["members"].append("0409 · جدول: مهمّةٌ في غير 04"); review["live_cap"] = 9
        self.assertTrue(any("لا تطابقان رقمَ مرحلته 05" in p for p in vr.validate(tabs, ROUTING)))

    def test_core_to_open_is_listed_but_not_required_live(self):
        # جلسةُ نواةٍ لم تُفتح بعدُ تُدرج في core_to_open ولا يلزمها تبويبٌ ولا حياة؛ نبنيها على نسخةٍ لأنّ الحالَ الحيّة تتغيّر بالفتح
        tabs = json.loads(json.dumps(TABS)); sp = tabs["session_policy"]; name = "0702 · مراقبات الجودة"
        if name in sp["core_sessions"]:
            sp["core_sessions"].remove(name)
        sp["core_to_open"] = [name]
        for t in tabs["tabs"]:
            if name in t.get("members", []):
                t["members"].remove(name)
        self.assertEqual(vr.validate(tabs, ROUTING), [])

    def test_routes_point_to_specialties(self):
        ids = {s["id"] for s in TABS["specialties"]}
        self.assertTrue({"exec_ui", "exec_schedule", "exec_admin"} <= ids)

    def test_live_diff(self):
        p = vr.validate(TABS, ROUTING, ["جلسةٌ جديدة"])
        self.assertTrue(any("غيرُ مسجَّلة" in x for x in p) and any("بلا جلسةٍ حيّة" in x for x in p))

    def test_scheduled_task_sessions_are_ignored(self):
        tabs = json.loads(json.dumps(TABS)); tabs["scheduled_task_title_prefixes"] = ["قراءة RK"]
        seats = [m for t in tabs["tabs"] for m in t["members"]]
        self.assertEqual(vr.validate(tabs, ROUTING, seats + ["قراءة RK1..RK3 الأسبوعيّة"]), [])

    def test_charters_render_all_tabs(self):
        import render_charters
        md = render_charters.render(TABS)
        for tab in TABS["tabs"]:
            self.assertIn(tab["name"], md)


if __name__ == "__main__":
    unittest.main()
