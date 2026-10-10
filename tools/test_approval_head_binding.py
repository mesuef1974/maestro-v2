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
    assert ac._is_ui_path("D:/shschool_mvp/static/css/custom/40-themes.css")
    assert ac._is_ui_path("static" + chr(92) + "js" + chr(92) + "app.js")
    assert not ac._is_ui_path("operations/schedule_evaluator.py")
    assert not ac._is_ui_path("docs/visual_gate.md")


def test_non_ui_card_is_unchanged_by_the_visual_gate(monkeypatch):
    monkeypatch.setattr(ac, "ui_touched", lambda files, head: False)
    assert ac.visual_problem("W-20261009-007", "abcd1234") is None


def test_ui_card_without_evidence_fails_with_the_documented_message(monkeypatch, tmp_path):
    import visual_gate

    monkeypatch.setattr(ac, "ui_touched", lambda files, head: True)
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
