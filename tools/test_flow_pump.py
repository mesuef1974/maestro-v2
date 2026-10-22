"""اختباراتُ مضخّة التدفّق:  python -m pytest test_flow_pump.py"""

import io
import json
import os
import re
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import flow_pump as fp


def _item(state="ready_for_review", *texts):
    return {"state": state, "notes": [{"text": t} for t in texts]}


class ReadyHead(unittest.TestCase):
    def test_the_last_announced_head_wins(self):
        item = _item("ready_for_review", "جاهزٌ للمعاينة بالرأس aaaaaaaa11", "رأسٌ جديد: الرأس bbbbbbbb22")
        self.assertEqual(fp.ready_head(item), "bbbbbbbb")

    def test_a_card_without_an_announced_head_has_none(self):
        self.assertIsNone(fp.ready_head(_item("ready_for_review", "ملاحظةٌ بلا رأس")))
        self.assertIsNone(fp.ready_head({"state": "ready_for_review"}))

    def test_a_head_shorter_than_eight_hex_is_not_taken(self):
        self.assertIsNone(fp.ready_head(_item("ready_for_review", "بالرأس abc123")))


class ApprovePass(unittest.TestCase):
    STATES = {
        "W-1": _item("ready_for_review", "جاهزٌ للمعاينة بالرأس aaaaaaaa"),
        "W-2": _item("ready_for_review", "بلا رأس"),
        "W-3": _item("approved", "بالرأس cccccccc"),
    }

    def test_only_ready_cards_are_considered(self):
        with mock.patch.object(fp, "approval_ok", return_value=False) as ok:
            lines = fp.approve_pass(self.STATES, apply=False)
        self.assertEqual(ok.call_count, 1)  # W-1 وحدَها لها رأس
        self.assertEqual(len(lines), 2)

    def test_a_card_without_approval_proof_waits_and_is_never_moved(self):
        with (
            mock.patch.object(fp, "approval_ok", return_value=False),
            mock.patch.object(fp.subprocess, "run") as run,
        ):
            lines = fp.approve_pass({"W-1": self.STATES["W-1"]}, apply=True)
        run.assert_not_called()
        self.assertIn("ينتظر", lines[0])

    def test_dry_run_reports_but_does_not_move(self):
        with (
            mock.patch.object(fp, "approval_ok", return_value=True),
            mock.patch.object(fp.subprocess, "run") as run,
        ):
            lines = fp.approve_pass({"W-1": self.STATES["W-1"]}, apply=False)
        run.assert_not_called()
        self.assertIn("(عرض)", lines[0])

    def test_apply_moves_with_the_proven_head(self):
        done = SimpleNamespace(returncode=0, stdout="ok", stderr="")
        with (
            mock.patch.object(fp, "approval_ok", return_value=True),
            mock.patch.object(fp.subprocess, "run", return_value=done) as run,
        ):
            lines = fp.approve_pass({"W-1": self.STATES["W-1"]}, apply=True)
        cmd = run.call_args.args[0]
        self.assertIn("approved", cmd)
        self.assertEqual(cmd[cmd.index("--head") + 1], "aaaaaaaa")
        self.assertTrue(lines[0].endswith("✔"))

    def test_a_ledger_refusal_is_reported_not_forced(self):
        refused = SimpleNamespace(returncode=1, stdout="", stderr="مرفوض: دليلٌ بصريّ ناقص")
        with (
            mock.patch.object(fp, "approval_ok", return_value=True),
            mock.patch.object(fp.subprocess, "run", return_value=refused),
        ):
            lines = fp.approve_pass({"W-1": self.STATES["W-1"]}, apply=True)
        self.assertIn("✘", lines[0])
        self.assertIn("دليلٌ بصريّ", lines[0])


