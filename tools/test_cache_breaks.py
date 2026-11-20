"""اختبارات مقياس انكسار ذاكرة التخزين المؤقت."""
from __future__ import annotations

import json
import os
import time

import cache_breaks as cb


def _line(ts, cr, cc, inp=2, model="m1", rid=None, side=False, h1=True):
    cache = {"ephemeral_1h_input_tokens": cc if h1 else 0, "ephemeral_5m_input_tokens": 0 if h1 else cc}
    return json.dumps({
        "type": "assistant", "timestamp": ts, "isSidechain": side, "requestId": rid or f"r{ts}{cr}{cc}",
        "message": {"model": model, "usage": {
            "input_tokens": inp, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cc,
            "cache_creation": cache}},
    })


T0 = "2026-11-20T10:00:00Z"
T1 = "2026-11-20T10:01:00Z"
T_LATE = "2026-11-20T11:30:00Z"


def test_parse_skips_sidechain_and_duplicates():
    lines = [_line(T0, 0, 30000, rid="a"), _line(T0, 0, 30000, rid="a"), _line(T1, 30000, 500, side=True)]
    reqs = cb.parse_lines(lines)
    assert len(reqs) == 1 and reqs[0].prefix == 30002


def test_no_break_when_prefix_read():
    reqs = cb.parse_lines([_line(T0, 0, 30000), _line(T1, 30000, 800)])
    assert cb.find_breaks(reqs) == []


def test_small_prefix_ignored():
    reqs = cb.parse_lines([_line(T0, 0, 5000), _line(T1, 0, 5200)])
    assert cb.find_breaks(reqs) == []


def test_prefix_change_break_and_weight():
    reqs = cb.parse_lines([_line(T0, 10000, 30000), _line(T1, 4000, 37000)])
    (b,) = cb.find_breaks(reqs)
    assert b.cause == "بادئة"
    assert b.wasted == 40002 - 4000
    assert abs(b.weighted - b.wasted * 1.9) < 1e-6


def test_timeout_cause_respects_ttl():
    reqs_1h = cb.parse_lines([_line(T0, 0, 30000), _line(T_LATE, 0, 31000)])
    assert cb.find_breaks(reqs_1h)[0].cause == "مهلة"
    # عشر دقائق: مهلة لذاكرة 5m، وبادئة لذاكرة 1h
    t10 = "2026-11-20T10:10:00Z"
    assert cb.find_breaks(cb.parse_lines([_line(T0, 0, 30000, h1=False), _line(t10, 0, 31000, h1=False)]))[0].cause == "مهلة"
    assert cb.find_breaks(cb.parse_lines([_line(T0, 0, 30000), _line(t10, 0, 31000)]))[0].cause == "بادئة"


def test_model_and_compact_causes():
    reqs = cb.parse_lines([_line(T0, 0, 30000), _line(T1, 0, 31000, model="m2")])
    assert cb.find_breaks(reqs)[0].cause == "نموذج"
    lines = [_line(T0, 0, 30000), json.dumps({"type": "system", "subtype": "compact_boundary"}), _line(T1, 0, 9000)]
    assert cb.find_breaks(cb.parse_lines(lines), min_prefix=20000)[0].cause == "ضغط"


def test_scan_and_summary(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    later = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 30))
    (proj / "s1.jsonl").write_text("\n".join([_line(now, 0, 30000), _line(later, 1000, 30000)]), encoding="utf-8")
    sub = proj / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "a.jsonl").write_text(_line(now, 0, 99999), encoding="utf-8")
    os.utime(proj / "s1.jsonl")
    sessions = cb.scan(1, 20000, root=tmp_path)
    assert len(sessions) == 1
    r = cb.summarize(sessions, 1)
    assert r["breaks"] == 1 and r["by_cause"]["بادئة"]["n"] == 1
    assert r["wasted"] == 29002
    assert "انكسارات 1" in cb.render(r, sessions, 5)
