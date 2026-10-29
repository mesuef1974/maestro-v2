from __future__ import annotations

from datetime import date

import approval_check as ac
import ledger
import pytest


def test_same_head_ok():
    assert ac.head_status("abcd1234", "abcd1234ffff") == "ok"


def test_changed_head_is_stale():
    assert ac.head_status("abcd1234", "f2901e49") == "stale"


def test_no_head_is_legacy_until_deadline_then_expired():
    assert ac.head_status(None, "f2901e49", date(2026, 10, 9)) == "legacy"
    assert ac.head_status(None, "f2901e49", date(2026, 10, 10)) == "expired"


def test_pr_line_with_other_head_is_stale():
    h = ac.HEAD_IN_LINE.search("اعتُمد من المالك على 8500 — 2026-10-02 — الرأس 0123abcd")
    assert h and ac.head_status(h.group(1), "f2901e49") == "stale"


def test_ledger_approval_requires_head():
    with pytest.raises(ledger.LedgerError):
        ledger.check_head("approved", None)
    assert ledger.check_head("approved", "ABCDEF".lower() + "12") == "abcdef12"
    assert ledger.check_head("pushed", None) is None


def test_waiver_only_for_0501_and_docs(tmp_path):
    p = tmp_path / "ev.jsonl"
    iid = ledger.add_item("owner", "bug", "م", "أ", "ق", path=p, start="2026-10-02T10:00", priority="P2")
    ledger.append_event("state", iid, {"state": "approved", "by": "0501", "head": "aaaa1111"}, p)
    with pytest.raises(ledger.LedgerError):
        ledger.waive_head(iid, "bbbb2222", "0405", "x", path=p, changed=["docs/a.md"])
    with pytest.raises(ledger.LedgerError):
        ledger.waive_head(iid, "bbbb2222", "0501", "x", path=p, changed=["core/permissions.py"])
    ledger.waive_head(iid, "bbbb2222", "0501", "وثيقةٌ فقط", path=p, changed=["docs/a.md"])
    assert ledger.reduce_state(ledger.load_events(p))[iid]["approved_head"] == "bbbb2222"


# ── البوّابةُ البصريّة (W-20261009-007) ─────────────────────────────────────────────

def test_ui_paths_are_detected_and_others_are_not():
    assert ac._is_ui_path("templates/dashboard/roles/director.html")
    assert ac._is_ui_path(ac.REPO_DIR.rstrip("/") + "/static/css/custom/40-themes.css")
    assert ac._is_ui_path("static" + chr(92) + "js" + chr(92) + "app.js")
    assert not ac._is_ui_path("operations/schedule_evaluator.py")
    assert not ac._is_ui_path("docs/visual_gate.md")


def test_non_ui_card_is_unchanged_by_the_visual_gate(monkeypatch):
    monkeypatch.setattr(ac, "ui_touched", lambda files, head: False)
    assert ac.visual_problem("W-20261009-007", "abcd1234") is None


def test_ui_card_without_evidence_fails_with_the_documented_message(monkeypatch, tmp_path):
    import visual_gate

    monkeypatch.setattr(ac, "ui_touched", lambda files, head: True)
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (0, '{"state": "captured"}'))  # لا يعتمد على بيانات الدفتر الحيّ
    monkeypatch.setattr(visual_gate, "EVIDENCE_DIR", tmp_path)
    msg = ac.visual_problem("W-20261009-007", "abcd1234")
    assert msg and "لا أدلة بصرية للرأس" in msg


def test_ui_card_without_a_head_cannot_be_checked(monkeypatch):
    monkeypatch.setattr(ac, "ui_touched", lambda files, head: True)
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (0, '{"state": "captured"}'))
    assert "لا أدلة بصرية" in ac.visual_problem("W-20261009-007", None)


def test_the_gate_is_active_from_the_owners_date():
    assert ac.VISUAL_GATE_FROM == "2026-10-10"


def test_a_ui_card_created_from_the_date_without_evidence_is_blocked(monkeypatch, tmp_path):
    import visual_gate

    monkeypatch.setattr(visual_gate, "EVIDENCE_DIR", tmp_path)
    monkeypatch.setattr(ac, "ui_touched", lambda files, head: True)
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (0, '{"state": "approved", "created": "2026-10-10T10:00:00+03:00"}'))
    msg = ac.visual_problem("W-20261010-001", "abcd1234", respect_cutoff=True)
    assert msg and "لا أدلة بصرية للرأس" in msg


def test_a_non_ui_card_created_from_the_date_is_not_blocked(monkeypatch):
    monkeypatch.setattr(ac, "ui_touched", lambda files, head: False)
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (0, '{"state": "approved", "created": "2026-10-11T10:00:00+03:00"}'))
    assert ac.visual_problem("W-20261011-001", "abcd1234", respect_cutoff=True) is None


