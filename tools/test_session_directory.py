"""اختباراتُ دليل عناوين الجلسات بعد المرحلة 2 من الدمج وترقيم المجموعة 01 (أمرا المالك 2026-10-21):
  cd tools && python -m pytest test_session_directory.py

لا تقرأ القرصَ الحقيقيّ: ملفّاتُ الجلسات وtabs.json مؤقّتةٌ (tmp_path) وتُحقن بـmonkeypatch.
"""
from __future__ import annotations

import json

import pytest

import session_alias as sa
import session_directory as sd

PLATFORM = r"D:\shschool_mvp\.claude\worktrees\tree-1"
LIGHT = r"C:\Users\mesue\delivery_manager_work"
ALIASES = {"_note": "x", "0702": "0701", "0102": "0301", "0103": "0301", "0204": "0202", "0202": "0101",
           "_reused": {"0402": "0401", "0201": "0101", "0301": "0101"}}
TREES = {"_note": "x", "C:/Users/mesue/delivery_manager_work": ["0101"]}


def _session(base, name, sid, title, tree, archived=False, at=1, cwd_only=False):
    d = base / "a" / "b"
    d.mkdir(parents=True, exist_ok=True)
    data = {"sessionId": sid, "title": title, "isArchived": archived, "lastActivityAt": at}
    # الجلسةُ بلا شجرة (الخفيفة) يكتبها التطبيق worktreePath: null ومجلّدُها في cwd
    data.update({"worktreePath": None, "cwd": tree} if cwd_only else {"worktreePath": tree})
    (d / f"local_{name}.json").write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def world(tmp_path, monkeypatch):
    base = tmp_path / "sessions"
    tabs = tmp_path / "tabs.json"
    tabs.write_text(json.dumps({"session_policy": {"aliases": ALIASES, "directory_trees": TREES}, "tabs": []}),
                    encoding="utf-8")
    monkeypatch.setattr(sd, "BASE", base)
    monkeypatch.setattr(sa, "TABS", tabs)
    _session(base, "1", "local_0701", "0701 · الجودة", PLATFORM)
    _session(base, "2", "local_0702", "0702 · معاون", PLATFORM, at=99)
    _session(base, "3", "local_0301", "0301 · الحوكمة", PLATFORM)
    _session(base, "4", "local_0102", "0102 · التقييم", PLATFORM)
    _session(base, "5", "local_0101", "0101 · المايسترو: التوجيه والاعتماد", LIGHT, cwd_only=True)
    _session(base, "6", "local_0201", "0201 · المايسترو: الرصد والتقييم", PLATFORM)
    _session(base, "7", "local_0703", "0703 · معاون 2 لـ0701", LIGHT, cwd_only=True, at=500)
    _session(base, "8", "local_misc", "0999 · جلسةٌ أخرى في المجلّد", LIGHT, cwd_only=True)
    return base


def test_merged_numbers_never_appear_even_when_their_session_is_live(world):
    e = sd.entries()
    assert set(e) == {"0101", "0201", "0301", "0701"}
    assert "0702" not in e and "0102" not in e


def test_cli_resolves_merged_number_to_receiver_id(world, capsys):
    assert sd.main(["0702"]) == 0
    out = capsys.readouterr()
    assert out.out.strip() == "local_0701"
    assert "0702 مدمَجةٌ في 0701" in out.err
    assert sd.main(["0102"]) == 0
    assert capsys.readouterr().out.strip() == "local_0301"
    assert sd.main(["0103"]) == 0  # الرقمُ القديمُ للحوكمة
    assert capsys.readouterr().out.strip() == "local_0301"


def test_light_0101_is_found_by_its_folder_and_heavy_is_0201(world, capsys):
    assert sd.main(["0101"]) == 0
    assert capsys.readouterr().out.strip() == "local_0101"
    assert sd.main(["0201"]) == 0  # 0201 جلسةٌ حيّة (الثقيلة) لا اسمٌ مستعار
    out = capsys.readouterr()
    assert out.out.strip() == "local_0201" and out.err == ""


