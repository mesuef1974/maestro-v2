"""اختباراتُ flow_watch (W-20261016-019) بدفترٍ تجريبيّ لا الحقيقيّ:  python -m unittest tools.test_flow_watch"""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flow_watch as fw  # noqa: E402

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone(timedelta(hours=3)))
TH = fw.Thresholds()


def ts(minutes_ago):
    return (NOW - timedelta(minutes=minutes_ago)).isoformat()


def created(cid, **extra):
    return {
        "kind": "created",
        "id": cid,
        "ts": ts(100000),
        "data": {"spec_tier": "full", **extra},
    }


def state(cid, st, ago, by="0101", **extra):
    return {
        "kind": "state",
        "id": cid,
        "ts": ts(ago),
        "data": {"state": st, "by": by, **extra},
    }


def note(cid, text, ago):
    return {"kind": "note", "id": cid, "ts": ts(ago), "data": {"text": text}}


def pr(number, text, checks="SUCCESS", pr_state="OPEN", age=200, draft=False):
    return {
        "number": number,
        "title": text,
        "body": "",
        "isDraft": draft,
        "state": pr_state,
        "mergeStateStatus": "CLEAN",
        "statusCheckRollup": [
            {
                "__typename": "CheckRun",
                "name": "c",
                "status": "COMPLETED",
                "conclusion": checks,
                "completedAt": ts(age),
                "workflowName": "w",
            }
        ],
        "createdAt": ts(age).replace("+03:00", "+03:00"),
    }


PREVIEW_OK = "الوضع:        follow\nالانتظار:      لا أحد\nالخادم:       running\n"
PREVIEW_QUEUE = (
    "الوضع:        follow\nالانتظار:      تُثبَّت آليّاً\n"
    "    1. wtree-a — 30 دقيقة (منذ 200 دقيقة)\n    2. wtree-b — 30 دقيقة (منذ 10 دقيقة)\nالإيقاع: x\n"
)


def by_case(rows, case):
    return [r for r in rows if r.case == case or case in r.also]


