"""أتمتةُ مصدر الخارطة (W-20261023-014): إلحاقُ المضخّة وفحصُ التأخّر وسلسلةُ المراقب وقياسُ السقوط — بلا شبكةٍ."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import ledger_sync as ls
import roadmap_gap as rg
import roadmap_queue as rq
import watch_once as wo

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def _states():
    return {
        "W-1": {"state": "published", "approved_head": "aaaaaaaa"},
        "W-2": {"state": "pushed", "approved_head": "bbbbbbbb"},
        "W-3": {"state": "captured"},
    }


def _merged():
    return {
        "mesuef1974/maestro-v2": {"aaaaaaaa": {"number": 7, "merge": "1234567890", "at": "2026-10-22T10:00:00Z"}},
        "sh-school/shschool_mvp": {"bbbbbbbb": {"number": 7, "merge": "abcdef0123", "at": "2026-10-22T11:00:00Z"}},
    }


def test_queue_rows_follow_the_ledger_and_merged_prs_not_messages():
    rows = ls.queue_rows(_states(), _merged())
    assert {(r["card"], r["pr"], r["repo"].split("/")[1]) for r in rows} == {("W-1", 7, "maestro-v2"), ("W-2", 7, "shschool_mvp")}
    assert all(r["commit"] and r["merged_at"] for r in rows)


def test_same_pr_number_in_two_repos_is_two_queue_lines_and_repeat_is_ignored(tmp_path):
    q = tmp_path / "roadmap_queue.jsonl"
    rows = ls.queue_rows(_states(), _merged())
    assert ls.enqueue_roadmap(rows, lambda r: rq.enqueue(r, q, NOW)) and len(rq.read(q)) == 2
    assert ls.enqueue_roadmap(rows, lambda r: rq.enqueue(r, q, NOW)) == [] and len(rq.read(q)) == 2


def test_legacy_line_without_repo_still_dedups(tmp_path):
    q = tmp_path / "q.jsonl"
    assert rq.enqueue({"pr": 9, "card": "W-1"}, q, NOW)
    assert not rq.enqueue({"pr": 9, "card": "W-1", "repo": "mesuef1974/maestro-v2"}, q, NOW)


def _entry(pr, card, hours_ago):
    return {"pr": pr, "card": card, "merged_at": (NOW - timedelta(hours=hours_ago)).isoformat()}


def test_late_entries_are_only_those_past_a_day_without_a_roadmap_line():
    entries = [_entry(1, "W-1", 30), _entry(2, "W-2", 30), _entry(3, "W-3", 2), _entry(4, "W-4", 40)]
    served = "بطاقة W-1 مُدرجة؛ وطلب #4 أُغلق"
    assert [e["pr"] for e in rq.late(entries, served, NOW)] == [2]


def test_roadmap_late_alert_is_raised_and_silent_when_served():
    entries = [_entry(2, "W-2", 30)]
    alerts = wo.roadmap_late_alerts(NOW, entries, "")
    assert alerts and alerts[0]["code"] == "roadmap_late" and "#2" in alerts[0]["message"]
    assert wo.roadmap_late_alerts(NOW, entries, "بطاقة W-2") == []
    assert wo.roadmap_late_alerts(NOW, [], "") == []


def test_series_appends_one_dated_line_per_run(tmp_path):
    p = tmp_path / "watch_series.jsonl"
    a = [wo.alert("main_red", "high", "m"), wo.alert("ok", "info", "m")]
    assert wo.append_series(a, NOW, p) and wo.append_series([], NOW + timedelta(minutes=10), p)
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
    assert [r["count"] for r in rows] == [2, 0] and rows[0]["alerts"][0] == {"code": "main_red", "severity": "high"}
    assert rows[0]["ts"] < rows[1]["ts"]


def test_series_write_failure_does_not_crash_the_watcher(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert wo.append_series([], NOW, blocker / "sub" / "s.jsonl") is False


def test_gap_counts_merged_cards_absent_from_the_queue():
    ev = [
        {"ts": "2026-10-22T10:00:00+00:00", "id": "W-1", "kind": "state", "data": {"state": "published"}},
        {"ts": "2026-10-22T11:00:00+00:00", "id": "W-2", "kind": "state", "data": {"state": "merged"}},
        {"ts": "2026-09-01T11:00:00+00:00", "id": "W-9", "kind": "state", "data": {"state": "merged"}},
    ]
    states = {"W-1": {"state": "published"}, "W-2": {"state": "merged"}, "W-9": {"state": "merged"}}
    out = rg.gap(states, ev, [{"card": "W-1", "pr": 1}], NOW, days=7)
    assert (out["merged"], out["missing"], out["missing_cards"]) == (2, 1, ["W-2"])
