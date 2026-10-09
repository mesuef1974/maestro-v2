from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import digest

DOHA = timezone(timedelta(hours=3))
NOW = datetime(2026, 10, 9, 20, 0, tzinfo=DOHA)


def ev(minutes_ago, item, kind, data):
    ts = (NOW - timedelta(minutes=minutes_ago)).isoformat(timespec="minutes")
    return {"ts": ts, "id": item, "kind": kind, "data": data}


def write(path, events):
    path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n", encoding="utf-8")


def sample(tmp_path):
    p = tmp_path / "events.jsonl"
    write(p, [
        ev(500, "W-1", "created", {"problem": "قديمة", "start": "2026-10-01T09:00+03:00"}),
        ev(500, "W-1", "state", {"state": "routed"}),
        ev(120, "W-2", "created", {"problem": "بلا حامل", "start": "2026-10-09T09:00+03:00"}),
        ev(120, "W-2", "state", {"state": "routed", "by": "0201"}),
        ev(100, "W-3", "created", {"problem": "بحامل", "start": "2026-10-09T09:00+03:00"}),
        ev(100, "W-3", "state", {"state": "routed", "held_by": "0701", "by": "0201"}),
        ev(10, "W-4", "created", {"problem": "مستقبلية", "start": "2026-10-20T09:00+03:00"}),
        ev(10, "W-4", "state", {"state": "routed"}),
        ev(5, "W-3", "note", {"by": "0701", "text": "إقرار"}),
    ])
    return p


def run(tmp_path, ev_path, now=NOW, viol=None):
    return digest.run_once(now, tmp_path / "out", ev_path, viol or tmp_path / "none.md")


def test_never_modifies_the_ledger(tmp_path):
    p = sample(tmp_path)
    before = p.read_bytes()
    run(tmp_path, p)
    assert p.read_bytes() == before


def test_sections_and_future_cards_excluded(tmp_path):
    p = sample(tmp_path)
    run(tmp_path, p)
    text = (tmp_path / "out" / "latest.md").read_text(encoding="utf-8")
    assert "W-2: captured ← routed (بواسطة 0201)" in text
    assert "W-3: — ← 0701" in text
    no_holder = text.split("## 3)")[1].split("## 4)")[0]
    assert "W-1" in no_holder and "W-2" in no_holder and "W-3" not in no_holder
    stale = text.split("## 4)")[1].split("## 5)")[0]
    assert "W-2" in stale and "W-4" not in stale and "استُبعدت 1" in stale
    assert "W-3" not in stale  # الملاحظةُ إقرارٌ من الحامل


def test_idempotent_second_run_rewrites_nothing(tmp_path):
    p = sample(tmp_path)
    assert run(tmp_path, p) is True
    assert run(tmp_path, p) is False
    assert run(tmp_path, p, NOW + timedelta(minutes=1)) is False  # فارقُ دقيقةٍ لا يغيّر الملفّ


def test_violations_baseline_then_new_row(tmp_path):
    p = sample(tmp_path)
    v = tmp_path / "v.md"
    v.write_text("| 2026-10-01 | 0101 | قاعدة | وصف قديم | إجراء | مفتوحة |\n", encoding="utf-8")
    run(tmp_path, p, NOW, v)
    assert "(0)" in (tmp_path / "out" / "latest.md").read_text(encoding="utf-8").split("## 5)")[1]
    v.write_text(v.read_text(encoding="utf-8") + "| 2026-10-09 | 0405 | قاعدة | مخالفة جديدة | إجراء | مفتوحة |\n", encoding="utf-8")
    run(tmp_path, p, NOW + timedelta(minutes=15), v)
    section = (tmp_path / "out" / "latest.md").read_text(encoding="utf-8").split("## 5)")[1]
    assert "(1)" in section and "مخالفة جديدة" in section and "وصف قديم" not in section


def test_corrupt_line_and_missing_file_do_not_crash(tmp_path):
    p = tmp_path / "events.jsonl"
    p.write_text('xx\n{"ts":"2026-10-09T19:00+03:00","id":"W-9","kind":"created","data":{}}\n', encoding="utf-8")
    assert run(tmp_path, p) is True
    assert digest.read_events(tmp_path / "missing.jsonl") == []


def test_list_cap_keeps_the_oldest(tmp_path):
    p = tmp_path / "events.jsonl"
    rows = []
    for i in range(20):
        rows += [ev(600 - i, f"W-{i:02d}", "created", {"start": "2026-10-01T09:00+03:00"}),
                 ev(600 - i, f"W-{i:02d}", "state", {"state": "routed"})]
    write(p, rows)
    run(tmp_path, p)
    text = (tmp_path / "out" / "latest.md").read_text(encoding="utf-8")
    assert text.count("W-00") >= 1 and "و5 أخرى" in text