class TestSevenCases(unittest.TestCase):
    def test_1_approved_not_pushed_over_30_minutes(self):
        ev = [
            created("A"),
            state("A", "approved", 45, held_by="0701"),
            created("B"),
            state("B", "approved", 10),
        ]
        rows = by_case(fw.collect(ev, [], PREVIEW_OK, NOW, TH), 1)
        self.assertEqual([r.ref for r in rows], ["A"])
        self.assertEqual((rows[0].severity, rows[0].owner), ("yellow", "0701"))

    def test_1_severity_turns_red_at_double_the_threshold(self):
        ev = [created("A"), state("A", "approved", 61)]
        self.assertEqual(
            by_case(fw.collect(ev, [], PREVIEW_OK, NOW, TH), 1)[0].severity, "red"
        )

    def test_2_pushed_not_merged_with_pr_states(self):
        ev = [
            created("A"),
            state("A", "pushed", 300),
            created("B"),
            state("B", "pushed", 300),
            created("C"),
            state("C", "pushed", 300),
            created("D"),
            state("D", "pushed", 60),
        ]
        prs = [pr(1, "فرع B W-B"), pr(2, "فرع C W-C", pr_state="MERGED")]
        prs[0]["title"], prs[1]["title"] = "طلب B", "طلب C"
        prs[0]["body"], prs[1]["body"] = "B", "C"
        rows = {
            r.ref: r.action
            for r in by_case(fw.collect(ev, prs, PREVIEW_OK, NOW, TH), 2)
        }
        self.assertEqual(set(rows), {"A", "B", "C"})  # D أحدث من العتبة
        self.assertIn("افتحي", rows["A"])
        self.assertIn("ادمجي", rows["B"])
        self.assertIn("حدّثي الدفتر", rows["C"])

    def test_3_red_and_pending_pull_requests_over_60_minutes(self):
        prs = [
            pr(10, "W-20261001-001 أحمر", checks="FAILURE", age=90),
            pr(11, "معلّق", checks="", age=90),
            pr(12, "أحمر حديث", checks="FAILURE", age=20),
            pr(13, "أخضر", age=500),
            pr(14, "مسودة", checks="FAILURE", age=500, draft=True),
        ]
        prs[1]["statusCheckRollup"] = [
            {
                "__typename": "CheckRun",
                "name": "c",
                "status": "IN_PROGRESS",
                "conclusion": "",
                "startedAt": ts(90),
                "workflowName": "w",
            }
        ]
        rows = {r.ref: r for r in by_case(fw.collect([], prs, PREVIEW_OK, NOW, TH), 3)}
        self.assertEqual(set(rows), {"#10 (W-20261001-001)", "#11"})
        self.assertEqual(rows["#10 (W-20261001-001)"].severity, "red")
        self.assertEqual(rows["#11"].severity, "yellow")

    def test_4_routed_stale_or_not_full(self):
        ev = [
            created("A"),
            state("A", "routed", 1500, held_by="0403"),
            created("B", spec_tier="basic"),
            state("B", "routed", 30, held_by="0403"),
            created("C"),
            state("C", "routed", 60, held_by="0403"),
        ]
        rows = {r.ref: r for r in by_case(fw.collect(ev, [], PREVIEW_OK, NOW, TH), 4)}
        self.assertEqual(set(rows), {"A", "B"})
        self.assertEqual(rows["B"].owner, "0301")
        self.assertIn("0403", rows["A"].owner)

    def test_5_preview_queue_and_expired_pin(self):
        rows = by_case(fw.collect([], [], PREVIEW_QUEUE, NOW, TH), 5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            (rows[0].ref, rows[0].age_min, rows[0].owner), ("wtree-a", 200, "0501")
        )
        expired = by_case(
            fw.collect([], [], "الوضع:        pin w1 — منتهٍ\n", NOW, TH), 5
        )
        self.assertEqual(expired[0].severity, "red")
        self.assertEqual(by_case(fw.collect([], [], PREVIEW_OK, NOW, TH), 5), [])

    def test_6_ready_without_evidence_pack(self):
        ev = [
            created("A"),
            state("A", "ready_for_review", 120),
            created("B"),
            state("B", "ready_for_review", 120),
            note("B", "(0502) أدلة 1234 في evidence/B/ ✔ 6 لقطات", 30),
            created("C"),
            state("C", "ready_for_review", 120),
            note("C", "(0502) أدلة قديمة", 500),
            created("D"),
            state("D", "ready_for_review", 20),
        ]
        refs = sorted(
            r.ref for r in by_case(fw.collect(ev, [], PREVIEW_OK, NOW, TH), 6)
        )
        self.assertEqual(
            refs, ["A", "C"]
        )  # B فيها حزمة بعد الدخول، وC حزمتُها قبل الدخول، وD أحدث من العتبة

    def test_7_silent_session_after_handoff(self):
        ev = [
            created("A"),
            state("A", "routed", 90, held_by="0403"),
            created("B"),
            state("B", "routed", 90, held_by="0403"),
            note("B", "(0403) بدأت", 40),
            created("C"),
            state("C", "routed", 90, held_by="0403"),
            state("C", "in_progress", 40, by="0403"),
            created("D"),
            state("D", "ready_for_review", 90),
            created("E"),
            state("E", "routed", 10, held_by="0403"),
        ]
        refs = sorted(
            r.ref for r in by_case(fw.collect(ev, [], PREVIEW_OK, NOW, TH), 7)
        )
        self.assertEqual(refs, ["A", "D"])
        self.assertEqual(
            {
                r.ref: r.owner
                for r in by_case(fw.collect(ev, [], PREVIEW_OK, NOW, TH), 7)
            }["D"].split(" / ")[-1],
            "0501",
        )


class TestCollapse(unittest.TestCase):
    def test_card_in_two_cases_is_one_row(self):
        ev = [created("A"), state("A", "ready_for_review", 120)]
        rows = [r for r in fw.collect(ev, [], PREVIEW_OK, NOW, TH) if r.ref == "A"]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].case, rows[0].also), (6, (7,)))

    def test_per_case_cap_summarises_the_rest(self):
        ev = []
        for i in range(8):
            ev += [created(f"W{i}"), state(f"W{i}", "approved", 100 + i)]
        rows = fw.collect(ev, [], PREVIEW_OK, NOW, TH)
        self.assertEqual(sum(1 for r in rows if r.case == 1 and r.ref != "—"), 3)
        self.assertTrue(any(r.ref == "—" and "+5 أخرى" in r.subject for r in rows))
        self.assertEqual(
            len(
                [
                    r
                    for r in fw.collect(ev, [], PREVIEW_OK, NOW, TH, cap=0)
                    if r.case == 1
                ]
            ),
            8,
        )

    def test_old_cards_fold_into_one_summary_row(self):
        ev = []
        for i in range(2):
            ev += [created(f"O{i}"), state(f"O{i}", "pushed", 6000 + i)]
        rows = fw.collect(ev, None, PREVIEW_OK, NOW, TH)
        old = [r for r in rows if "قديمٌ" in r.subject]
        self.assertEqual(len(old), 1)
        self.assertIn("2 بطاقة", old[0].subject)


