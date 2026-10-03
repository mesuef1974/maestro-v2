from __future__ import annotations

from datetime import date

import brainstorm_log as b
import pytest


def test_add_due_result_and_rate(tmp_path):
    p = tmp_path / "b.jsonl"
    n1 = b.add("بطء الدمج", "strict=false", "وسيط ≤ 1 س", "فتح←دمج", "2026-10-09", path=p)
    n2 = b.add("خادمان", "خادمٌ واحد", "ذاكرة", "free_gb", "2026-10-20", path=p)
    assert (n1, n2) == (1, 2)
    assert [r["n"] for r in b.due(date(2026, 10, 10), p)] == [1]
    b.result(1, "yes", "الوسيط 0.9", path=p)
    assert b.due(date(2026, 10, 10), p) == []
    assert b.success_rate(p) == {"measured": 1, "achieved": 1, "rate": 1.0}


def test_bad_date_and_unknown_number_rejected(tmp_path):
    p = tmp_path / "b.jsonl"
    with pytest.raises(ValueError):
        b.add("س", "خ", "أ", "م", "غدا", path=p)
    with pytest.raises(ValueError):
        b.result(9, "yes", "", path=p)
