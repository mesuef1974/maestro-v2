"""اختباراتُ مضخّة التدفّق:  python -m pytest test_flow_pump.py"""

import io
import json
import os
import re
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
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


def _fake_git(branches, grep_hits):
    """git وهميّ: for-each-ref يعيد الفروع، وlog --grep يعيد رأساً لفروع grep_hits فقط، وrev-parse لـ_is_platform."""
    def git(repo, *args):
        if args[0] == "for-each-ref":
            return 0, chr(10).join(f"{n} {s}" for n, s in branches)
        if args[0] == "log":
            return 0, "x" if args[-2] in grep_hits else ""
        return 0, ""
    return git


class DeriveHead(unittest.TestCase):
    BR = [("claude/a", "a" * 40), ("w0701-b", "b" * 40), ("main", "c" * 40)]

    def run_derive(self, hits):
        with mock.patch.object(fp, "_is_platform", return_value=True):
            return fp.derive_head("W-1", _fake_git(self.BR, hits), "P")

    def test_a_single_allowed_branch_gives_its_tip(self):
        self.assertEqual(self.run_derive({"claude/a"}), ("aaaaaaaa", "claude/a"))

    def test_main_is_never_a_candidate(self):
        head, _ = self.run_derive({"main"})
        self.assertIsNone(head)

    def test_two_branches_are_ambiguous_and_give_no_head(self):
        head, why = self.run_derive({"claude/a", "w0701-b"})
        self.assertIsNone(head)
        self.assertIn("التباس", why)

    def test_no_branch_gives_no_head(self):
        self.assertIsNone(self.run_derive(set())[0])

    def test_a_non_platform_card_gives_no_head(self):
        with mock.patch.object(fp, "_is_platform", return_value=False):
            self.assertIsNone(fp.derive_head("W-1", _fake_git(self.BR, {"claude/a"}), "P")[0])


class DerivedFlow(unittest.TestCase):
    """بطاقةٌ بلا رأسٍ معلَن ولا رسالة: يُشتقّ رأسُها من الفرع، فتنتظر المالك، فإن اعتمد انتقلت approved بالرأس المشتقّ وحده."""
    STATES = {"W-1": {"state": "ready_for_review", "notes": []}}
    GIT = staticmethod(lambda: _fake_git([("claude/a", "a" * 40)], {"claude/a"}))

    def test_waits_for_owner_and_is_listed_once(self):
        with mock.patch.object(fp, "_is_platform", return_value=True), mock.patch.object(fp, "approval_ok", return_value=False):
            self.assertEqual(fp.owner_list(self.STATES, self.GIT(), "P"), ["W-1 @ aaaaaaaa"])
            self.assertIn("[مالك=0101]", fp.approve_pass(self.STATES, False, self.GIT(), "P")[0])  # يُسمّى المالكُ بدل «ينتظر» (W-20261024-007)

    def test_owner_approval_moves_it_with_the_derived_head_and_no_message(self):
        with (
            mock.patch.object(fp, "_is_platform", return_value=True),
            mock.patch.object(fp, "approval_ok", return_value=True),
            mock.patch.object(fp.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")) as run,
        ):
            line = fp.approve_pass(self.STATES, True, self.GIT(), "P")[0]
        self.assertIn("approved", line)
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[cmd.index("--head") + 1], "aaaaaaaa")

    def test_an_approved_card_is_not_listed_for_the_owner(self):
        with mock.patch.object(fp, "_is_platform", return_value=True), mock.patch.object(fp, "approval_ok", return_value=True):
            self.assertEqual(fp.owner_list(self.STATES, self.GIT(), "P"), [])


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
            mock.patch.object(fp, "approval_why", return_value="لا اعتماد"),
            mock.patch.object(fp.hand_off, "__defaults__", (Path(tempfile.mkdtemp()), None)),
            mock.patch.object(fp.subprocess, "run") as run,
        ):
            lines = fp.approve_pass({"W-1": self.STATES["W-1"]}, apply=True)
        run.assert_not_called()
        self.assertNotIn("ينتظر", lines[0])  # يُسمّى المالكُ بدل «ينتظر» (W-20261024-007)
        self.assertIn("[مالك=0101]", lines[0])

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


_ENV = mock.patch.dict(os.environ, {"LEDGER_PATH": str(Path(tempfile.mkdtemp()) / "events.jsonl")})


def setUpModule():  # لقطةُ صحة المضخّة (--apply) لا تلمس الدفتر الحيّ
    _ENV.start()


def tearDownModule():
    _ENV.stop()


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


class ViewSh(FakeSh):
    """يردّ على `gh pr view` بحالة الدمج الآليّ المعطاة؛ وباقي الأوامر كما FakeSh."""

    def __init__(self, view_out='{"autoMergeRequest": {"enabledAt": "x"}, "state": "OPEN"}', view_rc=0, runs_out="[]", runs_rc=0):
        super().__init__()
        self.view_out, self.view_rc = view_out, view_rc
        self.runs_out, self.runs_rc = runs_out, runs_rc

    def __call__(self, cmd, cwd=None):
        if cmd[:3] == ["gh", "run", "list"]:  # main هادئ افتراضاً (W-20261022-020)؛ ولا يُسجَّل بين استدعاءات الدمج
            return self.runs_rc, self.runs_out
        if cmd[:3] == ["gh", "pr", "view"]:
            self.calls.append(cmd)
            return self.view_rc, self.view_out
        return super().__call__(cmd, cwd)


class MergePass(unittest.TestCase):
    def run_pass(self, pr, ok=True, security=None, apply=True, sh=None):
        sh = sh or ViewSh()
        with (
            mock.patch.object(fp, "approval_ok", return_value=ok),
            mock.patch.object(fp.ac, "security_approved", return_value=security),
            mock.patch.object(fp, "merge_window", return_value="2026-10-30:1"),
            mock.patch.object(fp, "MERGE_WINDOW_STATE", Path(tempfile.mkdtemp()) / "w.json"),
            mock.patch("inbox.send"),
        ):
            lines = fp.merge_pass(_states(), [pr], apply, sh)
        return lines, sh

    def test_a_lined_clean_pr_is_queued_to_merge_at_green_ci_bound_to_its_exact_head(self):
        lines, sh = self.run_pass(_pr(body=LINED))
        self.assertEqual(sh.calls[0], ["gh", "pr", "merge", "7", "--squash", "--auto", "--match-head-commit", FULL])
        self.assertIn("✔", lines[0])

    def test_no_tick_when_gh_succeeds_but_auto_merge_is_not_armed(self):  # #1226 و#1223 و#1218
        for view_out in ('{"autoMergeRequest": null, "state": "OPEN"}', "", "ليس json"):
            lines, _sh = self.run_pass(_pr(body=LINED), sh=ViewSh(view_out=view_out))
            self.assertNotIn("✔", lines[0], view_out)
            self.assertIn("غيرُ مفعَّل", lines[0])

    def test_tick_when_the_pr_is_already_merged(self):
        lines, _sh = self.run_pass(_pr(body=LINED), sh=ViewSh(view_out='{"autoMergeRequest": null, "state": "MERGED"}'))
        self.assertIn("✔", lines[0])

    def test_a_failed_view_means_no_tick(self):
        lines, _sh = self.run_pass(_pr(body=LINED), sh=ViewSh(view_rc=1))
        self.assertNotIn("✔", lines[0])

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


def _run(status="in_progress", event="push", branch="main"):
    return {"status": status, "event": event, "headBranch": branch}