def test_other_sessions_in_the_light_folder_are_not_admitted(world, capsys):
    e = sd.entries()
    assert "0703" not in e and "0999" not in e
    assert sd.main(["0703"]) == 1
    assert "لا جلسةَ حيّةً بالرقم 0703" in capsys.readouterr().err


def test_bound_number_is_taken_from_its_folder_only(tmp_path):
    # جلسةٌ بالرقم 0101 في شجرة منصّةٍ (ولو أحدث نشاطاً) لا تغلب الخفيفة المربوطةَ بمجلّدها
    base = tmp_path / "s"
    trees = sa.directory_trees({"session_policy": {"directory_trees": TREES}})
    _session(base, "1", "light", "0101 · المايسترو: التوجيه والاعتماد", LIGHT, cwd_only=True, at=1)
    _session(base, "2", "impostor", "0101 · المايسترو", PLATFORM, at=999)
    assert sd.entries(base, aliases={}, trees=trees)["0101"]["id"] == "light"


def test_binding_survives_renaming_because_it_uses_number_and_folder(tmp_path):
    base = tmp_path / "s"
    trees = sa.directory_trees({"session_policy": {"directory_trees": TREES}})
    _session(base, "1", "light", "0101 · اسمٌ جديدٌ بعد إعادة التسمية", LIGHT.lower() + "\\", cwd_only=True)
    assert sd.entries(base, aliases={}, trees=trees)["0101"]["id"] == "light"


def test_without_binding_the_light_folder_is_invisible(tmp_path):
    base = tmp_path / "s"
    _session(base, "1", "light", "0101 · المايسترو", LIGHT, cwd_only=True)
    assert sd.entries(base, aliases={}, trees={}) == {}


def test_alias_chain_resolves_to_final_receiver(world, capsys):
    assert sd.main(["0204"]) == 0  # 0204 ← 0202 ← 0101
    out = capsys.readouterr()
    assert out.out.strip() == "local_0101" and "0204 مدمَجةٌ في 0101" in out.err


def test_current_number_prints_id_without_note(world, capsys):
    assert sd.main(["0701"]) == 0
    out = capsys.readouterr()
    assert out.out.strip() == "local_0701" and out.err == ""


def test_json_mode_lists_only_current_numbers(world, capsys):
    assert sd.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"0101": "local_0101", "0201": "local_0201",
                                                   "0301": "local_0301", "0701": "local_0701"}


def test_archived_skipped_and_latest_activity_wins(tmp_path):
    base = tmp_path / "s"
    _session(base, "1", "old", "0601 · الإصدار", PLATFORM, at=5)
    _session(base, "2", "new", "0601 · الإصدار", PLATFORM, at=9)
    _session(base, "3", "gone", "0601 · الإصدار", PLATFORM, archived=True, at=50)
    _session(base, "4", "x", "بلا رقم", PLATFORM)
    assert sd.entries(base, aliases={}, trees={}) == {"0601": {"id": "new", "title": "0601 · الإصدار", "at": 9}}


def test_injected_aliases_override_tabs_and_empty_means_none_hidden(tmp_path):
    base = tmp_path / "s"
    _session(base, "1", "a", "0702 · معاون", PLATFORM)
    assert set(sd.entries(base, aliases={}, trees={})) == {"0702"}
    assert sd.entries(base, aliases={"0702": "0701"}, trees={}) == {}


def test_missing_tabs_file_means_no_aliases_and_no_bound_folders(tmp_path, monkeypatch):
    base = tmp_path / "s"
    _session(base, "1", "a", "0702 · معاون", PLATFORM)
    _session(base, "2", "b", "0101 · المايسترو", LIGHT, cwd_only=True)
    monkeypatch.setattr(sd, "BASE", base)
    monkeypatch.setattr(sa, "TABS", tmp_path / "missing.json")
    assert set(sd.entries()) == {"0702"}