class TestCase8And9(unittest.TestCase):
    def test_github_event_overrides_ledger_and_is_flagged(self):
        ev = [created("W-20261016-001"), state("W-20261016-001", "pushed", 10)]
        recon = [
            {
                "number": 7,
                "state": "MERGED",
                "title": "x (W-20261016-001)",
                "headRefName": "b",
                "body": "",
            }
        ]
        rows = by_case(
            fw.collect(ev, [], PREVIEW_OK, NOW, TH, recon, reconcile=True), 8
        )
        self.assertEqual(len(rows), 1)
        self.assertIn("مخالفة", rows[0].subject)

    def test_ledger_ahead_of_github_is_red(self):
        ev = [created("W-20261016-002"), state("W-20261016-002", "published", 10)]
        recon = [
            {
                "number": 9,
                "state": "CLOSED",
                "title": "(W-20261016-002)",
                "headRefName": "b",
                "body": "",
            }
        ]
        rows = by_case(
            fw.collect(ev, [], PREVIEW_OK, NOW, TH, recon, reconcile=True), 8
        )
        self.assertEqual(rows[0].severity, "red")

    def test_case8_without_gh_is_unmeasured(self):
        rows = by_case(fw.collect([], [], PREVIEW_OK, NOW, TH, None, reconcile=True), 8)
        self.assertEqual(rows[0].severity, "unmeasured")

    def test_stalled_merge_queue_green_approved_pr(self):
        p = pr(5, "ميزة (W-20261016-003)", age=200)
        p["body"] = "اعتُمد من المالك على 8500"
        rows = by_case(fw.collect([], [p], PREVIEW_OK, NOW, TH), 9)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].ref, "W-20261016-003")

    def test_reading_only_no_ledger_change(self):
        ev = [created("W-1"), state("W-1", "pushed", 10)]
        before = list(ev)
        fw.collect(ev, [], PREVIEW_OK, NOW, TH, [], reconcile=True)
        self.assertEqual(ev, before)


class TestUnmeasuredAndOutput(unittest.TestCase):
    def test_missing_tools_print_unmeasured_not_healthy(self):
        ev = [created("A"), state("A", "pushed", 300)]
        rows = fw.collect(ev, None, None, NOW, TH)
        self.assertEqual(
            {r.case for r in rows if r.severity == "unmeasured"}, {2, 3, 5}
        )
        self.assertIn(fw.UNMEASURED, fw.render_text(rows))

    def test_rows_are_sorted_by_severity_then_age(self):
        ev = [
            created("A"),
            state("A", "approved", 45),
            created("B"),
            state("B", "approved", 500),
        ]
        sev = [r.severity for r in fw.collect(ev, [], PREVIEW_OK, NOW, TH)]
        self.assertEqual(sev, sorted(sev, key=fw.SEVERITY_ORDER.get))

    def test_html_is_arabic_rtl_and_escapes(self):
        rows = [fw.Row("red", 1, "<b>x</b>", 5, "0701", "اعمل", "W-1")]
        out = fw.render_html(rows, NOW)
        self.assertIn("dir='rtl'", out)
        self.assertIn("&lt;b&gt;", out)