class SerialMerge(unittest.TestCase):
    """W-20261022-020: طلبٌ واحد لكلّ نشر — لا --auto والطابورُ أو main مشغولان، وطلبٌ واحدٌ يُفعَّل في الدورة."""

    def run_pass(self, prs, sh=None, apply=True, states=None):
        sh = sh or ViewSh()
        with (
            mock.patch.object(fp, "approval_ok", return_value=True),
            mock.patch.object(fp.ac, "security_approved", return_value=None),
            mock.patch.object(fp, "merge_window", return_value="2026-10-30:1"),
            mock.patch.object(fp, "MERGE_WINDOW_STATE", Path(tempfile.mkdtemp()) / "w.json"),
        ):
            lines = fp.merge_pass(states or _states(), prs, apply, sh)
        return lines, sh

    def merged(self, sh):
        return [c for c in sh.calls if c[:3] == ["gh", "pr", "merge"]]

    def test_main_runs_count_only_push_and_queue_events_on_main_in_flight(self):
        runs = [_run(), _run("queued", "merge_group", "gh-readonly-queue/main/pr-9"), _run("completed"),
                _run(event="pull_request"), _run(branch="feature/x")]
        self.assertEqual(fp.main_runs_in_flight(lambda c, cwd=None: (0, json.dumps(runs))), 2)

    def test_unreadable_runs_are_none(self):
        self.assertIsNone(fp.main_runs_in_flight(lambda c, cwd=None: (1, "")))
        self.assertIsNone(fp.main_runs_in_flight(lambda c, cwd=None: (0, "zzz")))
        self.assertIsNone(fp.main_runs_in_flight(lambda c, cwd=None: (0, "{}")))

    def test_a_busy_main_defers_the_arming_and_says_why(self):
        lines, sh = self.run_pass([_pr(body=LINED)], sh=ViewSh(runs_out=json.dumps([_run()])))
        self.assertEqual(self.merged(sh), [])
        self.assertIn("يؤجَّل", lines[0])
        self.assertIn("1 تشغيلاً جارياً على main", lines[0])

    def test_a_running_deploy_on_main_after_a_merge_also_defers(self):
        lines, sh = self.run_pass([_pr(body=LINED)], sh=ViewSh(runs_out=json.dumps([_run("queued")])))
        self.assertEqual(self.merged(sh), [])

    def test_another_pr_already_armed_holds_this_one_back(self):
        other = _pr(num=9, card="W-20261020-009", autoMergeRequest={"enabledAt": "x"})
        lines, sh = self.run_pass([_pr(body=LINED), other])
        self.assertEqual(self.merged(sh), [])
        self.assertIn("#9 في الطابور", lines[0])

    def test_a_draft_armed_pr_does_not_block(self):
        other = _pr(num=9, card="W-20261020-009", autoMergeRequest={"enabledAt": "x"}, isDraft=True)
        lines, sh = self.run_pass([_pr(body=LINED), other])
        self.assertEqual(len(self.merged(sh)), 1)

    def test_unreadable_main_runs_defer_instead_of_arming(self):
        lines, sh = self.run_pass([_pr(body=LINED)], sh=ViewSh(runs_rc=1))
        self.assertEqual(self.merged(sh), [])
        self.assertIn("تعذّرت", lines[0])

    def test_only_one_pr_is_armed_per_cycle(self):
        second = "W-20261020-002"
        states = {**_states(), second: {"state": "pushed", "approved_head": "abcdef12", "approvals": [{"ts": "2026-10-20T10:00:00+03:00"}], "notes": []}}
        prs = [_pr(num=7, body=LINED), _pr(num=8, card=second, body=LINED.replace(CARD, second))]
        with mock.patch.object(fp, "line_ok", return_value=True):
            lines, sh = self.run_pass(prs, states=states)
        self.assertEqual(len(self.merged(sh)), 1)
        self.assertTrue(any("فُعِّل الدمجُ الآليّ على #7" in line for line in lines))

    def test_dry_run_also_holds_the_second_pr_back(self):
        second = "W-20261020-002"
        states = {**_states(), second: {"state": "pushed", "approved_head": "abcdef12", "approvals": [{"ts": "2026-10-20T10:00:00+03:00"}], "notes": []}}
        prs = [_pr(num=7, body=LINED), _pr(num=8, card=second, body=LINED)]
        with mock.patch.object(fp, "line_ok", return_value=True):
            lines, sh = self.run_pass(prs, states=states, apply=False)
        self.assertEqual(sum("(عرض)" in line for line in lines), 1)
        self.assertEqual(sh.calls, [])

    def test_migration_and_security_blocks_still_come_first(self):
        lines, sh = self.run_pass([_pr(body=LINED, files=[{"path": "school/migrations/0007_x.py"}])], sh=ViewSh(runs_out=json.dumps([_run()])))
        self.assertIn("0601", lines[0])
        self.assertNotIn("يؤجَّل", lines[0])


