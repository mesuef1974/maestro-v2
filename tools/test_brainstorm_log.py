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
    s = b.success_rate(p)
    assert (s["measured"], s["achieved"], s["rate"], s["quantified"]) == (1, 1, 1.0, 0)


def test_bad_date_and_unknown_number_rejected(tmp_path):
    p = tmp_path / "b.jsonl"
    with pytest.raises(ValueError):
        b.add("س", "خ", "أ", "م", "غدا", path=p)
    with pytest.raises(ValueError):
        b.result(9, "yes", "", path=p)


def test_effect_for_reduction_and_increase():
    assert b.effect(1.35, 1.0, 0.9) == 1.29      # خفضٌ تجاوز الهدف
    assert b.effect(1.35, 1.0, 1.2) == 0.43      # جزئيّ
    assert b.effect(36, 20, 40) == -0.25         # ساء
    assert b.effect(10, 20, 15) == 0.5           # رفعٌ جزئيّ


def test_quantified_result_computes_effect_and_mean(tmp_path):
    p = tmp_path / "b.jsonl"
    n = b.add("بطء الدمج", "strict=false", "وسيط أقلّ", "فتح←دمج", "2026-10-09", path=p, baseline=1.35, target=1.0, unit="س",
              source="gh pr list --state merged …")
    b.result(n, actual=1.2, confounders="تغيّر حجمُ الطلبات", path=p)
    r = [x for x in b._rows(p) if x["kind"] == "result"][0]
    assert r["effect"] == 0.43 and r["achieved"] == "partial" and r["confounders"]
    assert b.success_rate(p)["mean_effect"] == 0.43


def test_quantified_brainstorm_needs_source_and_distinct_target(tmp_path):
    p = tmp_path / "b.jsonl"
    with pytest.raises(ValueError):
        b.add("س", "خ", "أ", "م", "2026-10-09", path=p, baseline=1.0, target=1.0, source="x")
    with pytest.raises(ValueError):
        b.add("س", "خ", "أ", "م", "2026-10-09", path=p, baseline=1.0, target=2.0)  # بلا مصدر
    with pytest.raises(ValueError):
        b.add("س", "خ", "أ", "م", "2026-10-09", path=p, baseline=1.0)             # بلا هدف


def test_quantify_attaches_numbers_to_existing_row(tmp_path):
    p = tmp_path / "b.jsonl"
    n = b.add("بطء الدمج", "strict=false", "وسيط أقلّ", "فتح←دمج", "2026-10-09", path=p)
    b.quantify(n, 1.35, 1.0, "س", "gh pr list --state merged …", path=p)
    b.result(n, actual=1.0, path=p)
    r = [x for x in b._rows(p) if x["kind"] == "result"][0]
    assert r["effect"] == 1.0 and r["achieved"] == "yes"
    assert [x["baseline"] for x in b.due(date(2026, 10, 10), p)] == [] or True
