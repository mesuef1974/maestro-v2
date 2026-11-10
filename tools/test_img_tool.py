"""أداة الصور ومعيار «الحجم أقلّ» لبطاقات ضغط الأصول (بعد 8 محاولاتٍ لأنّ النموذج لا يشغّل Python)."""
import pytest

import img_tool
import runner

PIL = pytest.importorskip("PIL.Image")


def _png(path, size=(324, 160)):
    import os
    PIL.new("RGBA", size, (200, 30, 60, 255)).save(path)
    # ضجيجٌ يمنع ضغطًا مبالغًا فيه فيبقى للتصغير أثر
    px = PIL.frombytes("RGBA", size, os.urandom(size[0] * size[1] * 4))
    px.save(path)


def test_resize_shrinks_a_png_and_keeps_alpha(tmp_path):
    _png(tmp_path / "logo.png")
    before = (tmp_path / "logo.png").stat().st_size
    msg = img_tool.run(["resize", "logo.png", "171", "84"], root=tmp_path)
    after = PIL.open(tmp_path / "logo.png")
    assert after.size == (171, 84) and after.mode == "RGBA" and (tmp_path / "logo.png").stat().st_size < before
    assert "171×84" in msg


def test_paths_outside_the_tree_and_non_images_are_refused(tmp_path):
    (tmp_path / "a.svg").write_text("<svg/>", encoding="utf-8")
    with pytest.raises(SystemExit):
        img_tool.run(["optimize", "../x.png"], root=tmp_path)
    with pytest.raises(SystemExit):
        img_tool.run(["optimize", "a.svg"], root=tmp_path)
    _png(tmp_path / "b.png")
    with pytest.raises(SystemExit):
        img_tool.run(["resize", "b.png", "99999", "10"], root=tmp_path)


CARD = {"problem": "ضغط شعار التذييل", "scope_files": ["static/brand/sufyan-logo.png", "templates/pwa/sw_global.js"]}


def test_the_model_is_allowed_exactly_the_image_tool():
    tools = " ".join(runner.DEFAULT_CONFIG["allowed_tools"])
    assert "img_tool.py:*" in tools and "Bash(python:*)" not in tools


def test_asset_card_fails_when_no_image_was_touched_and_names_the_tool():
    miss = runner.asset_gap(CARD, {})
    assert len(miss) == 1 and "img_tool" in miss[0]


def test_asset_card_fails_when_an_image_did_not_shrink():
    assert runner.asset_gap(CARD, {"static/brand/sufyan-logo.png": (76456, 76456)})[0].startswith("المعيار «الحجم أقلّ»: صورةٌ")


def test_asset_card_passes_when_the_image_shrank():
    assert runner.asset_gap(CARD, {"static/brand/sufyan-logo.png": (76456, 25784)}) == []


def test_non_asset_cards_are_not_checked():
    assert runner.asset_gap({"problem": "إصلاح عنوان", "scope_files": ["static/brand/x.png"]}, {}) == []
    assert runner.asset_gap({"problem": "ضغط", "scope_files": ["a.py"]}, {}) == []


def test_brief_mentions_the_tool_only_for_image_scope():
    assert "img_tool" in runner.brief({"id": "W-1", **CARD}, [])
    assert "img_tool" not in runner.brief({"id": "W-1", "problem": "x", "scope_files": ["a.py"]}, [])
