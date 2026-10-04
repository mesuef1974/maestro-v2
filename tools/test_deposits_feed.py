from __future__ import annotations

import deposits_feed as df


def _data(rows):
    return {"generated_doha": "t", "rows": rows, "warnings": [], "all_shas": {}, "prev_seen": {}}


def test_render_flags_stale_deposit_without_pr():
    rows = [{"session": "0104 · الأمان", "pr": None, "commits": 1, "latest": "إصلاح", "age_h": 5.0, "new": ["abc"], "stale_no_pr": True}]
    text = df.render(_data(rows))
    assert "غيرُ مُسلَّم للمعاينة" in text and "نعم (1)" in text


def test_render_shows_pr_number_and_empty_case():
    rows = [{"session": "0405", "pr": 772, "commits": 2, "latest": "x", "age_h": 1.0, "new": [], "stale_no_pr": False}]
    assert "#772" in df.render(_data(rows))
    assert "لا إيداعَ معلَّق" in df.render(_data([]))
