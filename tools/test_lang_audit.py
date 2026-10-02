from __future__ import annotations

import lang_audit as la


def test_detects_english_description():
    assert la.latin_dominant("Show last 10 lines of decisions ledger", 0.6)


def test_arabic_with_latin_token_is_clean():
    assert not la.latin_dominant("تشغيل pytest على اختبارات النسخ الاحتياطيّ", 0.6)


def test_short_text_is_ignored():
    assert not la.latin_dominant("git log", 0.6)


def test_identifiers_and_paths_do_not_count():
    assert not la.latin_dominant("P0 جديدة: ثغرة path-injection في docs_viewer (#746)", 0.6)
