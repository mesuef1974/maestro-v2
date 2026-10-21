"""اختباراتُ سطر الاعتماد الرابط للرمز والرأس (W-20261016-018) وإعفاء auto المحصور بالأنواع التي يثبتها الكود (D-451م)."""

import re

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


def test_template_puts_the_head_right_after_the_date_where_the_repo_check_reads_it():
    # منسوخٌ من D:/shschool_mvp (origin/main) scripts/pr_approval_head_check.py OWNER_HEAD (فوق auto_merge_gate.APPROVAL)
    owner_head = re.compile(r"اعتُمد من المالك (?:على 8500|مباشرةً بلا معاينة 8500) — \d{4}-\d{2}-\d{2}" + r"(?: — الرأس ([0-9a-f]{7,40}))?")
    line = pp.LINE_TEMPLATE.format(date="2026-10-21", card="W-20261016-018", head8="abcd1234")
    assert owner_head.search(line).group(1) == "abcd1234"


def test_auto_waive_refuses_anything_but_the_three_code_proven_kinds(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise ledger.LedgerError("لا")

    monkeypatch.setattr(ledger, "check_main_merge", boom)
    monkeypatch.setattr(ledger, "check_tests_only", boom)
    monkeypatch.setattr(ledger, "check_tests_main_chain", boom)
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


def _approved(tmp_path, name="e"):
    path = str(tmp_path / f"{name}.jsonl")
    cid = ledger.add_item("owner", "tool", "م", "أ", "ق", start="2026-10-21T08:00", priority="P2", path=path)
    ledger.append_event("state", cid, {"state": "approved", "by": "0501", "head": "abcd1234"}, path)
    return path, cid


def test_auto_waive_falls_through_to_the_tests_main_chain(monkeypatch, tmp_path):
    def no(*a, **k):
        raise ledger.LedgerError("لا")

    monkeypatch.setattr(ledger, "check_main_merge", no)
    monkeypatch.setattr(ledger, "check_tests_only", no)
    monkeypatch.setattr(ledger, "check_tests_main_chain", lambda *a, **k: [])
    path, cid = _approved(tmp_path)
    ledger.waive_head(cid, "deadbeef", "0101", "سبب", path=path, kind="auto")
    item = ledger.reduce_state(ledger.load_events(path))[cid]
    assert item["approved_head"] == "deadbeef"
    assert any(str(n.get("text", "")).startswith("استثناءُ رأسٍ تافه بتوقيع 0101: abcd1234→deadbeef — سلسلةُ إصلاح tests/") for n in item["notes"])


def test_the_pump_signs_only_the_code_proven_kinds(monkeypatch, tmp_path):
    for kind in ("main-merge", "tests-only", "tests-main-chain"):
        monkeypatch.setattr(ledger, {"main-merge": "check_main_merge", "tests-only": "check_tests_only",
                                     "tests-main-chain": "check_tests_main_chain"}[kind], lambda *a, **k: [])
        path, cid = _approved(tmp_path, kind)
        ledger.waive_head(cid, "deadbeef", "0101", "سبب", path=path, kind=kind)
    for kind in ("docs", "reviewed-diff", "red-fix", "types-only", "patch-id"):
        path, cid = _approved(tmp_path, "x-" + kind)
        with pytest.raises(ledger.LedgerError, match="الاستثناءُ لـ"):
            ledger.waive_head(cid, "deadbeef", "0101", "سبب", path=path, kind=kind, changed=["docs/a.md"])
    path, cid = _approved(tmp_path, "other")
    with pytest.raises(ledger.LedgerError, match="الاستثناءُ لـ"):
        ledger.waive_head(cid, "deadbeef", "0702", "سبب", path=path, kind="auto")
