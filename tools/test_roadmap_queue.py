from __future__ import annotations

from datetime import datetime, timezone

import roadmap_queue as rq

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def test_enqueue_dedup_and_read(tmp_path):
    p = tmp_path / "q.jsonl"
    assert rq.enqueue({"pr": 5, "card": "W-1", "commit": "ab", "merged_at": "2026-10-05T06:00:00Z"}, p, NOW)
    assert not rq.enqueue({"pr": 5}, p, NOW)
    rows = rq.read(p)
    assert len(rows) == 1 and rows[0]["queued_at"].startswith("2026-10-05T12:00:00")


def test_oldest_age_and_render(tmp_path):
    rows = [{"pr": 1, "merged_at": "2026-10-05T00:00:00Z"}, {"pr": 2, "merged_at": "2026-10-05T10:00:00Z"}]
    assert rq.oldest_age_hours(rows, NOW) == 12.0
    out = rq.render(rows, NOW)
    assert "#1" in out and "12.0" in out
    assert rq.render([], NOW) == "طابورُ الخارطة فارغ"


def test_missing_file_and_corrupt_line(tmp_path):
    assert rq.read(tmp_path / "none.jsonl") == []
    p = tmp_path / "q.jsonl"
    p.write_text('{"pr": 1}\nxx\n', encoding="utf-8")
    assert len(rq.read(p)) == 1
