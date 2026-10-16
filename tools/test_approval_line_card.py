"""اختباراتُ سطر الاعتماد الرابط للرمز والرأس (W-20261016-018) وإعفاء auto المحصور بنوعين."""

import approval_check as ac
import ledger
import pr_open_prep as pp
import pytest


def test_template_carries_card_and_head():
    line = pp.LINE_TEMPLATE.format(date="2026-10-17", card="W-20261016-018", head8="abcd1234")
    assert "W-20261016-018" in line and "abcd1234" in line and line.startswith("اعتُمد من المالك على 8500")
    assert ac.line_card_problem(line, "W-20261016-018") is None


def test_new_line_without_card_is_rejected():
    line = "اعتُمد من المالك على 8500 — 2026-10-17 — الرأس abcd1234"
    assert "رمزَ البطاقة" in ac.line_card_problem(line, "W-20261016-018")


def test_new_line_with_other_card_is_rejected():
    line = "اعتُمد من المالك على 8500 — 2026-10-17 — W-20261016-001 — الرأس abcd1234"
    assert "لا يطابق" in ac.line_card_problem(line, "W-20261016-018")


def test_old_line_is_unchanged():
    line = "اعتُمد من المالك على 8500 — 2026-10-10 — الرأس abcd1234"
    assert ac.line_card_problem(line, "W-20261010-001") is None


def test_auto_waive_refuses_anything_but_main_merge_or_tests_only(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise ledger.LedgerError("لا")

    monkeypatch.setattr(ledger, "check_main_merge", boom)
    monkeypatch.setattr(ledger, "check_tests_only", boom)
    path = str(tmp_path / "e.jsonl")
    cid = ledger.add_item("owner", "tool", "م", "أ", "ق", start="2026-10-17T08:00", priority="P2", path=path)
    ledger.append_event("state", cid, {"state": "approved", "by": "0501", "head": "abcd1234"}, path)
    with pytest.raises(ledger.LedgerError, match="لا إعفاءَ آليّاً"):
        ledger.waive_head(cid, "deadbeef", "0501", "سبب", path=path, kind="auto")


def test_auto_waive_picks_tests_only_when_main_merge_fails(monkeypatch, tmp_path):
    calls = []

    def no(*a, **k):
        raise ledger.LedgerError("لا")

    monkeypatch.setattr(ledger, "check_main_merge", no)
    monkeypatch.setattr(ledger, "check_tests_only", lambda *a, **k: calls.append("tests"))
    path = str(tmp_path / "e.jsonl")
    cid = ledger.add_item("owner", "tool", "م", "أ", "ق", start="2026-10-17T08:00", priority="P2", path=path)
    ledger.append_event("state", cid, {"state": "approved", "by": "0501", "head": "abcd1234"}, path)
    ledger.waive_head(cid, "deadbeef", "0501", "سبب", path=path, kind="auto")
    assert calls
    notes = ledger.reduce_state(ledger.load_events(path))[cid]["notes"]
    assert any("إصلاحُ اختباراتٍ فقط" in str(n) for n in notes)
