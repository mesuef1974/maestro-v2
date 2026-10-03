from __future__ import annotations

import memory_stale as ms


def mk(tmp_path):
    root = tmp_path / "mem"
    root.mkdir()
    (root / "MEMORY.md").write_text("# فهرس\n- [a](a.md) — x\n", encoding="utf-8")
    (root / "a.md").write_text("يذكر `tools/ok.py` و`templates/base.html`", encoding="utf-8")
    (root / "b.md").write_text("بلا مسار", encoding="utf-8")
    return root


def test_missing_path_and_unindexed_are_counted(tmp_path):
    root = mk(tmp_path)
    m = ms.measure(root, existing={"tools/ok.py"})
    assert m["memories_naming_missing_path"] == 1 and m["missing_paths"] == 1
    assert m["unindexed"] == 1 and m["_unindexed"] == ["b.md"]


def test_existing_path_is_not_stale(tmp_path):
    root = mk(tmp_path)
    m = ms.measure(root, existing={"tools/ok.py", "templates/base.html"})
    assert m["memories_naming_missing_path"] == 0


def test_index_cap_flag(tmp_path):
    root = mk(tmp_path)
    (root / "MEMORY.md").write_text("\n".join(f"- [x{i}](x{i}.md)" for i in range(130)), encoding="utf-8")
    assert ms.measure(root, existing=set())["index_over_cap"] is True
    (root / "MEMORY.md").write_text("- [a](a.md)\n", encoding="utf-8")
    assert ms.measure(root, existing=set())["index_over_cap"] is False


def test_archive_dir_excluded_and_marked_paths_accepted(tmp_path):
    root = mk(tmp_path)
    (root / "archive").mkdir()
    (root / "archive" / "old.md").write_text("يذكر `tools/gone.py`", encoding="utf-8")
    (root / "c.md").write_text("`tools/was.py` (حُذف في D-60م) و`tools/pack.py` (حزمة قديمة) و`tools/real_missing.py`", encoding="utf-8")
    m = ms.measure(root, existing={"tools/ok.py", "templates/base.html"})
    assert m["_bad"] == {"c.md": ["tools/real_missing.py"]}
