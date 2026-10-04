from __future__ import annotations

import post_merge_checklist as pm

PR = {"number": 9, "title": "اختبار", "mergedAt": "2026-10-02T10:00:00Z", "mergeCommit": {"oid": "abcdef1234567"}}


def test_messages_carry_commit_and_card():
    m = pm.build(PR, "W-1", [])
    assert "abcdef12" in m["0104"] and "W-1" in m["0701"]


def test_sensitive_path_makes_scan_mandatory():
    hits = pm.sensitive_hits(["core/permissions.py", "docs/x.md"], ["core/permissions*.py"])
    assert hits == ["core/permissions.py"]
    assert "إلزاميّ" in pm.build(PR, None, hits)["0104"]


def test_session_and_maestro_get_publish_notice():
    m = pm.build(PR, "W-1", [], "0405 · واجهة")
    assert "0405 · واجهة" in m and "مذكّرةَ تسليمٍ" in m["0405 · واجهة"]
    assert "قرّري أرشفتَها" in m["0101"]


def test_enqueue_appends_once_and_not_for_unmerged(tmp_path, capsys):
    import json

    q = tmp_path / "q.jsonl"
    pr = {**PR, "state": "MERGED", "files": [], "headRefName": "x"}
    fetch = lambda target: (pr, "")  # noqa: E731 — حقنٌ بلا شبكة
    assert pm.main(["9", "--card", "W-1", "--enqueue"], fetch=fetch, queue_path=q) == 0
    assert pm.main(["9", "--enqueue"], fetch=fetch, queue_path=q) == 0
    rows = [json.loads(x) for x in q.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1 and rows[0]["pr"] == 9 and rows[0]["card"] == "W-1" and rows[0]["commit"] == "abcdef12"
    open_pr = {**pr, "state": "OPEN"}
    q2 = tmp_path / "q2.jsonl"
    assert pm.main(["9", "--enqueue"], fetch=lambda t: (open_pr, ""), queue_path=q2) == 1
    assert not q2.exists()