class TestReadOnly(unittest.TestCase):
    def test_a_run_leaves_the_ledger_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            import json

            ev = [created("A"), state("A", "approved", 45)]
            path.write_text(
                "\n".join(json.dumps(e, ensure_ascii=False) for e in ev) + "\n",
                encoding="utf-8",
            )
            before = path.read_bytes()
            old = os.environ.get("LEDGER_PATH")
            os.environ["LEDGER_PATH"] = str(path)
            try:
                with contextlib.redirect_stdout(
                    io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
                ):
                    code = fw.main(["--no-live", "--now", NOW.isoformat()])
            finally:
                if old is None:
                    os.environ.pop("LEDGER_PATH")
                else:
                    os.environ["LEDGER_PATH"] = old
            self.assertEqual(code, 0)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(
                sorted(p.name for p in Path(tmp).iterdir()), ["events.jsonl"]
            )

    def test_unreadable_ledger_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            # بايتاتٌ لا تُفكّ بـUTF-8: دفترٌ غيرُ مقروء. (السطرُ التالف وحده يُهمَل ويُحصى: الاختبار التالي)
            path.write_bytes(b"\xff\xfe\x00")
            os.environ["LEDGER_PATH"] = str(path)
            try:
                with contextlib.redirect_stdout(
                    io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
                ):
                    self.assertEqual(fw.main(["--no-live"]), 1)
            finally:
                os.environ.pop("LEDGER_PATH")

    def test_one_corrupt_line_prints_unmeasured_and_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            import json

            good = json.dumps(created("A"), ensure_ascii=False)
            path.write_text(good + "\n{ليس json\n", encoding="utf-8")
            old = os.environ.get("LEDGER_PATH")
            os.environ["LEDGER_PATH"] = str(path)
            raw = io.BytesIO()
            buf = io.TextIOWrapper(raw, encoding="utf-8")
            try:
                with contextlib.redirect_stdout(buf):
                    code = fw.main(["--no-live", "--now", NOW.isoformat()])
            finally:
                if old is None:
                    os.environ.pop("LEDGER_PATH")
                else:
                    os.environ["LEDGER_PATH"] = old
            self.assertEqual(code, 2)
            buf.flush()
            self.assertIn("غير مقيس: 1 سطراً تالفاً", raw.getvalue().decode("utf-8"))


class TestChangesOnly(unittest.TestCase):
    """W-20261019-019: المراقبةُ (Monitor) تُبلغ عند التغيّر فقط، وتبقى قراءةً فقط."""

    def run_main(self, events, extra, now=NOW):
        import json
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n", encoding="utf-8")
            state_file = Path(tmp) / "state.json"
            os.environ["LEDGER_PATH"] = str(path)
            raw = io.BytesIO()
            buf = io.TextIOWrapper(raw, encoding="utf-8")
            try:
                with contextlib.redirect_stdout(buf), mock.patch.object(fw, "fetch_prs", return_value=[]), mock.patch.object(
                    fw, "read_preview_status", return_value=""
                ), mock.patch.object(fw.ledger_reconcile, "fetch_prs", return_value=[]):
                    code = fw.main(["--changes-only", "--state-file", str(state_file), "--now", now.isoformat(), *extra])
            finally:
                os.environ.pop("LEDGER_PATH", None)
            buf.flush()
            return code, raw.getvalue().decode("utf-8")

    def test_healthy_ledger_prints_nothing(self):
        code, out = self.run_main([created("A"), state("A", "published", 5)], [])
        self.assertEqual((code, out), (0, ""))

    def test_new_row_prints_once_then_silent(self):
        ev = [created("A"), state("A", "approved", 45)]
        _, first = self.run_main(ev, [])
        self.assertIn("A", first)

    def test_repeat_inside_window_is_silent(self):
        import json
        from unittest import mock

        ev = [created("A"), state("A", "approved", 45)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in ev) + "\n", encoding="utf-8")
            sf = Path(tmp) / "state.json"
            os.environ["LEDGER_PATH"] = str(path)
            outs = []
            try:
                for _ in range(2):
                    raw = io.BytesIO()
                    buf = io.TextIOWrapper(raw, encoding="utf-8")
                    with contextlib.redirect_stdout(buf), mock.patch.object(fw, "fetch_prs", return_value=[]), mock.patch.object(
                        fw, "read_preview_status", return_value=""
                    ), mock.patch.object(fw.ledger_reconcile, "fetch_prs", return_value=[]):
                        fw.main(["--changes-only", "--state-file", str(sf), "--now", NOW.isoformat()])
                    buf.flush()
                    outs.append(raw.getvalue().decode("utf-8"))
            finally:
                os.environ.pop("LEDGER_PATH", None)
        self.assertIn("A", outs[0])
        self.assertEqual(outs[1], "")

    def test_loop_requires_changes_only(self):
        with self.assertRaises(SystemExit):
            fw.main(["--loop", "--no-live"])


if __name__ == "__main__":
    unittest.main()
