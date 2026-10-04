from __future__ import annotations

import json

import pytest

import session_register as sr


def test_update_adds_replaces_and_removes():
    n = {"a": "0701 · س"}
    n = sr.update(n, "b", "0409 · إدارة: امتثال الأدوار (W-020)")
    assert n["b"].startswith("0409") and "a" in n
    n = sr.update(n, "a", "0702 · ص")
    assert n["a"] == "0702 · ص"
    assert "a" not in sr.update(n, "a", None)


def test_bad_name_rejected():
    with pytest.raises(ValueError):
        sr.update({}, "x", "بلا رقم")
    with pytest.raises(ValueError):
        sr.update({}, "x", "409 · قصير")


def test_cli_roundtrip(tmp_path):
    f = tmp_path / "n.json"
    f.write_text("{}", encoding="utf-8")
    assert sr.main(["tree1", "0409 · إدارة: x", "--file", str(f)]) == 0
    assert json.loads(f.read_text(encoding="utf-8")) == {"tree1": "0409 · إدارة: x"}
    assert sr.main(["tree1", "--remove", "--file", str(f)]) == 0
    assert json.loads(f.read_text(encoding="utf-8")) == {}
    assert sr.main(["tree2", "اسم خاطئ", "--file", str(f)]) == 1