class Main(unittest.TestCase):
    def test_skip_excludes_cards_from_both_stages(self):
        seen = {}

        def fake_pass(states, apply):
            seen["approve"] = sorted(states)
            return []

        fake_states = {"W-1": _item(), "W-2": _item()}
        tmp = Path(tempfile.mkdtemp())
        with (
            mock.patch.object(fp, "LOCK", tmp / "p.lock"),
            mock.patch.object(fp, "OFF", tmp / "p.off"),
            mock.patch.object(fp, "LOG", tmp / "p.log"),
            mock.patch.object(fp.ledger, "load_events", return_value=[]),
            mock.patch.object(fp.ledger, "reduce_state", return_value=fake_states),
            mock.patch.object(fp, "approve_pass", side_effect=fake_pass),
            mock.patch.object(fp.ledger_sync, "plan", side_effect=lambda st, *r, **k: sorted(st)) as plan,
            mock.patch.object(fp.ledger_sync, "cycle", side_effect=lambda apply, n: (fp.ledger_sync.plan(fake_states), 0)[1]),
        ):
            code = fp.main(["--skip", "W-1"])
        self.assertEqual(code, 0)
        self.assertEqual(seen["approve"], ["W-2"])
        self.assertTrue(plan.called)


class HeadPattern(unittest.TestCase):
    def test_the_three_phrasings_are_read(self):
        for phrase in ("بالرأس", "للرأس", "الرأس"):
            self.assertEqual(fp.ready_head(_item("ready_for_review", f"{phrase} deadbeef99")), "deadbeef")

    def test_a_full_forty_hex_head_is_cut_to_eight(self):
        self.assertEqual(fp.ready_head(_item("ready_for_review", "الرأس " + "a1" * 20)), "a1a1a1a1")


