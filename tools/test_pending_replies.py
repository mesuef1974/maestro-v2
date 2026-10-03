from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pending_replies as pr

DOHA = timezone(timedelta(hours=3))


def test_overdue_after_threshold_and_reset_by_asked(tmp_path, monkeypatch):
    p = tmp_path / "p.jsonl"
    t0 = datetime(2026, 10, 3, 10, 0, tzinfo=DOHA)
    n = pr.add("0101", "قرارُ pr_red", path=p, now=t0)
    assert pr.overdue(30, p, now=t0 + timedelta(minutes=10)) == []
    assert [r["n"] for r in pr.overdue(30, p, now=t0 + timedelta(minutes=45))] == [n]
    monkeypatch.setattr(pr, "_now", lambda: t0 + timedelta(minutes=46))
    pr.asked(n, p)
    assert pr.overdue(30, p, now=t0 + timedelta(minutes=60)) == []          # أُعيد السؤال فبدأ العدُّ من جديد
    assert pr.open_items(p)[0]["asks"] == 1


def test_done_closes_item_and_unknown_number_rejected(tmp_path):
    import pytest
    p = tmp_path / "p.jsonl"
    n = pr.add("0104", "x", path=p)
    pr.done(n, "رُدّ", p)
    assert pr.open_items(p) == []
    with pytest.raises(ValueError):
        pr.done(99, "", p)
