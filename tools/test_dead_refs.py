from __future__ import annotations

import dead_refs as dr


def test_scan_classifies_and_flags_referral():
    text = "جلسة 0203 تعمل\nكانت 0801 ثمّ دُمجت\nأخبر 0104\nلا شيء 12345 ولا 2026"
    hits = dr.scan_text(text, "f.md")
    assert [(h["number"], h["kind"], h["referral"]) for h in hits] == [("0203", "ميّت", False), ("0801", "ميّت", True), ("0104", "مُعاد", False)]


def test_sort_puts_active_dead_first():
    hits = dr.scan_text("أخبر 0104\nكانت 0203\nجلسة 0702", "f.md")
    assert [h["number"] for h in dr.sort_hits(hits)] == ["0702", "0104", "0203"]


def test_collect_reads_files_without_writing(tmp_path):
    (tmp_path / "role_cards").mkdir()
    (tmp_path / "role_cards" / "0101.md").write_text("ارجع إلى 0204", encoding="utf-8")
    mem = tmp_path / "MEMORY.md"
    mem.write_text("- 0201 بلاغات", encoding="utf-8")
    hits = dr.collect(mem, tmp_path)
    assert {h["number"] for h in hits} == {"0204", "0201"}
