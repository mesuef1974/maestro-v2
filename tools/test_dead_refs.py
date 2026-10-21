from __future__ import annotations

import dead_refs as dr


def test_scan_classifies_and_flags_referral():
    text = "جلسة 0203 تعمل\nكانت 0801 ثمّ دُمجت\nأخبر 0104\nلا شيء 12345 ولا 2026"
    hits = dr.scan_text(text, "f.md")
    assert [(h["number"], h["kind"], h["referral"]) for h in hits] == [("0203", "ميّت", False), ("0801", "ميّت", True), ("0104", "مُعاد", False)]


def test_sort_puts_active_dead_first():
    hits = dr.scan_text("أخبر 0104\nكانت 0203\nجلسة 0801", "f.md")
    assert [h["number"] for h in dr.sort_hits(hits)] == ["0801", "0104", "0203"]


def test_collect_reads_files_without_writing(tmp_path):
    (tmp_path / "role_cards").mkdir()
    (tmp_path / "role_cards" / "0101.md").write_text("ارجع إلى 0204", encoding="utf-8")
    mem = tmp_path / "MEMORY.md"
    mem.write_text("- 0201 بلاغات", encoding="utf-8")
    hits = dr.collect(mem, tmp_path)
    assert {h["number"] for h in hits} == {"0204", "0201"}


MERGED = {"0702": "0701", "0102": "0301", "0103": "0301", "0204": "0101"}


def test_merged_numbers_get_their_own_kind_and_dead_wins():
    text = "أخبر 0702 بالفحص\nميثاقُ 0102 مدمَجٌ في الحوكمة\nارجع إلى 0204\nأخبر 0104"
    hits = dr.scan_text(text, "f.md", MERGED)
    assert [(h["number"], h["kind"], h["referral"]) for h in hits] == [
        ("0702", "مدمَج", False), ("0102", "مدمَج", True), ("0204", "ميّت", False), ("0104", "مُعاد", False)]
    assert [h["number"] for h in dr.sort_hits(hits)] == ["0204", "0702", "0104", "0102"]


def test_merged_section_text_counts_as_referral_until_next_section():
    text = "## مدمَج من 0201 · البوابة\n### من كانت\nتسلّم إلى 0301\n## قواعد\nأخبر 0301"
    hits = dr.scan_text(text, "f.md", MERGED)
    assert [(h["line"], h["number"], h["referral"]) for h in hits] == [(1, "0201", True), (3, "0301", True), (5, "0301", False)]
    assert [h["kind"] for h in hits] == ["مُعاد", "مُعاد", "مُعاد"]


def test_0201_and_0301_are_reused_again_and_0702_is_silent_without_aliases():
    # ترقيمُ 01 بالترتيب (أمر المالك 2026-10-21 14:02): 0201 و0301 جلستان حيّتان وميثاقاهما القديمان مدمَجان في 0101
    hits = dr.scan_text("أخبر 0201 و0702\nأخبر 0301", "f.md", {})
    assert [(h["number"], h["kind"]) for h in hits] == [("0201", "مُعاد"), ("0301", "مُعاد")]

