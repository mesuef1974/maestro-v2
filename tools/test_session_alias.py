from __future__ import annotations

import session_alias as sa

TABS = {
    "session_policy": {
        "core_sessions": ["0104 · الأمان", "0201 · البوابة", "0701 · الجودة", "0401 · جدول"],
        "aliases": {"_note": "x", "0105": "0104", "0203": "0701", "0204": "0201", "_reused": {"0402": "0401"}},
    },
    "tabs": [{"members": ["0402 · جدول آخر"]}],
}


def test_dead_number_resolves_to_current_title():
    assert sa.resolve("0105", TABS) == "0104 · الأمان"
    assert sa.resolve("0203 · الرصد", TABS) == "0701 · الجودة"


def test_current_number_unchanged():
    assert sa.resolve("0201", TABS) == "0201 · البوابة"


def test_reused_number_needs_legacy_flag():
    assert sa.resolve("0402", TABS) == "0402 · جدول آخر"
    assert sa.resolve("0402", TABS, legacy=True) == "0401 · جدول"


def test_unknown_and_note_key():
    assert sa.resolve("9999", TABS) is None
    assert sa.resolve("_note", TABS) is None


def test_real_registry_has_aliases():
    assert sa.resolve("0801") is not None and sa.resolve("0801").startswith("0701")
