from __future__ import annotations

import charter_paths_check as c


def test_paths_in_extracts_only_real_looking_paths():
    text = "اقرأ `tools/a.py` و`docs/x.md` و`ledger.py show W-1` و`https://x.y/z.md` و`handover_notes/<رقم>.md` و`C:/Users/m/q.json`"
    assert c.paths_in(text) == ["tools/a.py", "docs/x.md", "ledger.py", "C:/Users/m/q.json"]


def test_check_reports_missing_and_accepts_prefixed_locations(tmp_path):
    cards = tmp_path / "role_cards"
    (cards / "details").mkdir(parents=True)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "real.py").write_text("x", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "d.md").write_text("x", encoding="utf-8")
    (cards / "details" / "0301.md").write_text("`real.py` و`d.md` و`gone/missing.md` و`tools/real.py`", encoding="utf-8")
    assert c.check(cards, tmp_path) == [{"file": "details/0301.md", "path": "gone/missing.md"}]


def test_check_dedups_and_returns_empty_when_all_exist(tmp_path):
    cards = tmp_path / "role_cards"
    cards.mkdir()
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    (cards / "1.md").write_text("`a.md` `a.md`", encoding="utf-8")
    assert c.check(cards, tmp_path) == []


def test_bare_paths_without_backticks_are_checked():
    assert c.paths_in("انظر inputs/governance_gaps.md و tools/a.py، وhttp://a/b.md وملف.md") == ["inputs/governance_gaps.md", "tools/a.py"]


def test_retired_archive_is_not_checked(tmp_path):
    cards = tmp_path / "role_cards"
    (cards / "_retired").mkdir(parents=True)
    (cards / "_retired" / "old.md").write_text("`gone/old.md` و tools/zzz.py", encoding="utf-8")
    assert c.check(cards, tmp_path) == []