class PushPass(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = str(self.tmp / "e.jsonl")
        self.card = fp.ledger.add_item("owner", "tool", "م", "أ", "ق", start="2026-10-20T08:00", priority="P2", path=self.path, held_by="0702")
        fp.ledger.move(self.card, "approved", path=self.path, note="اعتمد المالك على 8500", head="aaaaaaaa", by="0501", waive_spec="اختبار")
        self.gitdir = self.tmp / "gitdir"
        self.gitdir.mkdir()
        self.has_tool = True  # المستودعُ الوهميُّ منصّةٌ تحمل scripts/prepush_check.py ما لم يُقل غيرُه
        p = mock.patch.object(fp.push_approved, "has_prepush_tool", lambda repo: self.has_tool)
        p.start()
        self.addCleanup(p.stop)

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

    def test_a_governance_repo_needs_the_substitute_receipt_not_an_exemption(self):
        """(W-20261026-018) مستودعُ حوكمةٍ بلا scripts/prepush_check.py لا يُعفى: إيصالُه البديل pytest tools/ أخضرَ للرأس نفسه."""
        self.has_tool = False
        lines, pushes, item = self.run_pass(receipt=False)
        self.assertEqual((pushes, item["state"]), ([], "approved"))
        (self.gitdir / fp.ledger.RECEIPT_NAME).write_text(
            json.dumps({"head": "aaaaaaaa", "ok": True, "kind": fp.push_approved.GOV_RECEIPT_KIND}), encoding="utf-8")
        lines, pushes, item = self.run_pass(receipt=False)
        self.assertEqual((pushes, item["state"]), ([("push", "origin", "HEAD:refs/heads/w20261020-001-x")], "pushed"))

    def test_other_branches_are_never_pushed(self):
        for branch in ("main", "feature/x"):
            lines, pushes, item = self.run_pass(branch=branch)
            self.assertEqual(pushes, [], branch)

    def test_no_approved_card_touches_no_repository(self):
        with mock.patch("ready_mark.candidate_repos") as repos:
            self.assertEqual(fp.push_pass({CARD: {"state": "pushed"}}, True), [])
        repos.assert_not_called()


class PrepushPass(unittest.TestCase):
    """(W-20261023-016) إيصال prepush آليّاً: حاويةٌ وهميّة، ولا إيصالَ إلا بخروج 0 وسطر النجاح الكامل وبلا «غير مقيس»."""

    OK_LOG = "=== النتيجة ===\n✔ ruff check: نجح\n\nالفحوصُ السريعةُ ناجحة — الدفعُ مسموح (الاختبارات الكاملة تبقى في CI)."

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = str(self.tmp / "e.jsonl")
        self.tree = self.tmp / "wt1"
        (self.tree / "scripts").mkdir(parents=True)
        (self.tree / "scripts" / "prepush_check.py").write_text("", encoding="utf-8")
        self.gitdir = self.tmp / "common" / "worktrees" / "wt1"
        self.gitdir.mkdir(parents=True)
        p = mock.patch.object(fp, "PREPUSH_ATTEMPTS", self.tmp / "attempts.json")
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(fp, "LOG", self.tmp / "pump.log")
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(fp.hand_off, "__defaults__", (self.tmp, None))  # رسائلُ الإحالة في صندوقٍ مؤقّت لا صندوق المستودع
        p.start()
        self.addCleanup(p.stop)
        self.card = fp.ledger.add_item("owner", "tool", "م", "أ", "ق", start="2026-10-20T08:00", priority="P2", path=self.path, held_by="0702")
        fp.ledger.move(self.card, "approved", path=self.path, note="اعتمد المالك على 8500", head="aaaaaaaa", by="0501", waive_spec="اختبار")

    def git(self, branch="w20261020-001-x", origin="https://github.com/x/shschool_mvp.git", dirty="", head="a" * 40):
        porcelain = f"worktree {self.tree.as_posix()}\nHEAD {'a' * 40}\nbranch refs/heads/{branch}\n"

        def git(repo, *args):
            if args[0] == "worktree":
                return 0, porcelain
            if args[:2] == ("rev-parse", "--absolute-git-dir"):
                return 0, str(self.gitdir) + "\n"
            if args[:2] == ("rev-parse", "--path-format=absolute"):
                return 0, str(self.gitdir.parent.parent) + "\n"
            if args[0] == "rev-parse":
                return 0, head + "\n"
            if args[0] == "log":
                return 0, "a" * 40 + "\n"
            if args[0] == "remote":
                return 0, origin + "\n"
            if args[0] == "status":
                return 0, dirty
            return 0, ""

        return git

    def docker(self, code=0, log=None, image=True):
        calls = []

        def docker(cmd, timeout):
            calls.append((cmd, timeout))
            if cmd[0] == "image":
                return (0 if image else 1), ""
            if cmd[0] != "run" or "-d" in cmd:
                return 0, ""  # network/exec/rm وتشغيل قاعدة الاختبار
            return code, self.OK_LOG if log is None else log

        docker.calls = calls
        return docker

    def run_pass(self, apply=True, docker=None, git=None, **kw):
        docker = docker or self.docker()
        states = fp.ledger.reduce_state(fp.ledger.load_events(self.path))
        lines = fp.prepush_pass(states, apply, repos=[str(self.tmp)], git=git or self.git(), docker=docker, **kw)
        return lines, docker

    def receipt(self):
        f = self.gitdir / fp.ledger.RECEIPT_NAME
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None

    def runs(self, docker):
        return [c for c, _ in docker.calls if c[0] == "run" and "-d" not in c]

    def test_success_writes_the_receipt_for_the_same_head_and_push_guard_accepts_it(self):
        lines, docker = self.run_pass()
        self.assertEqual(self.receipt(), {"head": "aaaaaaaa", "ok": True})
        self.assertIsNone(fp.push_approved.receipt_problem(str(self.tree), "a" * 40, self.git()))
        self.assertIn("✔ prepush", lines[0])
        self.assertEqual(len(self.runs(docker)), 1)

    def test_the_container_gets_read_only_mounts_and_only_the_internal_db_network(self):
        _, docker = self.run_pass()
        cmd = self.runs(docker)[0]
        net = cmd[cmd.index("--network") + 1]
        self.assertIn(["network", "create", "--internal", net], [c for c, _ in docker.calls])
        self.assertIn("TEST_DB_HOST=db", cmd)
        mounts = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-v"]
        self.assertTrue(mounts and all(m.endswith(":ro") for m in mounts), mounts)
        self.assertIn("PREPUSH_GIT_DIR=/gitmain/worktrees/wt1", cmd)

    def test_dry_run_runs_nothing_and_writes_nothing(self):
        lines, docker = self.run_pass(apply=False)
        self.assertEqual(docker.calls, [])
        self.assertIsNone(self.receipt())
        self.assertIn("عرض", lines[0])

    def test_failure_writes_no_receipt_and_is_not_retried_for_the_same_head(self):
        lines, docker = self.run_pass(docker=self.docker(code=1, log="✘ ruff check: فشل"))
        self.assertIsNone(self.receipt())
        self.assertIn("✘ prepush لم يُنتج", lines[0])
        lines, docker = self.run_pass()
        self.assertEqual(self.runs(docker), [])
        self.assertIn("لم يُعَد", lines[0])

    def test_unmeasured_exit_3_is_never_a_receipt(self):
        lines, _ = self.run_pass(docker=self.docker(code=3, log="؟ التعقيد: غير مقيس"))
        self.assertIsNone(self.receipt())
        self.assertIn("غير مقيس", lines[0])

    def test_exit_0_with_an_unmeasured_line_is_still_no_receipt(self):
        self.run_pass(docker=self.docker(code=0, log=self.OK_LOG + "\n؟ x: غير مقيس"))
        self.assertIsNone(self.receipt())

    def test_exit_0_without_the_full_success_line_is_no_receipt(self):
        self.run_pass(docker=self.docker(code=0, log="شيءٌ آخر"))
        self.assertIsNone(self.receipt())

    def test_timeout_is_a_failure_not_a_receipt(self):
        lines, _ = self.run_pass(docker=self.docker(code=124, log="تجاوز المهلة"))
        self.assertIsNone(self.receipt())
        self.assertIn("المهلة", lines[0])

    def test_an_existing_receipt_means_no_run(self):
        (self.gitdir / fp.ledger.RECEIPT_NAME).write_text(json.dumps({"head": "aaaaaaaa", "ok": True}), encoding="utf-8")
        lines, docker = self.run_pass()
        self.assertEqual((lines, docker.calls), ([], []))

    def test_missing_image_is_reported_and_nothing_runs(self):
        lines, docker = self.run_pass(docker=self.docker(image=False))
        self.assertEqual(self.runs(docker), [])
        self.assertIn("docker build", lines[0])

    def test_every_skip_prints_a_line_and_nothing_runs(self):
        """(W-20261026-018) لا تخطٍّ صامتاً: شجرةٌ متسخة أو فرعٌ آخر أو رأسٌ مختلف يطبع سطراً ولا يشغّل شيئاً."""
        for git in (self.git(dirty=" M x.py\n"), self.git(branch="main"), self.git(head="b" * 40)):
            lines, docker = self.run_pass(git=git)
            self.assertEqual(len(lines), 1, lines)
            self.assertIn("⏭", lines[0])
            self.assertEqual(docker.calls, [])
        self.assertIsNone(self.receipt())

    def test_governance_tree_gets_the_pytest_substitute_receipt_only_when_green(self):
        """(W-20261026-018) بلا scripts/prepush_check.py: pytest tools/ بدل الحاوية؛ الإيصالُ برمز 0 وحده."""
        (self.tree / "scripts" / "prepush_check.py").unlink()
        ran = []
        lines, docker = self.run_pass(pytest_run=lambda path, timeout: (ran.append(path) or (0, "1500 passed")))
        self.assertEqual([Path(x) for x in ran], [self.tree])
        self.assertEqual(docker.calls, [])
        self.assertIn("✔", lines[0])
        self.assertEqual(self.receipt(), {"head": "aaaaaaaa", "ok": True, "kind": fp.push_approved.GOV_RECEIPT_KIND})

    def test_governance_pytest_red_or_timeout_gives_no_receipt_and_is_not_retried_for_the_same_head(self):
        (self.tree / "scripts" / "prepush_check.py").unlink()
        calls = []

        def red(path, timeout):
            calls.append(1)
            return 1, "FAILED tools/test_x.py::t\n1 failed, 3 passed"

        lines, _ = self.run_pass(pytest_run=red)
        self.assertIn("✘", lines[0])
        self.assertIn("رمز الخروج 1", lines[0])
        self.assertIsNone(self.receipt())
        lines, _ = self.run_pass(pytest_run=red)
        self.assertEqual(len(calls), 1)  # لا إعادة لرأسٍ فشل
        self.assertIn("لم يُعَد", lines[0])
        (self.tree / "x").touch()
        lines, _ = self.run_pass(apply=False)
        self.assertIsNone(self.receipt())

    def test_an_old_format_or_old_runner_failure_is_retried_once(self):
        """(10-28) محاولاتُ مشغّل DETACHED_PROCESS حُجبت للأبد بـWinError 6 بلا عيبٍ في الشيفرة؛ الصيغةُ القديمة ونسخةُ مشغّلٍ أخرى تُعادان."""
        older = {"why": "رمز الخروج 1", "cond": "prepush", "v": fp.RUNNER_V - 1, "ts": "2026-10-28T10:00:00+03:00"}
        for old in ("رمز الخروج 1", older):
            fp.PREPUSH_ATTEMPTS.write_text(json.dumps({f"{self.card}:aaaaaaaa": old}), encoding="utf-8")
            lines, docker = self.run_pass()
            self.assertEqual(len(self.runs(docker)), 1, old)
            self.assertIn("✔ prepush", lines[0])
            (self.gitdir / fp.ledger.RECEIPT_NAME).unlink()

    def test_red_code_goes_to_the_live_holder_with_the_reason_and_the_log(self):
        import inbox

        with mock.patch.object(fp.hand_off, "__kwdefaults__", {"detail": "", "alive": lambda n, r: True}):
            lines, _ = self.run_pass(docker=self.docker(code=1, log="✘ ruff check: فشل"))
        self.assertIn("[مالك=0702]", lines[0])
        rows = [r for r in inbox._rows("0702", self.tmp) if r["k"] == "msg"]
        self.assertIn(f"ledger/prepush_{self.card}_aaaaaaaa.log", rows[0]["text"])
        self.assertIn("رمز الخروج 1", rows[0]["text"])
        self.assertEqual(json.loads(fp.PREPUSH_ATTEMPTS.read_text(encoding="utf-8"))[f"{self.card}:aaaaaaaa"]["cond"], "prepush")

    def test_an_environment_failure_goes_to_automation_and_is_retried_later(self):
        (self.tree / "scripts" / "prepush_check.py").unlink()
        calls = []

        def broken(path, timeout):
            calls.append(1)
            return 1, "FAILED tools/test_a.py::T::t - OSError: [WinError 6] The handle is invalid\n1 failed, 9 passed"

        lines, _ = self.run_pass(pytest_run=broken)
        self.assertIn("[مالك=0701]", lines[0])
        lines, _ = self.run_pass(pytest_run=broken)
        self.assertEqual(len(calls), 1)
        self.assertIn("يُعاد بعد", lines[0])
        key = f"{self.card}:aaaaaaaa"
        tried = json.loads(fp.PREPUSH_ATTEMPTS.read_text(encoding="utf-8"))
        tried[key]["ts"] = (datetime.now().astimezone() - timedelta(hours=fp.ENV_RETRY_H + 1)).isoformat(timespec="seconds")
        fp.PREPUSH_ATTEMPTS.write_text(json.dumps(tried), encoding="utf-8")
        self.run_pass(pytest_run=lambda path, timeout: (calls.append(1) or (0, "10 passed")))
        self.assertEqual(len(calls), 2)
        self.assertIsNotNone(self.receipt())

    def test_governance_dry_run_only_announces_the_substitute_receipt(self):
        (self.tree / "scripts" / "prepush_check.py").unlink()
        lines, _ = self.run_pass(apply=False, pytest_run=lambda p, t: (_ for _ in ()).throw(AssertionError("لا تشغيل في العرض")))
        self.assertIn("إيصالاً بديلاً", lines[0])
        self.assertIsNone(self.receipt())

    def test_governance_head_changed_during_pytest_gives_no_receipt(self):
        (self.tree / "scripts" / "prepush_check.py").unlink()
        base, state = self.git(), {"done": False}

        def git(repo, *args):
            if args == ("rev-parse", "HEAD"):
                return 0, ("b" if state["done"] else "a") * 40 + chr(10)
            return base(repo, *args)

        def run(path, timeout):
            state["done"] = True
            return 0, "ok"

        lines, _ = self.run_pass(git=git, pytest_run=run)
        self.assertIsNone(self.receipt())
        self.assertIn("تغيّر أثناء الفحص", lines[0])

    def test_head_changed_during_the_run_gives_no_receipt(self):
        heads = iter(["a" * 40, "b" * 40])
        base = self.git()

        def git(repo, *args):
            if args == ("rev-parse", "HEAD"):
                return 0, next(heads, "b" * 40) + "\n"
            return base(repo, *args)

        self.run_pass(git=git)
        self.assertIsNone(self.receipt())

    def test_only_approved_cards_with_one_run_per_cycle(self):
        states = {"W-1": {"state": "ready_for_review", "approved_head": "aaaaaaaa"}}
        docker = self.docker()
        self.assertEqual(fp.prepush_pass(states, True, repos=[str(self.tmp)], git=self.git(), docker=docker), [])
        self.assertEqual(docker.calls, [])

    def test_the_limit_defers_the_second_card(self):
        import push_watch

        a = self.card
        b = fp.ledger.add_item("owner", "tool", "م", "أ", "ق", start="2026-10-20T08:00", priority="P2", path=self.path, held_by="0702")
        fp.ledger.move(b, "approved", path=self.path, note="اعتمد المالك على 8500", head="aaaaaaaa", by="0501", waive_spec="اختبار")
        docker = self.docker(code=1, log="✘ فشل")
        states = fp.ledger.reduce_state(fp.ledger.load_events(self.path))
        with mock.patch.object(push_watch, "find_tree",
                               return_value=({"path": str(self.tree), "branch": "w1", "head": "a" * 40}, "")):
            lines = fp.prepush_pass(states, True, repos=[str(self.tmp)], git=self.git(), docker=docker, limit=1)
        self.assertEqual(len(self.runs(docker)), 1)
        self.assertTrue(any("الدورة التالية" in x for x in lines), (a, b, lines))

    def test_db_and_network_are_removed_even_when_the_run_fails(self):
        _, docker = self.run_pass(docker=self.docker(code=1, log="x"))
        heads = [c[:2] for c, _ in docker.calls]
        self.assertIn(["rm", "-f"], heads)
        self.assertIn(["network", "rm"], heads)

    def test_a_db_that_never_becomes_ready_is_a_failure_and_is_cleaned_up(self):
        calls = []

        def docker(cmd, timeout):
            calls.append(cmd)
            return (1, "") if cmd[0] == "exec" else (0, "")

        rc, out = fp.run_with_db(docker, lambda net: ["run"], "n", 10, sleep=lambda s: None)
        self.assertEqual(rc, 1)
        self.assertEqual([c[0] for c in calls][-2:], ["rm", "network"])
        self.assertEqual(calls[0][:2], ["rm", "-f"])  # تنظيفُ بقايا قبل البدء
        self.assertNotIn(["run"], calls)

    def test_docker_helper_kills_the_container_on_timeout(self):
        import subprocess

        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            if cmd[1] == "run":
                raise subprocess.TimeoutExpired(cmd, 1)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(fp.subprocess, "run", side_effect=run):
            rc, _ = fp._docker(["run", "--name", "n1", "img"], 1)
        self.assertEqual(rc, 124)
        self.assertEqual(calls[-1], ["docker", "rm", "-f", "n1"])


def _rollup(*entries):
    return {"number": 1, "isDraft": False, "statusCheckRollup": list(entries)}


class CiLimit(unittest.TestCase):
    """W-20261022-019: لا دفعَ لبطاقات المنصّة وطلبان قيد الفحص (checks لم تكتمل)."""

    def test_check_run_and_status_context_pending_rules(self):
        self.assertTrue(fp._entry_pending({"status": "IN_PROGRESS"}))
        self.assertTrue(fp._entry_pending({"status": "QUEUED"}))
        self.assertFalse(fp._entry_pending({"status": "COMPLETED", "conclusion": "FAILURE"}))
        self.assertTrue(fp._entry_pending({"state": "PENDING"}))
        self.assertFalse(fp._entry_pending({"state": "SUCCESS"}))

    def _sh(self, prs, rc=0):
        return lambda cmd, cwd=None: (rc, json.dumps(prs))

    def test_counts_only_open_non_draft_prs_with_an_unfinished_check(self):
        prs = [
            _rollup({"status": "COMPLETED"}, {"status": "IN_PROGRESS"}),
            {**_rollup({"status": "IN_PROGRESS"}), "isDraft": True},
            _rollup({"status": "COMPLETED"}),
            _rollup({"state": "PENDING"}),
            {"number": 5, "isDraft": False, "statusCheckRollup": []},
        ]
        self.assertEqual(fp.ci_in_flight(self._sh(prs)), 2)

    def test_unreadable_gh_is_none_not_zero(self):
        self.assertIsNone(fp.ci_in_flight(self._sh([], rc=1)))
        self.assertIsNone(fp.ci_in_flight(lambda cmd, cwd=None: (0, "not json")))
        self.assertIsNone(fp.ci_in_flight(lambda cmd, cwd=None: (0, "{}")))


class CiLimitPush(PushPass):
    """نفسُ إعداد الدفع، بمستودعٍ يُعرَّف منصّةً أو لا، وعدّادِ فحوصٍ مُحاكى."""

    platform = True

    def git(self, branch):
        base = super().git(branch)
        calls = base.calls
        platform = self.platform

        def git(repo, *args):
            if args[:2] == ("remote", "get-url"):
                calls.append(args)
                return 0, ("https://github.com/x/shschool_mvp.git" if platform else "https://github.com/x/maestro-v2.git") + "\n"
            return base(repo, *args)

        git.calls = calls
        return git

    def run_gated(self, busy, platform=True, apply=True):
        type(self).platform = platform
        (self.gitdir / fp.ledger.RECEIPT_NAME).write_text(json.dumps({"head": "aaaaaaaa", "ok": True}), encoding="utf-8")
        git = self.git("w20261020-001-x")
        states = fp.ledger.reduce_state(fp.ledger.load_events(self.path))
        with mock.patch.object(fp, "LOG", self.tmp / "pump.log"):
            lines = fp.push_pass(states, apply, repos=["C:/repo"], path=self.path, git=git, approved=lambda c, h: True,
                                 busy_fn=lambda: busy)
        pushes = [a for a in git.calls if a[0] == "push"]
        return lines, pushes, fp.ledger.reduce_state(fp.ledger.load_events(self.path))[self.card]["state"]

    def test_two_prs_in_ci_defer_the_push_and_say_why(self):
        lines, pushes, state = self.run_gated(2)
        self.assertEqual((pushes, state), ([], "approved"))
        self.assertIn("يُؤجَّل", lines[0])
        self.assertIn("2 طلباً قيد الفحص", lines[0])

    def test_below_the_limit_it_pushes(self):
        lines, pushes, state = self.run_gated(1)
        self.assertEqual(state, "pushed")
        self.assertEqual(len(pushes), 1)

    def test_unreadable_ci_state_defers_instead_of_guessing(self):
        lines, pushes, state = self.run_gated(None)
        self.assertEqual((pushes, state), ([], "approved"))
        self.assertIn("تعذّرت", lines[0])

    def test_a_tool_repo_card_is_not_limited(self):
        lines, pushes, state = self.run_gated(5, platform=False)
        self.assertEqual(state, "pushed")

    def test_deferral_is_logged_once_across_repeated_cycles(self):
        self.run_gated(2)
        self.run_gated(2)
        log = (self.tmp / "pump.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(log), 1)
        self.assertIn("دفع:", log[0])

    def test_a_dry_run_writes_no_log(self):
        self.run_gated(2, apply=False)
        self.assertFalse((self.tmp / "pump.log").exists())

    def test_the_cap_counts_pushes_of_the_same_cycle(self):
        items = {"W-1": {"approved_head": "aaaaaaaa"}, "W-2": {"approved_head": "aaaaaaaa"}}
        with mock.patch("push_watch.find_tree", return_value=({"path": "C:/repo/wt1", "branch": "w1"}, "")):
            keep, lines = fp.defer_for_ci(items, ["C:/repo"], lambda *a: (0, "git@github.com:x/shschool_mvp.git"), lambda: 1,
                                          ready=lambda cid, tree: True)
        self.assertEqual(sorted(keep), ["W-1"])
        self.assertEqual(len(lines), 1)
        self.assertIn("W-2", lines[0])

    def test_a_card_the_guard_refuses_takes_no_slot_so_the_ready_one_after_it_pushes(self):
        """(10-28، W-20261027-031) بطاقةٌ بلا إيصالٍ قبلها في الترتيب كانت تحجز الخانةَ ثمّ يرفضها الحارس فتُؤجَّل الجاهزة."""
        items = {"W-1": {"approved_head": "aaaaaaaa"}, "W-2": {"approved_head": "aaaaaaaa"}}
        with mock.patch("push_watch.find_tree", return_value=({"path": "C:/repo/wt1", "branch": "w1"}, "")):
            keep, lines = fp.defer_for_ci(items, ["C:/repo"], lambda *a: (0, "git@github.com:x/shschool_mvp.git"), lambda: 1,
                                          ready=lambda cid, tree: cid == "W-2")
        self.assertEqual((sorted(keep), lines), (["W-1", "W-2"], []))

    def test_the_18_32_incident_two_refused_cards_before_a_ready_one_push_it(self):
        """(10-28 18:32، W-20261028-029) بطاقتان بلا إيصال أو بلا approval_check قبل سليمة لا تحجزان خانة؛ السليمةُ تُدفع."""
        items = {"W-1": {"approved_head": "aaaaaaaa"}, "W-2": {"approved_head": "aaaaaaaa"}, "W-3": {"approved_head": "aaaaaaaa"}}
        with mock.patch("push_watch.find_tree", return_value=({"path": "C:/repo/wt1", "branch": "w1"}, "")):
            keep, lines = fp.defer_for_ci(items, ["C:/repo"], lambda *a: (0, "git@github.com:x/shschool_mvp.git"), lambda: 1,
                                          ready=lambda cid, tree: cid == "W-3")
        self.assertEqual((sorted(keep), lines), (["W-1", "W-2", "W-3"], []))

    def test_the_default_readiness_is_the_push_guard_itself(self):
        (self.gitdir / fp.ledger.RECEIPT_NAME).write_text(json.dumps({"head": "aaaaaaaa", "ok": True}), encoding="utf-8")
        states = fp.ledger.reduce_state(fp.ledger.load_events(self.path))
        tree = {"path": "C:/repo/wt1", "branch": "w20261020-001-x"}
        git = self.git("w20261020-001-x")
        self.assertTrue(fp.guard_passes(self.card, tree, states, git, lambda c, h: True))
        self.assertFalse(fp.guard_passes(self.card, tree, states, git, lambda c, h: False))
        (self.gitdir / fp.ledger.RECEIPT_NAME).unlink()
        self.assertFalse(fp.guard_passes(self.card, tree, states, git, lambda c, h: True))


class TreePass(unittest.TestCase):
    """(W-20261023-016) مرحلة الشجرة: git وهميّ؛ لا تُنشأ شجرةٌ إلا على فرعٍ محلّيٍّ رأسُه الرأسُ المعتمَد بالضبط."""

    NO_TREE = (None, "لا شجرةَ على الرأس aaaaaaaa بفرع claude/* يحمل رمز W-1")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        p = mock.patch.object(fp, "LOG", self.tmp / "pump.log")
        p.start()
        self.addCleanup(p.stop)
        self.states = {"W-1": {"state": "approved", "approved_head": "aaaaaaaa"}}

    def git(self, branches=(("claude/w1-x", "a" * 40),), origin="https://github.com/sh-school/shschool_mvp.git", grep="a" * 40, add_rc=0):
        calls = []

        def git(repo, *args):
            calls.append(args)
            if args[0] == "remote":
                return 0, origin + "\n"
            if args[0] == "for-each-ref":
                return 0, "".join(f"{n} {s}\n" for n, s in branches)
            if args[0] == "log":
                return 0, grep + "\n"
            if args[0] == "worktree" and args[1] == "add":
                return add_rc, "" if not add_rc else "fatal: already checked out"
            return 0, ""

        git.calls = calls
        return git

    def run_pass(self, apply=True, states=None, find=None, **kw):
        git = kw.pop("git", None) or self.git()
        with mock.patch("push_watch.find_tree", return_value=find or self.NO_TREE):
            lines = fp.tree_pass(states or self.states, apply, repos=[str(self.tmp)], git=git, platform=str(self.tmp), **kw)
        return lines, git

    def adds(self, git):
        return [c for c in git.calls if c[:2] == ("worktree", "add")]

    def test_apply_adds_a_worktree_on_the_branch_at_the_approved_head(self):
        lines, git = self.run_pass()
        dest = str(self.tmp / ".claude" / "worktrees" / "pump-W-1")
        self.assertEqual(self.adds(git), [("worktree", "add", dest, "claude/w1-x")])
        self.assertIn("✔", lines[0])

    def test_dry_run_creates_nothing(self):
        lines, git = self.run_pass(apply=False)
        self.assertEqual(self.adds(git), [])
        self.assertIn("(عرض)", lines[0])

    def test_a_card_that_already_has_a_tree_is_untouched(self):
        lines, git = self.run_pass(find=({"path": "C:/x", "branch": "w1", "head": "a" * 40}, ""))
        self.assertEqual((lines, self.adds(git)), ([], []))

    def test_no_local_branch_on_the_head_is_report_only(self):
        lines, git = self.run_pass(git=self.git(branches=(("claude/w1-x", "b" * 40),)))
        self.assertEqual(self.adds(git), [])
        self.assertIn("تبليغ فقط", lines[0])
        self.assertIn("W-1", lines[0])

    def test_a_branch_outside_the_allowed_patterns_is_never_used(self):
        lines, git = self.run_pass(git=self.git(branches=(("main", "a" * 40), ("feature/x", "a" * 40))))
        self.assertEqual(self.adds(git), [])

    def test_a_branch_without_the_card_code_in_its_commits_is_never_used(self):
        lines, git = self.run_pass(git=self.git(grep=""))
        self.assertEqual(self.adds(git), [])

    def test_two_branches_on_the_head_is_ambiguous_and_nothing_is_created(self):
        lines, git = self.run_pass(git=self.git(branches=(("claude/a", "a" * 40), ("w1-b", "a" * 40))))
        self.assertEqual(self.adds(git), [])
        self.assertIn("التباس", lines[0])

    def test_an_existing_path_is_never_touched(self):
        (self.tmp / ".claude" / "worktrees" / "pump-W-1").mkdir(parents=True)
        lines, git = self.run_pass()
        self.assertEqual(self.adds(git), [])
        self.assertIn("لا لمس", lines[0])

    def test_other_repository_or_non_approved_cards_are_skipped(self):
        lines, git = self.run_pass(git=self.git(origin="https://github.com/x/maestro-v2.git"))
        self.assertEqual((lines, self.adds(git)), ([], []))
        lines, git = self.run_pass(states={"W-1": {"state": "pushed", "approved_head": "aaaaaaaa"}})
        self.assertEqual((lines, git.calls), ([], []))

    def test_the_cycle_limit_defers_the_rest(self):
        states = {c: {"state": "approved", "approved_head": "aaaaaaaa"} for c in ("W-1", "W-2", "W-3")}
        lines, git = self.run_pass(states=states, limit=2)
        self.assertEqual(len(self.adds(git)), 2)
        self.assertTrue(any("الدورة التالية" in x for x in lines))

    def test_a_failed_add_is_reported_not_forced(self):
        lines, git = self.run_pass(git=self.git(add_rc=128))
        self.assertIn("✘", lines[0])
        self.assertNotIn("--force", sum((list(c) for c in git.calls), []))


class OpenPrPass(unittest.TestCase):
    """(W-20261023-016) فتحُ الطلب لبطاقة pushed بلا طلب: gh وgit وهميّان؛ لا دمجَ ولا --auto في أيّ حال."""

    HEAD = "d" * 40
    CARD = "W-5"
    URL = "https://github.com/sh-school/shschool_mvp/pull/321\n"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        p = mock.patch.object(fp, "LOG", self.tmp / "pump.log")
        p.start()
        self.addCleanup(p.stop)
        self.states = {self.CARD: {"state": "pushed", "approved_head": "dddddddd", "problem": "مشكلةٌ عربيّة", "accept": "قبولٌ عربيّ"}}

    def git(self, remote=None, rc=0):
        remote = [("claude/w5-x", self.HEAD)] if remote is None else remote

        def git(repo, *args):
            if args[:2] == ("ls-remote", "--heads"):
                return rc, "".join(f"{sha}\trefs/heads/{n}\n" for n, sha in remote)
            return 0, ""

        return git

    def sh(self, known=(), files=("clinic/services.py", "tests/test_x.py"), create=(0, URL), compare_rc=0):
        calls = []

        def sh(cmd, cwd=None):
            calls.append(cmd)
            if cmd[:3] == ["gh", "pr", "list"]:
                return 0, json.dumps(list(known))
            if cmd[:2] == ["gh", "api"]:
                return compare_rc, "\n".join(files) + "\n"
            if cmd[:3] == ["gh", "pr", "create"]:
                return create
            return 0, ""

        sh.calls = calls
        return sh

    def run_pass(self, apply=True, prs=(), approved=True, line="اعتُمد من المالك مباشرةً بلا معاينة 8500 — 2026-10-23 — الرأس dddddddd — W-5",
                 states=None, git=None, sh=None, **kw):
        sh = sh or self.sh()
        with (
            mock.patch.object(fp, "approval_ok", return_value=approved),
            mock.patch.object(fp, "approval_line", return_value=line),
            mock.patch.object(fp.ledger, "add_note") as note,
            mock.patch.object(fp.ac, "security_approved", return_value=None),
        ):
            lines = fp.openpr_pass(states or self.states, list(prs), apply, git=git or self.git(), sh=sh, platform=str(self.tmp), **kw)
        return lines, sh, note

    def creates(self, sh):
        return [c for c in sh.calls if c[:3] == ["gh", "pr", "create"]]

    def test_apply_opens_the_pr_with_arabic_title_and_card_fields_then_notes_the_number(self):
        bodies = []
        base = self.sh()

        def sh(cmd, cwd=None):
            if cmd[:3] == ["gh", "pr", "create"]:
                bodies.append(Path(cmd[cmd.index("--body-file") + 1]).read_text(encoding="utf-8"))
            return base(cmd, cwd)

        sh.calls = base.calls
        lines, _, note = self.run_pass(sh=sh)
        cmd = self.creates(base)[0]
        self.assertEqual(cmd[cmd.index("--head") + 1], "claude/w5-x")
        self.assertEqual(cmd[cmd.index("--base") + 1], "main")
        self.assertEqual(cmd[cmd.index("--repo") + 1], "sh-school/shschool_mvp")
        self.assertIn("W-5", cmd[cmd.index("--title") + 1])
        self.assertTrue(bodies[0].startswith("اعتُمد من المالك"))
        self.assertIn("مشكلةٌ عربيّة", bodies[0])
        self.assertIn("قبولٌ عربيّ", bodies[0])
        self.assertIn("W-5", bodies[0])
        note.assert_called_once()
        self.assertIn("#321", note.call_args.args[1])
        self.assertIn("✔", lines[0])

    def test_never_merges_or_arms_auto_merge(self):
        _, sh, _ = self.run_pass()
        self.assertFalse(any(c[:3] == ["gh", "pr", "merge"] or "--auto" in c for c in sh.calls))

    def test_dry_run_opens_nothing_and_writes_nothing(self):
        lines, sh, note = self.run_pass(apply=False)
        self.assertEqual(self.creates(sh), [])
        note.assert_not_called()
        self.assertIn("(عرض)", lines[0])

    def test_a_governance_card_opens_its_pr_in_maestro_v2_not_the_platform(self):
        """(10-28) فرعُ بطاقة الحوكمة بعيدٌ في maestro-v2 لا المنصّة: كان يُقال «لا فرعَ بعيداً» ولا يُفتح طلب."""
        def git(repo, *args):
            if args[:2] == ("ls-remote", "--heads"):
                return 0, (f"{self.HEAD}\trefs/heads/claude/w5-gov\n" if repo == "GOV" else "")
            return 0, ""

        lines, sh, note = self.run_pass(git=git, gov="GOV")
        made = self.creates(sh)
        self.assertEqual(len(made), 1)
        self.assertEqual(made[0][made[0].index("--repo") + 1], fp.GOV_SLUG)
        self.assertTrue(any(c[:2] == ["gh", "api"] and f"repos/{fp.GOV_SLUG}/" in c[2] for c in sh.calls))
        self.assertIn("✔", lines[0])

    def test_a_remote_head_that_differs_from_the_approved_head_is_never_opened(self):
        lines, sh, _ = self.run_pass(git=self.git(remote=[("claude/w5-x", "e" * 40)]))
        self.assertEqual(self.creates(sh), [])
        self.assertIn("لا فرعَ بعيداً", lines[0])

    def test_a_ledger_branch_that_moved_is_reported_as_mismatch(self):
        states = {self.CARD: {**self.states[self.CARD], "branch": "claude/w5-x"}}
        lines, sh, _ = self.run_pass(states=states, git=self.git(remote=[("claude/w5-x", "e" * 40)]))
        self.assertEqual(self.creates(sh), [])
        self.assertIn("يخالف", lines[0])

    def test_unstable_approval_blocks(self):
        lines, sh, _ = self.run_pass(approved=False)
        self.assertEqual(self.creates(sh), [])
        self.assertIn("بلا اعتمادٍ ثابت", lines[0])

    def test_forbidden_categories_are_not_opened(self):
        for files, word in ((("app/migrations/0001_x.py",), "هجرات"), (("core/permissions.py",), "أمن"), (("accounts/rls.py",), "أمنيّ")):
            lines, sh, _ = self.run_pass(sh=self.sh(files=files))
            self.assertEqual(self.creates(sh), [], files)
            self.assertIn(word, lines[0], files)

    def test_a_wide_branch_is_not_opened(self):
        lines, sh, _ = self.run_pass(sh=self.sh(files=[f"docs/f{i}.md" for i in range(fp.MAX_FILES)]))
        self.assertEqual(self.creates(sh), [])

    def test_an_existing_open_or_merged_pr_means_no_new_one(self):
        for known in ([{"number": 9, "state": "OPEN", "headRefOid": self.HEAD}], [{"number": 9, "state": "MERGED", "headRefOid": "f" * 40}]):
            _, sh, _ = self.run_pass(sh=self.sh(known=known))
            self.assertEqual(self.creates(sh), [])
        pr = {"number": 9, "headRefName": "claude/w5-x", "headRefOid": self.HEAD, "title": "W-5", "body": "", "baseRefName": "main"}
        _, sh, _ = self.run_pass(prs=[pr])
        self.assertEqual(self.creates(sh), [])

    def test_unreadable_remote_or_gh_or_compare_opens_nothing(self):
        lines, sh, _ = self.run_pass(git=self.git(rc=1))
        self.assertEqual(self.creates(sh), [])
        lines, sh, _ = self.run_pass(sh=self.sh(compare_rc=1))
        self.assertEqual(self.creates(sh), [])
        self.assertIn("تعذّر", lines[0])

    def test_no_approval_line_source_means_no_pr(self):
        lines, sh, _ = self.run_pass(line=None)
        self.assertEqual(self.creates(sh), [])

    def test_a_gh_failure_is_reported_and_no_note_is_written(self):
        lines, _, note = self.run_pass(sh=self.sh(create=(1, "GraphQL: boom")))
        note.assert_not_called()
        self.assertIn("✘", lines[0])

    def test_only_pushed_cards_with_a_head_are_considered(self):
        states = {"W-1": {"state": "approved", "approved_head": "dddddddd"}, "W-2": {"state": "pushed"}}
        lines, sh, _ = self.run_pass(states=states)
        self.assertEqual((lines, sh.calls), ([], []))

    def test_the_cycle_limit_defers_the_rest(self):
        states = {c: {**self.states[self.CARD]} for c in ("W-5", "W-6", "W-7")}
        git = self.git(remote=[("claude/w5-x", "d" * 40)])
        lines, sh, _ = self.run_pass(states=states, git=git, limit=1)
        self.assertEqual(len(self.creates(sh)), 1)


class Stages(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        for name in ("LOCK", "LOG", "OFF", "NO_MERGE", "NO_PREPUSH", "NO_TREE", "NO_OPENPR"):
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
            mock.patch.object(fp, "tree_pass", side_effect=stage("tree")),
            mock.patch.object(fp, "prepush_pass", side_effect=stage("prepush")),
            mock.patch.object(fp, "push_pass", side_effect=stage("push")),
            mock.patch.object(fp, "openpr_pass", side_effect=stage("openpr")),
            mock.patch.object(fp, "line_pass", side_effect=stage("line")),
            mock.patch.object(fp, "merge_pass", side_effect=stage("merge")),
            mock.patch.object(fp.ledger_sync, "cycle", return_value=0),
            mock.patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            fp._run(argv)  # بلا main: main يعيد ضبطَ ترميز stdout ولا يقبله StringIO
        return called, out.getvalue()

    def test_all_stages_run_in_order(self):
        called, _ = self.run_main(["--apply"])
        self.assertEqual(called, ["approve", "prs", "waive", "tree", "prepush", "push", "openpr", "line", "merge"])

    def test_each_stage_can_be_switched_off(self):
        called, _ = self.run_main(["--apply", "--no-push", "--no-line", "--no-merge", "--no-open-pr"])
        self.assertEqual(called, ["approve", "prs", "waive"])

    def test_the_prepush_stage_has_its_own_switches(self):
        called, _ = self.run_main(["--apply", "--no-prepush"])
        self.assertEqual(called, ["approve", "prs", "waive", "tree", "push", "openpr", "line", "merge"])
        fp.NO_PREPUSH.write_text("")
        called, out = self.run_main(["--apply"])
        self.assertEqual(called, ["approve", "prs", "waive", "tree", "push", "openpr", "line", "merge"])
        self.assertIn("prepush: معطَّل", out)

    def test_the_no_merge_switch_skips_only_the_merge_stage(self):
        fp.NO_MERGE.write_text("")
        called, out = self.run_main(["--apply"])
        self.assertEqual(called, ["approve", "prs", "waive", "tree", "prepush", "push", "openpr", "line"])
        self.assertIn("دمج: معطَّل", out)

    def test_tree_and_open_pr_have_their_own_switches(self):
        called, _ = self.run_main(["--apply", "--no-tree", "--no-open-pr"])
        self.assertEqual(called, ["approve", "prs", "waive", "prepush", "push", "line", "merge"])
        fp.NO_TREE.write_text("")
        fp.NO_OPENPR.write_text("")
        called, out = self.run_main(["--apply"])
        self.assertEqual(called, ["approve", "prs", "waive", "prepush", "push", "line", "merge"])
        self.assertIn("شجرة: معطَّلة", out)
        self.assertIn("طلب: معطَّل", out)

    def test_open_pr_is_skipped_when_open_prs_are_unreadable(self):
        called, _ = self.run_main(["--apply"], prs=None)
        self.assertNotIn("openpr", called)

    def test_unreadable_prs_are_reported_not_taken_as_none(self):
        called, out = self.run_main([], prs=None)
        self.assertIn("تعذّرت قراءةُ الطلبات", out)


if __name__ == "__main__":
    unittest.main()


class CiPass(unittest.TestCase):
    def _run(self, checks, done=None, apply=True):
        from datetime import datetime, timezone

        states = {"W-9": {"state": "approved", "approved_head": "aaaaaaaa"}}
        prs = [{"number": 7, "headRefOid": "a" * 40}]
        calls = []

        def sh(cmd, cwd=None):
            calls.append(cmd)
            return (0, json.dumps(checks)) if cmd[:3] == ["gh", "pr", "checks"] else (0, "")

        tmp = Path(tempfile.mkdtemp()) / "r.json"
        if done:
            tmp.write_text(json.dumps(done))
        now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
        with mock.patch.object(fp, "RERUNS", tmp), mock.patch.object(fp, "approved_prs", lambda s, p: [("W-9", prs[0], {})]), \
                mock.patch.object(fp.ledger, "add_note") as note:
            out = fp.ci_pass(states, prs, apply, sh, now)
        return out, calls, note

    def test_failed_check_is_rerun_once(self):
        link = "https://github.com/o/r/actions/runs/123/job/9"
        out, calls, _ = self._run([{"name": "axe", "bucket": "cancel", "link": link}])
        self.assertIn(["gh", "run", "rerun", "123", "--failed"], calls)
        out2, calls2, _ = self._run([{"name": "axe", "bucket": "cancel", "link": link}], done={"7:aaaaaaaa": 1})
        self.assertFalse(any(c[:3] == ["gh", "run", "rerun"] for c in calls2))
        self.assertIn("لا إعادة ثانية", out2[0])

    def test_pending_over_threshold_notes_once(self):
        out, _, note = self._run([{"name": "e2e", "bucket": "pending", "startedAt": "2026-10-23T11:00:00Z", "link": ""}])
        note.assert_called_once()
        self.assertIn("معلَّق", out[0])

    def test_fresh_pending_is_ignored(self):
        out, _, note = self._run([{"name": "e2e", "bucket": "pending", "startedAt": "2026-10-23T11:50:00Z", "link": ""}])
        self.assertEqual(out, [])
        note.assert_not_called()


def test_pr_body_names_only_its_own_card():
    """وصفُ الطلب يذكر بطاقتَه وحدها: رقمُ بطاقة المضخّة فيه كان يُوهم مضخّةَ التدفّق بتعارضٍ فترفض الطلب."""
    body = fp._pr_body("سطر الاعتماد", "W-20261013-004", {"problem": "م", "accept": "ق"})
    assert body.count("W-") == 1 and "W-20261013-004" in body


class FailureCond(unittest.TestCase):
    """(10-28) فشلُ prepush: علّةُ البيئة للأتمتة، والفحصُ الأحمر في الشيفرة لحامل البطاقة."""

    def test_timeout_and_missing_tools_are_the_environment(self):
        for code in (3, 124, 127):
            self.assertEqual(fp.failure_cond(code, ""), "prepush_env", code)

    def test_every_failure_line_carrying_winerror_is_the_environment(self):
        log = "FAILED a::t - OSError: [WinError 6] The handle is invalid\nERROR b::u - OSError: [WinError 6]\n2 failed"
        self.assertEqual(fp.failure_cond(1, log), "prepush_env")

    def test_truncated_summary_lines_are_judged_by_their_reason_lines(self):
        """ملخّصُ pytest يقصّ FAILED/ERROR فتضيع العلامة؛ يُحكم بأسطر «E »: كلُّ فشلٍ سببُه علّةُ بيئة."""
        env = "ERROR tools/test_a.py::t - OSE...\nE   OSError: [WinError 6] The handle is invalid\n1 error"
        self.assertEqual(fp.failure_cond(1, env), "prepush_env")
        browser = "ERROR t::a - pla...\nE   playwright._impl._errors.Error: BrowserType.launch: Executable doesn't exist\n1 error"
        self.assertEqual(fp.failure_cond(1, browser), "prepush_env")
        mixed = "FAILED t::a - Ass...\nE   AssertionError\nERROR t::b - OSE...\nE   OSError: [WinError 6]\n1 failed, 1 error"
        self.assertEqual(fp.failure_cond(1, mixed), "prepush")

    def test_one_unmarked_failure_line_makes_it_the_code(self):
        self.assertEqual(fp.failure_cond(1, "FAILED a::t - OSError: [WinError 6]\nFAILED b::u - AssertionError"), "prepush")
        self.assertEqual(fp.failure_cond(1, "✘ ruff check: فشل"), "prepush")
        self.assertEqual(fp.failure_cond(1, "شيءٌ آخر"), "prepush")


class HandOff(unittest.TestCase):
    """جدولُ شرط←مالك: يسمّي المالك، ويُلحق رسالةً بصندوقه عند التطبيق فقط، ولا يكرّرها خلال ست ساعات (W-20261027-006)."""

    def setUp(self):
        self.path = Path(tempfile.mkdtemp())
        self.item = {"state": "approved", "held_by": "0408"}

    def _rows(self, owner="0501"):
        import inbox

        return [r for r in inbox._rows(owner, self.path) if r["k"] == "msg"]

    def test_owner_table(self):
        """(10-28) prepush الأحمر لحامل البطاقة (عيبٌ في شيفرتها)، والبيئيُّ للأتمتة؛ لا 0501 التي لا تكتب شيفرة."""
        live = lambda num, root: True  # noqa: E731
        for cond, owner in (("visual_evidence", "0502"), ("head_unapproved", "0101"), ("migrations", "0601"), ("prepush", "0408"),
                            ("prepush_env", "0701")):
            self.assertEqual(fp.hand_off("W-1", cond, self.item, False, self.path, alive=live), f"[مالك={owner}]")

    def test_pushed_no_pr_goes_to_card_holder_and_unknown_is_marked(self):
        self.assertEqual(fp.hand_off("W-1", "pushed_no_pr", self.item, False, self.path, alive=lambda n, r: True), "[مالك=0408]")
        self.assertEqual(fp.hand_off("W-1", "pushed_no_pr", {"state": "approved"}, False, self.path), "[مالك=؟]")

    def test_a_holder_without_a_live_watcher_goes_to_the_router_with_the_reason(self):
        """(10-28) 035 عند 0420 المؤرشفة: رسالةُ صندوقٍ لا يقرؤه أحد؛ تُحال إلى 0101 لإعادة التكليف ومعها السبب والسجلّ."""
        self.assertEqual(fp.hand_off("W-1", "prepush", self.item, False, self.path, alive=lambda n, r: False), f"[مالك={fp.ROUTER}]")
        t0 = datetime(2026, 10, 28, 10, 0).astimezone()
        fp.hand_off("W-1", "prepush", self.item, True, self.path, t0, detail="رمز الخروج 1 — السجلّ ledger/x.log", alive=lambda n, r: False)
        text = self._rows(fp.ROUTER)[0]["text"]
        self.assertIn("الحامل 0408 بلا مراقبٍ حيّ", text)
        self.assertIn("ledger/x.log", text)
        self.assertEqual(self._rows("0408"), [])

    def test_a_watcher_beat_keeps_the_message_with_the_holder(self):
        import inbox

        inbox.beat("0408", self.path)
        self.assertEqual(fp.hand_off("W-1", "prepush", self.item, False, self.path), "[مالك=0408]")

    def test_dry_run_writes_nothing(self):
        fp.hand_off("W-1", "prepush", self.item, False, self.path)
        self.assertEqual(self._rows(), [])
        self.assertFalse((self.path / "ledger").exists())

    def test_apply_writes_row_once_within_six_hours(self):
        t0 = datetime(2026, 10, 24, 10, 0).astimezone()
        fp.hand_off("W-1", "migrations", self.item, True, self.path, t0)
        fp.hand_off("W-1", "migrations", self.item, True, self.path, t0 + timedelta(hours=5))
        self.assertEqual(len(self._rows("0601")), 1)
        row = self._rows("0601")[0]
        self.assertEqual((row["from"], row["text"].startswith("[مضخّة:W-1:migrations:approved]")), (fp.PUMP_FROM, True))
        self.assertFalse((self.path / "ledger" / "pending_wakes.jsonl").exists())
        fp.hand_off("W-1", "migrations", self.item, True, self.path, t0 + timedelta(hours=7))
        self.assertEqual(len(self._rows("0601")), 2)


class DisarmPass(unittest.TestCase):
    """W-20261028-032 (واقعة #1285): الدمجُ الآليّ يتحقّق من الرأس عند التفعيل فقط؛ رأسٌ تغيّر بعده بلا اعتمادٍ يُعطَّل التفعيلُ."""

    NEW = "99999999" + "0" * 32

    def run_pass(self, pr, ok=False, apply=True):
        sh = FakeSh()
        with (
            mock.patch.object(fp, "approval_ok", return_value=ok),
            mock.patch.object(fp.ledger, "add_note") as note,
            mock.patch("inbox.send") as send,
        ):
            lines = fp.disarm_pass(_states(), [pr], apply, sh)
        return lines, sh, note, send

    def test_armed_pr_with_unapproved_new_head_is_disarmed_and_reported(self):
        lines, sh, note, send = self.run_pass(_pr(head=self.NEW, autoMergeRequest={"mergeMethod": "SQUASH"}))
        self.assertIn(["gh", "pr", "merge", "7", "--disable-auto"], sh.calls)
        note.assert_called_once()
        self.assertEqual(send.call_args[0][0], "0601")
        self.assertIn("#7", lines[0])

    def test_approved_head_or_unarmed_pr_is_left_alone(self):
        for pr, ok in ((_pr(head=self.NEW, autoMergeRequest={"mergeMethod": "SQUASH"}), True), (_pr(head=self.NEW), False)):
            lines, sh, note, send = self.run_pass(pr, ok=ok)
            self.assertEqual((lines, sh.calls), ([], []))
            note.assert_not_called()

    def test_dry_run_disarms_nothing(self):
        lines, sh, note, send = self.run_pass(_pr(head=self.NEW, autoMergeRequest={"mergeMethod": "SQUASH"}), apply=False)
        self.assertEqual(sh.calls, [])
        self.assertIn("(عرض)", lines[0])


class MergeWindow(unittest.TestCase):
    """W-20261028-006: نافذتا الدمج الآليّ 14:30–16:30 و19:00–21:00 بالدوحة؛ البدايةُ مشمولةٌ والنهايةُ لا."""

    @staticmethod
    def at(h, m, day=30):
        return datetime(2026, 10, day, h, m, tzinfo=fp.ledger.DOHA)

    def test_boundaries_of_both_windows(self):
        cases = {
            (14, 29): None, (14, 30): "2026-10-30:1", (16, 29): "2026-10-30:1", (16, 30): None,
            (18, 59): None, (19, 0): "2026-10-30:2", (20, 59): "2026-10-30:2", (21, 0): None,
            (0, 0): None, (12, 0): None,
        }
        for (h, m), want in cases.items():
            self.assertEqual(fp.merge_window(self.at(h, m)), want, f"{h}:{m}")

    def test_window_follows_doha_clock_not_the_machine_zone(self):
        utc = datetime(2026, 10, 30, 11, 30, tzinfo=timezone.utc)  # 14:30 بالدوحة
        self.assertEqual(fp.merge_window(utc), "2026-10-30:1")

    def test_outside_window_no_gh_call_and_one_line(self):
        sh = ViewSh()
        with (
            mock.patch.object(fp, "approval_ok", return_value=True),
            mock.patch.object(fp.ac, "security_approved", return_value=None),
        ):
            lines = fp.merge_pass(_states(), [_pr(body=LINED)], True, sh, now=self.at(16, 30))
        self.assertEqual(sh.calls, [])
        self.assertEqual(len(lines), 1)
        self.assertIn("خارج نافذة النشر", lines[0])

    def run_in_window(self, prs, state_path, ok=True):
        sh = ViewSh()
        with (
            mock.patch.object(fp, "approval_ok", return_value=ok),
            mock.patch.object(fp.ac, "security_approved", return_value=None),
            mock.patch.object(fp, "MERGE_WINDOW_STATE", state_path),
            mock.patch("inbox.send") as send,
        ):
            lines = fp.merge_pass(_states(), prs, True, sh, now=self.at(15, 0))
        return lines, sh, send

    def test_eligible_pr_is_armed_once_inside_window(self):
        with tempfile.TemporaryDirectory() as d:
            lines, sh, _ = self.run_in_window([_pr(body=LINED)], Path(d) / "w.json")
        merges = [c for c in sh.calls if c[:3] == ["gh", "pr", "merge"]]
        self.assertEqual(len(merges), 1)
        self.assertTrue(any("✔" in x for x in lines))

    def test_ineligible_is_reported_to_0601_once_per_window(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "w.json"
            _, sh, send = self.run_in_window([_pr(body=LINED)], state, ok=False)
            self.assertEqual([c for c in sh.calls if c[:3] == ["gh", "pr", "merge"]], [])
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args.args[0], "0601")
            _, _, send2 = self.run_in_window([_pr(body=LINED)], state, ok=False)
            self.assertEqual(send2.call_count, 0)  # لا تكرار في دورةٍ ثانية من النافذة نفسها

    def test_state_records_eligible_and_armed(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "w.json"
            self.run_in_window([_pr(body=LINED)], state)
            entry = json.loads(state.read_text(encoding="utf-8"))["2026-10-30:1"]
        self.assertEqual(entry["eligible"], [7])
        self.assertEqual(entry["armed"], [7])
