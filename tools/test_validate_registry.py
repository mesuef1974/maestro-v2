from __future__ import annotations

import validate_registry as vr


def test_self_reference_rejected():
    assert vr.self_reference_problems("0201 دُمجت في 0201")
    assert vr.self_reference_problems("x 0701 دمجت في 0701 y")
    assert not vr.self_reference_problems("0203 دُمجت في 0701")
    assert not vr.self_reference_problems("0201 دُمجت في 02015")


def test_dead_number_as_live_session():
    tabs = {"session_policy": {"core_sessions": ["0203 · قديمة"]}, "tabs": [{"id": "a", "members": ["0801 · س"]}]}
    p = vr.dead_number_problems(tabs, {"w": "0105 · أ"}, ["0204 · ب"], {"0702.md": "# بطاقةُ دورٍ — 0702 · ج"})
    assert len(p) == 5


def test_reused_or_merged_not_flagged():
    tabs = {"session_policy": {"core_sessions": ["0104 · الأمان"]}, "tabs": []}
    cards = {"0203.md": "# بطاقةُ دورٍ — 0203 (دُمجت)"}
    assert vr.dead_number_problems(tabs, {}, [], cards) == []


def test_changelog_after_cutoff_needs_version_and_decision():
    ok = "- **v2.30 — 2026-10-05 — D-210م:** نص"
    bad = "- 2026-10-06 نصٌّ بلا رقم"
    old = "- 2026-10-04 (بأمر المالك): نص"
    row_bad = "| v2.31 | 10-07 ~10:00 | D-211 | تغيّر | الكلّ | x |"
    assert vr.changelog_problems(ok) == []
    assert len(vr.changelog_problems(bad)) == 2
    assert vr.changelog_problems(old) == []
    assert len(vr.changelog_problems(row_bad)) == 1