def test_cards_created_before_the_gate_are_grandfathered_on_card_checks(monkeypatch):
    monkeypatch.setattr(ac, "VISUAL_GATE_FROM", "2026-10-09")
    monkeypatch.setattr(ac, "ui_touched", lambda files, head: True)
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (0, '{"state": "approved", "created": "2026-10-08T10:00:00+03:00"}'))
    assert ac.visual_problem("W-20261008-004", "abcd1234", respect_cutoff=True) is None
    assert ac.visual_problem("W-20261008-004", "abcd1234") is not None  # الأمر الصريح يفحص دائماً


def test_known_head_is_judged_by_actual_diff_not_ledger_files(monkeypatch):
    wide = ["operations/", "templates/", "static/", "tests/"]
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (0, "operations/x.py" + chr(10) + "tests/test_x.py"))
    assert ac.ui_touched(wide, "abcd1234") is False
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (0, "operations/x.py" + chr(10) + "templates/a/b.html"))
    assert ac.ui_touched([], "abcd1234") is True


def test_unknown_head_falls_back_to_ledger_files(monkeypatch):
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (128, ""))
    assert ac.ui_touched(["templates/a.html"], "abcd1234") is True
    assert ac.ui_touched(["operations/x.py"], "abcd1234") is False
    assert ac.ui_touched(["templates/a.html"], None) is True


def test_a_card_missing_from_the_ledger_is_treated_as_no_card(monkeypatch):
    """`ledger.py show` لبطاقةٍ غيرِ موجودة يطبع null: لا AttributeError في أيٍّ من الدوال الثلاث (W-20261017-020)."""
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (0, "null\n"))
    assert ac.card_evidence("W-20990101-999") == []
    assert ac.visual_problem("W-20990101-999", "abcd1234") is None
    assert ac.waiver_carry("W-20990101-999", "abcd1234", "W-20990101-999") == []


# ── التنازلُ البصريّ (قرار المالك D-352م) وامتدادُه التلقائيّ (D-356م) ─────────────────────

WAIVER = "تنازلٌ بصريّ بقرار المالك D-352م: الرأس bdcb4628 — معاينته اليدويّة بدل المانيفست"


def _card_with(*texts):
    return {"notes": [{"text": t} for t in texts]}


def test_waiver_applies_to_named_head_only(monkeypatch):
    monkeypatch.setattr(ac, "_diff_paths", lambda old, new: None)  # بلا امتداد: git يفشل
    card = _card_with(WAIVER)
    assert ac.visual_waived(card, "bdcb4628") is True
    assert ac.visual_waived(card, "bdcb46289abc") is True  # رأسٌ كاملٌ يبدأ بالثماني خانات
    assert ac.visual_waived(card, "c98dbd3d") is False
    assert ac.visual_waived(_card_with("ملاحظةٌ عاديّة فيها bdcb4628"), "bdcb4628") is False  # لا تبدأ بالعبارة


def test_waiver_extends_to_backend_only_head(monkeypatch):
    seen = []

    def fake(old, new):
        seen.append((old, new))
        return ["operations/schedule_edges.py", "tests/test_x.py"]

    monkeypatch.setattr(ac, "_diff_paths", fake)
    assert ac.visual_waived(_card_with(WAIVER), "63328b05") is True
    assert seen == [("bdcb4628", "63328b05")]


def test_waiver_does_not_extend_over_template_or_static(monkeypatch):
    monkeypatch.setattr(ac, "_diff_paths", lambda old, new: ["operations/a.py", "templates/schedule/x.html"])
    assert ac.visual_waived(_card_with(WAIVER), "63328b05") is False
    monkeypatch.setattr(ac, "_diff_paths", lambda old, new: ["static/css/custom/a.css"])
    assert ac.visual_waived(_card_with(WAIVER), "63328b05") is False


def test_waiver_does_not_extend_when_git_fails_or_other_card(monkeypatch):
    monkeypatch.setattr(ac, "_diff_paths", lambda old, new: None)
    assert ac.visual_waived(_card_with(WAIVER), "63328b05") is False
    monkeypatch.setattr(ac, "_diff_paths", lambda old, new: ["operations/a.py"])
    assert ac.visual_waived(_card_with(), "63328b05") is False  # بطاقةٌ بلا تنازلٍ في دفترها


def test_diff_paths_returns_none_on_git_failure(monkeypatch):
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (128, ""))
    assert ac._diff_paths("aaaaaaaa", "bbbbbbbb") is None
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (0, "a.py" + chr(10) + "b.py" + chr(10)))
    assert ac._diff_paths("aaaaaaaa", "bbbbbbbb") == ["a.py", "b.py"]


def test_waiver_accepts_ledger_author_prefix(monkeypatch):
    monkeypatch.setattr(ac, "_diff_paths", lambda old, new: None)
    assert ac.visual_waived(_card_with("(0502) " + WAIVER), "bdcb4628") is True  # ledger note --by يضيف «(NNNN) »
    assert ac.visual_waived(_card_with("(0502) ملاحظةٌ عاديّة bdcb4628"), "bdcb4628") is False


# ── إيصالُ الهويّة لرأس الإيداع (D-376م) ─────────────────────────────────────────