class Lock(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [
            mock.patch.object(fp, "LOCK", self.tmp / "p.lock"),
            mock.patch.object(fp, "OFF", self.tmp / "p.off"),
            mock.patch.object(fp, "LOG", self.tmp / "p.log"),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_a_free_lock_is_taken_once(self):
        self.assertTrue(fp._lock())
        self.assertFalse(fp._lock())

    def test_a_stale_lock_is_treated_as_dead_and_replaced(self):
        fp.LOCK.write_text("")
        old = time.time() - fp.STALE_LOCK_S - 5
        os.utime(fp.LOCK, (old, old))
        self.assertTrue(fp._lock())

    def test_a_fresh_lock_makes_the_cycle_skip_without_touching_the_ledger(self):
        fp.LOCK.write_text("")
        with mock.patch.object(fp, "_run") as run:
            self.assertEqual(fp.main([]), 0)
        run.assert_not_called()
        self.assertTrue(fp.LOCK.exists())  # قفلُ غيرِها لا يُحذف

    def test_the_lock_is_released_even_if_the_cycle_raises(self):
        with mock.patch.object(fp, "_run", side_effect=RuntimeError("x")):
            with self.assertRaises(RuntimeError):
                fp.main([])
        self.assertFalse(fp.LOCK.exists())


class OffSwitch(unittest.TestCase):
    """(الموجة 0.3، D-453م) مفتاحُ الإيقاف ledger/flow_pump.off تفحصه المضخّةُ نفسُها لا الخطّافُ وحده."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for name, rel in (("LOCK", "p.lock"), ("LOG", "p.log"), ("OFF", "p.off")):
            p = mock.patch.object(fp, name, self.tmp / rel)
            p.start()
            self.addCleanup(p.stop)

    def test_the_default_path_is_the_one_the_hook_checks(self):
        import flow_pump_hook as hook

        self.assertEqual(Path(hook.__file__).resolve().parent.parent / "ledger" / "flow_pump.off", hook.OFF)
        self.assertEqual(fp.HERE.parent / "ledger" / "flow_pump.off", hook.OFF)

    def test_apply_does_not_run_while_the_switch_exists(self):
        fp.OFF.write_text("")
        with mock.patch.object(fp, "_run") as run:
            out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
            with mock.patch("sys.stdout", out):
                self.assertEqual(fp.main(["--apply"]), 0)
            out.flush()
            printed = out.buffer.getvalue().decode("utf-8")
        run.assert_not_called()
        self.assertIn("مفتاحُ الإيقاف", printed)
        self.assertFalse(fp.LOCK.exists())  # لم تأخذ القفلَ ولا كتبت شيئاً

    def test_a_dry_run_is_also_refused_so_no_trigger_can_spin_the_pump(self):
        fp.OFF.write_text("")
        with mock.patch.object(fp, "_run") as run:
            self.assertEqual(fp.main([]), 0)
        run.assert_not_called()

    def test_without_the_switch_the_cycle_runs(self):
        with mock.patch.object(fp, "_run", return_value=0) as run:
            self.assertEqual(fp.main(["--apply"]), 0)
        run.assert_called_once()

    def test_the_switch_is_not_removed_or_written_by_the_pump(self):
        fp.OFF.write_text("حرجٌ")
        with mock.patch.object(fp, "_run"):
            fp.main(["--apply"])
        self.assertEqual(fp.OFF.read_text(), "حرجٌ")


class PublishStage(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        for name in ("LOCK", "LOG", "OFF"):
            p = mock.patch.object(fp, name, tmp / name)
            p.start()
            self.addCleanup(p.stop)

    def _run(self, argv):
        real_move = fp.ledger.move
        seen = {}

        def cycle(apply, n):
            fp.ledger.move("W-1", "published", note="x")
            return 0

        with (
            mock.patch.object(fp.ledger, "load_events", return_value=[]),
            mock.patch.object(fp.ledger, "reduce_state", return_value={}),
            mock.patch.object(fp.ledger, "move", side_effect=lambda *a, **k: seen.update(k)) as mv,
            mock.patch.object(fp.ledger_sync, "cycle", side_effect=cycle),
        ):
            code = fp.main(argv)
        self.assertIsNotNone(real_move)
        return code, seen, mv

    def test_every_ledger_sync_move_carries_the_pump_identity(self):
        code, seen, _ = self._run(["--apply"])
        self.assertEqual(code, 0)
        self.assertEqual(seen["by"], fp.SENDER)

    def test_an_explicit_by_is_not_overridden(self):
        called = {}
        with (
            mock.patch.object(fp.ledger, "load_events", return_value=[]),
            mock.patch.object(fp.ledger, "reduce_state", return_value={}),
            mock.patch.object(fp.ledger, "move", side_effect=lambda *a, **k: called.update(k)),
            mock.patch.object(
                fp.ledger_sync, "cycle", side_effect=lambda apply, n: fp.ledger.move("W-1", "merged", by="0601") and 0
            ),
        ):
            fp.main(["--apply"])
        self.assertEqual(called["by"], "0601")

    def test_a_dry_run_writes_no_log_line(self):
        with (
            mock.patch.object(fp.ledger, "load_events", return_value=[]),
            mock.patch.object(fp.ledger, "reduce_state", return_value={}),
            mock.patch.object(fp.ledger_sync, "cycle", return_value=0),
        ):
            fp.main([])
        self.assertFalse(fp.LOG.exists())

    def test_an_applied_cycle_appends_one_log_line_with_the_result(self):
        with (
            mock.patch.object(fp.ledger, "load_events", return_value=[]),
            mock.patch.object(fp.ledger, "reduce_state", return_value={}),
            mock.patch.object(fp.ledger_sync, "cycle", return_value=0),
        ):
            fp.main(["--apply"])
        self.assertIn("rc=0", fp.LOG.read_text(encoding="utf-8"))


CARD = "W-20261020-001"
FULL = "abcdef12" + "0" * 32
OWNER_ROW = f"| 2026-10-20 09:00 | 0101 (إفادةُ جلسة) مصدره: مباشر | {CARD} | «اعتمد» | {CARD} @abcdef12 |"
D443_ROW = f"| 2026-10-20 09:00 | 0101 (إفادةُ جلسة) مصدره: مباشر | بتفويض D-443م | «اعتماد الراس عندك الا المستثنى يعرض على المالك فقط» | {CARD} @abcdef12 |"

# منسوخةٌ حرفيّاً من D:/shschool_mvp (origin/main): scripts/auto_merge_gate.py APPROVAL وscripts/pr_approval_head_check.py
# MANDATE/OWNER_HEAD/same_head/verdict وscripts/pr_evidence.py DELEGATED — سطرُ المضخّة يجب أن يُقرأ رأسُه في فحص المستودع نفسه.
B_APPROVAL = re.compile(r"اعتُمد من المالك (?:على 8500|مباشرةً بلا معاينة 8500) — \d{4}-\d{2}-\d{2}")
B_MANDATE = re.compile(r"اعتُمد بتكليف المالك D-\d+م عبر (?:0101|0501) — \d{4}-\d{2}-\d{2} — الرأس ([0-9a-f]{7,40})")
B_OWNER_HEAD = re.compile(B_APPROVAL.pattern + r"(?: — الرأس ([0-9a-f]{7,40}))?")
B_DELEGATED = re.compile(r"اعتُمد بتفويض (?:0101|0501) على الرأس ([0-9a-f]{8,40}) — \d{4}-\d{2}-\d{2}")


def b_same_head(written, head):
    written, head = written.lower(), head.lower()
    return len(written) >= 7 and len(head) >= 7 and (head.startswith(written) or written.startswith(head))


def b_verdict(body, head):
    owner = list(B_OWNER_HEAD.finditer(body or ""))
    delegated = B_DELEGATED.findall(body or "") + B_MANDATE.findall(body or "")
    written = [m.group(1) for m in owner if m.group(1)] + delegated
    return "ok" if any(b_same_head(w, head) for w in written) else "no"


def _pr(num=7, head=FULL, card=CARD, body="ملخّص الطلب", **kw):
    return {"number": num, "headRefOid": head, "headRefName": "claude/x", "title": f"{card}: عمل", "body": body,
            "labels": [], "files": [{"path": "school/x.py"}], "changedFiles": 1, "baseRefName": "main",
            "isDraft": False, "autoMergeRequest": None, **kw}


def _states(state="pushed", head="abcdef12"):
    return {CARD: {"state": state, "approved_head": head, "approvals": [{"ts": "2026-10-20T10:00:00+03:00"}], "notes": []}}


class FakeSh:
    def __init__(self, rc=0, out=""):
        self.calls, self.bodies, self.rc, self.out = [], [], rc, out

    def __call__(self, cmd, cwd=None):
        self.calls.append(cmd)
        if cmd[:3] == ["gh", "pr", "edit"]:
            self.bodies.append(Path(cmd[cmd.index("--body-file") + 1]).read_text(encoding="utf-8"))
        return self.rc, self.out


class StructuredReadyHead(unittest.TestCase):
    def test_the_structured_field_wins_over_notes(self):
        item = {**_item("ready_for_review", "الرأس bbbbbbbb"), "ready_head": "aaaaaaaa"}
        self.assertEqual(fp.ready_head(item), "aaaaaaaa")

    def test_an_empty_structured_field_withdraws_the_announcement(self):
        self.assertIsNone(fp.ready_head({**_item("ready_for_review", "الرأس bbbbbbbb"), "ready_head": ""}))

    def test_the_at_form_of_legacy_notes_is_read(self):
        for text in ("جاهز @deadbeef99", "جاهز ＠ deadbeef"):
            self.assertEqual(fp.ready_head(_item("ready_for_review", text)), "deadbeef")


class WaivePass(unittest.TestCase):
    def test_a_new_declared_head_of_an_approved_card_is_waived_auto_by_0101(self):
        st = {CARD: {"state": "ready_for_review", "approved_head": "aaaaaaaa", "ready_head": "bbbbbbbb"}}
        done = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(fp.subprocess, "run", return_value=done) as run:
            lines = fp.waive_pass(st, apply=True)
        cmd = run.call_args.args[0]
        self.assertEqual([cmd[cmd.index(f) + 1] for f in ("--kind", "--by", "--head")], ["auto", "0101", "bbbbbbbb"])
        self.assertIn("✔", lines[0])

    def test_the_open_pr_head_of_a_pushed_card_is_a_candidate(self):
        with mock.patch.object(fp.subprocess, "run") as run:
            lines = fp.waive_pass(_states(head="1234567"), apply=False, prs=[_pr()])
        run.assert_not_called()
        self.assertIn("abcdef12", lines[0])
        self.assertIn("#7", lines[0])

    def test_the_same_head_or_an_unapproved_card_is_not_a_candidate(self):
        st = {"W-20261020-001": {"state": "approved", "approved_head": "aaaaaaa", "ready_head": "aaaaaaaa"},
              "W-20261020-002": {"state": "ready_for_review", "ready_head": "bbbbbbbb"}}
        self.assertEqual(fp.waive_pass(st, apply=False, prs=[_pr(head="a" * 40)]), [])

    def test_a_refusal_is_reported_not_forced(self):
        st = {CARD: {"state": "approved", "approved_head": "aaaaaaaa", "ready_head": "bbbbbbbb"}}
        refused = SimpleNamespace(returncode=1, stdout="", stderr="لا إعفاءَ آليّاً: الفرقُ ليس دمجَ main خالصاً")
        with mock.patch.object(fp.subprocess, "run", return_value=refused):
            lines = fp.waive_pass(st, apply=True)
        self.assertIn("ليس إعفاءً آليّاً", lines[0])


class CardPrs(unittest.TestCase):
    def test_two_open_prs_for_one_card_are_ambiguous_not_guessed(self):
        pairs, notes = fp.card_prs(_states(), [_pr(1), _pr(2)])
        self.assertEqual(pairs, {})
        self.assertIn("التباس", notes[0])

    def test_a_pr_naming_two_cards_is_reported_only_when_one_is_ours(self):
        pr = _pr(title="W-20261020-001 وW-20261020-002")
        self.assertEqual(fp.card_prs(_states(), [pr])[1][0][:3], "#7:")
        self.assertEqual(fp.card_prs({}, [pr])[1], [])

    def test_a_card_not_yet_approved_has_no_pr(self):
        self.assertEqual(fp.card_prs(_states("ready_for_review"), [_pr()])[0], {})


class LinePass(unittest.TestCase):
    def run_pass(self, pr, rows=(OWNER_ROW,), base="abcdef12", ok=True, apply=True, states=None):
        sh = FakeSh()
        found = (base, list(rows)) if rows else None
        with (
            mock.patch.object(fp, "approval_ok", return_value=ok),
            mock.patch.object(fp.ac, "approval_base", return_value=found),
        ):
            lines = fp.line_pass(states or _states(), [pr], apply, sh)
        return lines, sh

    def test_the_owner_direct_line_is_written_first_with_the_head_after_the_date(self):
        lines, sh = self.run_pass(_pr())
        body = sh.bodies[0]
        first = body.splitlines()[0]
        self.assertEqual(first, f"اعتُمد من المالك مباشرةً بلا معاينة 8500 — 2026-10-20 — الرأس abcdef12 — {CARD}")
        self.assertEqual(b_verdict(body, FULL), "ok", "فحصُ المستودع يقرأ الرأسَ من سطر المضخّة")
        self.assertIsNone(fp.ac.line_card_problem(first, CARD))
        self.assertIn("ملخّص الطلب", body)
        self.assertEqual(sh.calls[0][:4], ["gh", "pr", "edit", "7"])
        self.assertIn("✔", lines[0])

    def test_a_d443_delegation_gets_the_mandate_line(self):
        _, sh = self.run_pass(_pr(), rows=(D443_ROW,))
        first = sh.bodies[0].splitlines()[0]
        self.assertTrue(first.startswith("اعتُمد بتكليف المالك D-443م عبر 0101 — 2026-10-20 — الرأس abcdef12"))
        self.assertTrue(B_MANDATE.search(first))
        self.assertEqual(b_verdict(sh.bodies[0], FULL), "ok")

    def test_a_stale_first_approval_line_is_replaced_not_duplicated(self):
        old = f"اعتُمد من المالك على 8500 — 2026-10-19 — الرأس 11111111 — {CARD}\nنصٌّ باقٍ"
        _, sh = self.run_pass(_pr(body=old))
        self.assertNotIn("11111111", sh.bodies[0])
        self.assertEqual(sh.bodies[0].count("اعتُمد"), 1)
        self.assertIn("نصٌّ باقٍ", sh.bodies[0])

    def test_a_valid_line_is_left_alone(self):
        body = f"اعتُمد من المالك على 8500 — 2026-10-20 — الرأس abcdef12 — {CARD}"
        lines, sh = self.run_pass(_pr(body=body))
        self.assertEqual((lines, sh.calls), ([], []))

    def test_an_inherited_approval_names_its_base_and_still_binds_the_head(self):
        _, sh = self.run_pass(_pr(), base="99999999")
        self.assertIn("موروثٌ من الرأس 99999999", sh.bodies[0])
        self.assertEqual(b_verdict(sh.bodies[0], FULL), "ok")

    def test_no_proven_approval_or_no_owner_row_writes_nothing(self):
        for kw in ({"ok": False}, {"rows": ()}):
            lines, sh = self.run_pass(_pr(), **kw)
            self.assertEqual(sh.calls, [])
            self.assertIn("لا سطر", lines[0])

    def test_a_pr_head_other_than_the_approved_head_gets_no_line(self):
        lines, sh = self.run_pass(_pr(head="f" * 40))
        self.assertEqual((lines, sh.calls), ([], []))

    def test_a_dry_run_writes_nothing(self):
        lines, sh = self.run_pass(_pr(), apply=False)
        self.assertEqual(sh.calls, [])
        self.assertIn("(عرض)", lines[0])


LINED = f"اعتُمد من المالك على 8500 — 2026-10-20 — الرأس abcdef12 — {CARD}"


class MergePass(unittest.TestCase):
    def run_pass(self, pr, ok=True, security=None, apply=True):
        sh = FakeSh()
        with (
            mock.patch.object(fp, "approval_ok", return_value=ok),
            mock.patch.object(fp.ac, "security_approved", return_value=security),
        ):
            lines = fp.merge_pass(_states(), [pr], apply, sh)
        return lines, sh

    def test_a_lined_clean_pr_is_queued_to_merge_at_green_ci_bound_to_its_exact_head(self):
        lines, sh = self.run_pass(_pr(body=LINED))
        self.assertEqual(sh.calls, [["gh", "pr", "merge", "7", "--squash", "--auto", "--match-head-commit", FULL]])
        self.assertIn("✔", lines[0])

    def test_blocked_prs_are_reported_and_never_merged(self):
        cases = {
            "مسودّة": _pr(body=LINED, isDraft=True),
            "لا main": _pr(body=LINED, baseRefName="develop"),
            "0601": _pr(body=LINED, files=[{"path": "school/migrations/0007_x.py"}]),
            "واسع": _pr(body=LINED, changedFiles=120),
            "أقرّ أمنياً": _pr(body=LINED, labels=[{"name": fp.SECURITY_LABEL}]),
            "مساراتٌ أمنيّة": _pr(body=LINED, files=[{"path": "school/permissions.py"}]),
            "بلا سطر": _pr(),
        }
        for why, pr in cases.items():
            lines, sh = self.run_pass(pr)
            self.assertEqual(sh.calls, [], why)
            self.assertIn(why, lines[0])

    def test_owner_security_approval_on_the_head_or_its_carried_base_unblocks_the_security_label(self):
        lines, sh = self.run_pass(_pr(body=LINED, labels=[{"name": fp.SECURITY_LABEL}]), security="abcdef12")
        self.assertEqual(sh.calls[0][:4], ["gh", "pr", "merge", "7"])

    def test_no_proven_approval_no_merge(self):
        lines, sh = self.run_pass(_pr(body=LINED), ok=False)
        self.assertEqual(sh.calls, [])

    def test_an_already_queued_pr_is_silent(self):
        self.assertEqual(self.run_pass(_pr(body=LINED, autoMergeRequest={"mergeMethod": "SQUASH"}))[0], [])

    def test_a_dry_run_merges_nothing(self):
        lines, sh = self.run_pass(_pr(body=LINED), apply=False)
        self.assertEqual(sh.calls, [])
        self.assertIn("(عرض)", lines[0])


class PushPass(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = str(self.tmp / "e.jsonl")
        self.card = fp.ledger.add_item("owner", "tool", "م", "أ", "ق", start="2026-10-20T08:00", priority="P2", path=self.path, held_by="0702")
        fp.ledger.move(self.card, "approved", path=self.path, note="اعتمد المالك على 8500", head="aaaaaaaa", by="0501", waive_spec="اختبار")
        self.gitdir = self.tmp / "gitdir"
        self.gitdir.mkdir()

    def git(self, branch):
        head = "a" * 40
        porcelain = f"worktree C:/repo/wt1\nHEAD {head}\nbranch refs/heads/{branch}\n"
        calls = []

        def git(repo, *args):
            calls.append(args)
            if args[0] == "worktree":
                return 0, porcelain
            if args[:2] == ("rev-parse", "--absolute-git-dir"):
                return 0, str(self.gitdir) + "\n"
            if args[0] == "rev-parse":
                return 0, head + "\n"
            if args[0] == "log":
                return 0, head + "\n"
            if args[0] == "ls-remote":
                return 0, f"{head}\trefs/heads/{branch}\n"
            return 0, ""

        git.calls = calls
        return git

    def run_pass(self, branch="w20261020-001-x", receipt=True):
        if receipt:
            (self.gitdir / fp.ledger.RECEIPT_NAME).write_text(json.dumps({"head": "aaaaaaaa", "ok": True}), encoding="utf-8")
        git = self.git(branch)
        states = fp.ledger.reduce_state(fp.ledger.load_events(self.path))
        lines = fp.push_pass(states, True, repos=["C:/repo"], path=self.path, git=git, approved=lambda c, h: True)
        pushes = [a for a in git.calls if a[0] == "push"]
        return lines, pushes, fp.ledger.reduce_state(fp.ledger.load_events(self.path))[self.card]

    def test_a_w_branch_with_the_receipt_for_the_same_head_is_pushed_by_0101(self):
        lines, pushes, item = self.run_pass()
        self.assertEqual(pushes, [("push", "origin", "HEAD:refs/heads/w20261020-001-x")])
        self.assertEqual(item["state"], "pushed")
        self.assertIn("دُفع ✔", lines[0])

    def test_without_the_prepush_receipt_nothing_is_pushed(self):
        lines, pushes, item = self.run_pass(receipt=False)
        self.assertEqual((pushes, item["state"]), ([], "approved"))
        self.assertIn("prepush", lines[0])

    def test_other_branches_are_never_pushed(self):
        for branch in ("main", "feature/x"):
            lines, pushes, item = self.run_pass(branch=branch)
            self.assertEqual(pushes, [], branch)

    def test_no_approved_card_touches_no_repository(self):
        with mock.patch("ready_mark.candidate_repos") as repos:
            self.assertEqual(fp.push_pass({CARD: {"state": "pushed"}}, True), [])
        repos.assert_not_called()


class Stages(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        for name in ("LOCK", "LOG", "OFF", "NO_MERGE"):
            p = mock.patch.object(fp, name, tmp / name)
            p.start()
            self.addCleanup(p.stop)

    def run_main(self, argv, prs=()):
        called = []

        def stage(name):
            return lambda *a, **k: called.append(name) or []

        with (
            mock.patch.object(fp.ledger, "load_events", return_value=[]),
            mock.patch.object(fp.ledger, "reduce_state", return_value=_states("approved")),
            mock.patch.object(fp, "open_prs", side_effect=lambda: called.append("prs") or (None if prs is None else list(prs))),
            mock.patch.object(fp, "approve_pass", side_effect=stage("approve")),
            mock.patch.object(fp, "waive_pass", side_effect=stage("waive")),
            mock.patch.object(fp, "push_pass", side_effect=stage("push")),
            mock.patch.object(fp, "line_pass", side_effect=stage("line")),
            mock.patch.object(fp, "merge_pass", side_effect=stage("merge")),
            mock.patch.object(fp.ledger_sync, "cycle", return_value=0),
            mock.patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            fp._run(argv)  # بلا main: main يعيد ضبطَ ترميز stdout ولا يقبله StringIO
        return called, out.getvalue()

    def test_all_stages_run_in_order(self):
        called, _ = self.run_main(["--apply"])
        self.assertEqual(called, ["approve", "prs", "waive", "push", "line", "merge"])

    def test_each_stage_can_be_switched_off(self):
        called, _ = self.run_main(["--apply", "--no-push", "--no-line", "--no-merge"])
        self.assertEqual(called, ["approve", "prs", "waive"])

    def test_the_no_merge_switch_skips_only_the_merge_stage(self):
        fp.NO_MERGE.write_text("")
        called, out = self.run_main(["--apply"])
        self.assertEqual(called, ["approve", "prs", "waive", "push", "line"])
        self.assertIn("دمج: معطَّل", out)

    def test_unreadable_prs_are_reported_not_taken_as_none(self):
        called, out = self.run_main([], prs=None)
        self.assertIn("تعذّرت قراءةُ الطلبات", out)


if __name__ == "__main__":
    unittest.main()
