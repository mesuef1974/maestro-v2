from __future__ import annotations

import validate_registry as vr


def test_self_reference_rejected():
    assert vr.self_reference_problems("0201 دُمجت في 0201")
    assert vr.self_reference_problems("x 0701 دمجت في 0701 y")
    assert not vr.self_reference_problems("0203 دُمجت في 0701")
    assert not vr.self_reference_problems("0201 دُمجت في 02015")


def test_live_titles_compared_without_tashkeel():
    """الشريطُ «الحوكمة» والسجلُّ «الحوكمةُ»: تشكيلٌ تجميليٌّ لا يُسقط التعرّف (ملاحظة 0301، الجولة 2)."""
    assert vr.bare_title("0301 · الحوكمة: حراسةُ القواعد") == "0301 · الحوكمة: حراسة القواعد"
    assert vr.bare_title("0601 · الإصدار: الدمجُ والنشر") == vr.bare_title("0601 · الإصدار: الدمج والنشر")
    assert vr.bare_title("0101 · المايسترو") != vr.bare_title("0201 · المايسترو")


def test_dead_number_as_live_session():
    tabs = {"session_policy": {"core_sessions": ["0203 · قديمة"]}, "tabs": [{"id": "a", "members": ["0801 · س"]}]}
    p = vr.dead_number_problems(tabs, {"w": "0105 · أ"}, ["0204 · ب"], {"0203.md": "# بطاقةُ دورٍ — 0203 · ج"})
    assert len(p) == 5


def test_0702_reopened_is_not_dead():
    """D-315م: 0702 أُعيد فتحها معاوناً لـ0701 فلا تُعدّ رقماً ميّتاً."""
    assert "0702" not in vr.DEAD_NUMBERS
    tabs = {"session_policy": {"core_sessions": ["0702 · معاون 0701: CI والخارطة (خفيفة)"]}, "tabs": []}
    assert vr.dead_number_problems(tabs) == []


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


def _merge_tabs(**over):
    tabs = {"session_policy": {
        "core_sessions": ["0101 · المايسترو", "0701 · الجودة"],
        "aliases": {"_note": "x", "0702": "0701", "0201": "0101", "_reused": {"0402": "0401"}},
        "charters": {"0701 · الجودة": {"merged": {"0702 · معاون": {}}}, "0101 · المايسترو": {"merged": {"0201 · البوابة": {}}}},
    }, "tabs": [{"id": "a", "members": ["0101 · المايسترو", "0701 · الجودة"]}]}
    tabs["session_policy"].update(over)
    return tabs


def test_alias_consistency_clean_for_phase2_shape():
    assert vr.alias_problems(_merge_tabs()) == []
    assert vr.alias_problems({"session_policy": {}, "tabs": []}) == []


def test_alias_key_still_standing_or_target_not_core_is_flagged():
    tabs = _merge_tabs(core_sessions=["0101 · المايسترو", "0701 · الجودة", "0702 · معاون"])
    assert any("0702 ← 0701 مستعارٌ وما زال" in p for p in vr.alias_problems(tabs))
    chain = _merge_tabs(aliases={"0702": "0701", "0201": "0101", "0204": "0201"})
    assert any("0204 ← 0201 ليس جلسةَ نواة" in p for p in vr.alias_problems(chain))


def test_merged_charter_without_alias_is_flagged():
    tabs = _merge_tabs(aliases={"0702": "0701"})
    assert vr.alias_problems(tabs) == ["«0201 · البوابة» مدمَجٌ في «0101 · المايسترو» بلا إحالة 0201 ← 0101 في aliases"]


def test_real_registry_aliases_consistent():
    import json

    tabs = json.loads((vr.ROOT / "projects/schoolos/tabs.json").read_text(encoding="utf-8"))
    assert vr.alias_problems(tabs) == []
    merged = {m[:4]: t[:4] for t, ch in tabs["session_policy"]["charters"].items() for m in ch.get("merged", {})}
    assert merged == {"0102": "0301", "0502": "0501", "0703": "0701"}  # 0702 أُعيدت جلسةً مستقلّةً (أمر المالك 2026-10-22)؛ 0201/0301 القديمان صارا جلستين عند الطلب 0106/0107 (D-455م)


def test_merged_number_reused_for_live_session_is_accepted_only_in_reused():
    # ترقيمُ 01 بالترتيب (أمر المالك 2026-10-21 14:02): 0201 جلسةٌ حيّةٌ وميثاقُ البوابة القديم مدمَجٌ في 0101
    core = ["0101 · المايسترو", "0201 · الرصد", "0701 · الجودة"]
    ok = _merge_tabs(core_sessions=core, aliases={"0702": "0701", "_reused": {"0201": "0101"}})
    assert vr.alias_problems(ok) == []
    wrong = _merge_tabs(core_sessions=core, aliases={"0702": "0701", "_reused": {"0201": "0701"}})
    assert vr.alias_problems(wrong) == ["«0201 · البوابة» مدمَجٌ في «0101 · المايسترو» بلا إحالة 0201 ← 0101 في aliases"]
    # «_reused» لا يكفي لرقمٍ ليس جلسةً قائمة: المدمَجُ الذي لم يُعَد يلزمه إحالةٌ عاديّة
    gone = _merge_tabs(aliases={"0702": "0701", "_reused": {"0201": "0101"}})
    assert len(vr.alias_problems(gone)) == 1


def test_ordinal_tab_accepts_sstt_and_keeps_ttss():
    serial = {"ordinal_tabs": {"01": "x"}, "max_title_len": 40}
    assert vr.name_problems("0201 · الرصد", "01", serial) == []
    assert vr.name_problems("0104 · الأمان", "01", serial) == []
    assert vr.name_problems("0302 · خطأ", "01", serial) != []
    assert vr.name_problems("0201 · الرصد", "01", {"max_title_len": 40}) != [], "بلا ordinal_tabs يبقى TTSS وحده"



def test_live_charter_number_as_alias_key_is_flagged():
    # W-20261028-010: رقمٌ مفتاحٌ في aliases يُعاد لميثاقٍ حيّ (حادثة 0111) يُرفض
    tabs = _merge_tabs(aliases={"0702": "0701", "0201": "0101", "0111": "0701"})
    tabs["session_policy"]["charters"]["0111 · تقييم"] = {}
    assert any("0111 ← 0701 مستعارٌ وما زال جلسةً قائمة" in p for p in vr.alias_problems(tabs))
