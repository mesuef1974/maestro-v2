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


def test_real_registry_resolves_phase2_merged_numbers():
    # المرحلة 2 (أمر المالك 2026-10-21): المدمَجةُ أسماءٌ مستعارةٌ لمستقبِلاتها؛ ثمّ ترقيمُ 01 بالترتيب (14:02):
    # 0103 ← 0301 و0102 ← 0301، و0201 و0301 جلستان حيّتان فخرجتا من الإحالة إلى «_reused»
    expect = {"0102": "0301", "0103": "0301", "0204": "0101", "0202": "0101"}
    for old, new in expect.items():
        assert sa.resolve(old).startswith(new), old
    m = sa.number_map()
    assert {k: m[k] for k in expect} == expect
    reused = sa._load(None)["session_policy"]["aliases"]["_reused"]
    assert "0702" not in reused and "0702" not in m and "0201" not in m and "0301" not in m
    assert sa.resolve("0201").startswith("0201 · المايسترو") and sa.resolve("0301").startswith("0301 · الحوكمة")
    assert sa.resolve("0201", legacy=True).startswith("0106") and sa.resolve("0301", legacy=True).startswith("0107")  # D-455م


def test_number_map_skips_meta_keys_and_tolerates_missing_file(tmp_path, monkeypatch):
    assert sa.number_map(TABS) == {"0105": "0104", "0203": "0701", "0204": "0201"}
    monkeypatch.setattr(sa, "TABS", tmp_path / "none.json")
    assert sa.number_map() == {}
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(sa, "TABS", tmp_path / "bad.json")
    assert sa.number_map() == {}


def test_directory_trees_normalise_paths_and_skip_meta(tmp_path, monkeypatch):
    tabs = {"session_policy": {"directory_trees": {"_note": "x", "C:\\Users\\Me\\Work\\": ["0101", "bad"]}}}
    assert sa.directory_trees(tabs) == {"c:/users/me/work": {"0101"}}
    monkeypatch.setattr(sa, "TABS", tmp_path / "none.json")
    assert sa.directory_trees() == {}


def test_real_registry_binds_light_0101_to_its_folder_only():
    assert sa.directory_trees() == {"c:/users/mesue/delivery_manager_work": {"0101"},
                                    "c:/users/mesue/delivery_manager_work/.claude/worktrees/*": {"0109", "0110"}}


def test_canonical_follows_chain_and_stops_on_cycle():
    chain = {"0204": "0201", "0201": "0101"}
    assert sa.canonical("0204", chain) == "0101"
    assert sa.canonical("0501", chain) == "0501"
    assert sa.canonical("0204", None) == "0204"
    assert sa.canonical("0001", {"0001": "0002", "0002": "0001"}) == "0001"
