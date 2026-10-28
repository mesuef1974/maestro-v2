from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pending_replies as pr

DOHA = timezone(timedelta(hours=3))


def test_overdue_after_threshold_and_reset_by_asked(tmp_path, monkeypatch):
    p = tmp_path / "p.jsonl"
    t0 = datetime(2026, 10, 3, 10, 0, tzinfo=DOHA)
    n = pr.add("0101", "قرارُ pr_red", path=p, now=t0)
    assert pr.overdue(30, p, now=t0 + timedelta(minutes=10)) == []
    assert [r["n"] for r in pr.overdue(30, p, now=t0 + timedelta(minutes=45))] == [n]
    monkeypatch.setattr(pr, "_now", lambda: t0 + timedelta(minutes=46))
    pr.asked(n, p)
    assert pr.overdue(30, p, now=t0 + timedelta(minutes=60)) == []          # أُعيد السؤال فبدأ العدُّ من جديد
    assert pr.open_items(p)[0]["asks"] == 1


def test_done_closes_item_and_unknown_number_rejected(tmp_path):
    import pytest
    p = tmp_path / "p.jsonl"
    n = pr.add("0104", "x", path=p)
    pr.done(n, "رُدّ", p)
    assert pr.open_items(p) == []
    with pytest.raises(ValueError):
        pr.done(99, "", p)


def test_close_reported_closes_only_items_whose_report_exists_after_registration(tmp_path):
    """W-20261026-008: كتابةُ التقرير المذكور في الإحالة تُغلق الانتظار آلياً."""
    p = tmp_path / "ledger" / "p.jsonl"
    notes = tmp_path / "handover_notes"
    notes.mkdir()
    t0 = datetime.now(DOHA) - timedelta(hours=1)
    a = pr.add("0101", "اكتبي تقريرك في handover_notes/selfcheck_0301.md", path=p, now=t0)
    b = pr.add("0101", "اكتبي تقريرك في handover_notes/other_report.md", path=p, now=t0)
    c = pr.add("0101", "قرارٌ بلا ملفّ", path=p, now=t0)
    (notes / "selfcheck_0301.md").write_text("x", encoding="utf-8")
    assert pr.close_reported(p, tmp_path) == [a]
    assert {r["n"] for r in pr.open_items(p)} == {b, c}
    assert pr.close_reported(p, tmp_path) == []  # idempotent


def test_close_reported_ignores_report_older_than_the_item(tmp_path):
    p = tmp_path / "p.jsonl"
    notes = tmp_path / "handover_notes"
    notes.mkdir()
    (notes / "old.md").write_text("x", encoding="utf-8")
    pr.add("0101", "التقرير في handover_notes/old.md", path=p, now=datetime.now(DOHA) + timedelta(hours=1))
    assert pr.close_reported(p, tmp_path) == []


def test_report_regex_accepts_windows_and_posix_paths():
    bs = chr(92)
    for text in (f"C:{bs}x{bs}handover_notes{bs}a.json", f"handover_notes{bs}r.md", "x/handover_notes/b.md"):
        assert pr.REPORT_RE.search(text), text
    assert pr.REPORT_RE.search("بلا مسار") is None


def test_strict_add_requires_card_or_pr_code(tmp_path):
    import pytest
    p = tmp_path / "p.jsonl"
    with pytest.raises(ValueError):
        pr.add("0501", "قرارٌ بلا رمز", path=p, strict=True)
    assert pr.add("0501", "ردٌّ على W-20261028-031", path=p, strict=True) == 1
    assert pr.add("0601", "دمج #1290", path=p, strict=True) == 2
    assert pr.add("0601", "قديم بلا رمز", path=p) == 3          # الإحالاتُ القديمة وغيرُ الصارمة تبقى


def test_autoclose_by_state_closes_merged_card_and_pr_with_evidence(tmp_path):
    p = tmp_path / "p.jsonl"
    a = pr.add("0501", "تسليم W-20261028-031", path=p)
    b = pr.add("0601", "دمج #1290", path=p)
    c = pr.add("0601", "W-20261028-032 و#1291", path=p)        # أحدُ الرمزين غير منتهٍ
    d = pr.add("0101", "قديم بلا رمز", path=p)
    e = pr.add("0101", "W-20261028-099", path=p)                 # بطاقةٌ مجهولة
    cards = {"W-20261028-031": "published", "W-20261028-032": "merged"}
    prs = {"1290": "MERGED (maestro-v2)", "1291": "OPEN (maestro-v2)"}
    closed = pr.close_by_state(p, card_state=cards.get, pr_state=prs.get)
    assert closed == [a, b]
    assert sorted(r["n"] for r in pr.open_items(p)) == [c, d, e]
    notes = [r["note"] for r in pr._rows(p) if r["kind"] == "done"]
    assert "W-20261028-031" in notes[0] and "published" in notes[0]
    assert "#1290" in notes[1] and "MERGED" in notes[1]


def test_autoclose_closed_pr_and_idempotent(tmp_path):
    p = tmp_path / "p.jsonl"
    n = pr.add("0601", "طلب #77", path=p)
    assert pr.close_by_state(p, card_state=lambda _: None, pr_state={"77": "CLOSED (x)"}.get) == [n]
    assert pr.close_by_state(p, card_state=lambda _: None, pr_state={"77": "CLOSED (x)"}.get) == []