def test_identity_ack_is_off_by_default():
    assert ac.IDENTITY_ACK_FROM == ""
    assert ac.identity_ack_problem("W-1", "abcd1234ffff", "2026-10-11") is None


def test_identity_ack_requires_the_line_for_the_same_head(tmp_path, monkeypatch):
    import visual_gate

    monkeypatch.setattr(visual_gate, "EVIDENCE_DIR", tmp_path)
    assert "لا إيصالَ" in ac.identity_ack_problem("W-1", "abcd1234ffff", enforce=True)
    d = tmp_path / "W-1" / "abcd1234"
    d.mkdir(parents=True)
    (d / ac.IDENTITY_ACK_FILE).write_text("identity_ack: abcd1234 سقط\n", encoding="utf-8")
    assert ac.identity_ack_problem("W-1", "abcd1234ffff", enforce=True)
    (d / ac.IDENTITY_ACK_FILE).write_text("identity_ack: abcd1234 نجح\n", encoding="utf-8")
    assert ac.identity_ack_problem("W-1", "abcd1234ffff", enforce=True) is None
    # إيصالُ رأسٍ آخر لا يكفي
    assert ac.identity_ack_problem("W-1", "ffff0000aaaa", enforce=True)


def test_identity_ack_cutoff_by_card_creation_date(monkeypatch):
    monkeypatch.setattr(ac, "IDENTITY_ACK_FROM", "2026-10-12")
    assert ac.identity_ack_problem("W-1", "abcd1234", "2026-10-11") is None
    assert ac.identity_ack_problem("W-1", "abcd1234", "2026-10-12")


class TestHeadFromTargetColumn:
    """W-20261025-018: الرأسُ من عمود الهدف «بطاقة @رأس» لا من أوّل «الرأس/@» في السطر."""

    ROW = "| 2026-10-25 12:00 | 0101 (إفادةُ جلسة) | هل أعتمد على @11111111 كما سبق؟ | «اعتمد» | W-20261025-099 @22222222 |"

    def test_before_cutoff_keeps_old_head_but_warns_on_mismatch(self):
        head, warn = ac.row_head(self.ROW, date(2026, 10, 31))
        assert head == "11111111" and "22222222" in warn and "11111111" in warn

    def test_from_cutoff_reads_the_target_column(self):
        head, warn = ac.row_head(self.ROW, date(2026, 11, 1))
        assert head == "22222222" and warn == ""

    def test_agreeing_row_has_no_warning(self):
        row = "| 2026-10-25 12:00 | 0101 | س | «اعتمد» | W-1 @abcd1234 |"
        assert ac.row_head(row, date(2026, 10, 25)) == ("abcd1234", "")

    def test_missing_head_in_column_becomes_none_after_cutoff(self):
        row = "| 2026-10-25 | 0101 | الرأس aaaa1111 في السؤال | «اعتمد» | W-1 |"
        assert ac.row_head(row, date(2026, 11, 2))[0] is None
        assert ac.row_head(row, date(2026, 10, 30))[0] == "aaaa1111"

    def test_non_table_line_keeps_old_behaviour(self):
        assert ac.row_head("اعتُمد من المالك — الرأس abcd1234", date(2026, 12, 1)) == ("abcd1234", "")

    def test_refusal_text_never_counts_as_approval_even_with_matching_head(self, tmp_path):
        f = tmp_path / "oc.md"
        f.write_text("| 2026-10-25 | 0101 | هل أدمج؟ | «لا، ارفضه ولا تدمج» | W-20261025-098 @abcd1234 |\n", encoding="utf-8")
        rows = ac._confirmation_rows("W-20261025-098", "abcd1234", False, f)
        assert rows and rows[0][1] == "rejected"

    def test_confirmation_uses_column_head_after_cutoff(self, tmp_path, monkeypatch):
        f = tmp_path / "oc.md"
        f.write_text("| 2026-10-25 | 0101 | هل على @11111111؟ | «اعتمد» | W-20261025-097 @22222222 |\n", encoding="utf-8")
        monkeypatch.setattr(ac, "COLUMN_HEAD_FROM", date(2000, 1, 1))
        assert ac._confirmation_rows("W-20261025-097", "22222222", False, f)[0][1] == "ok"
        assert ac._confirmation_rows("W-20261025-097", "11111111", False, f)[0][1] == "stale"


def test_seven_char_approval_matches_eight_char_head():
    """W-20261029-007: اعتمادٌ مسجَّل بسبع خانات يطابق الرأس بثمانٍ."""
    assert ac.head_status("782d679", "782d679f") == "ok"
    assert ac.head_status("782d679f", "782d679") == "ok"
    assert ac.head_status("782d679", "782d679fabcdef") == "ok"


def test_short_or_different_prefix_is_still_stale():
    assert ac.head_status("782d67", "782d679f") == "stale"  # أقصر من 7
    assert ac.head_status("782d679", "782d680f") == "stale"
    assert ac.head_status("782d6791", "782d679f") == "stale"  # ثماني خانات مختلفة
