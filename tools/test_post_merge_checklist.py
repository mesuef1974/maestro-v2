from __future__ import annotations

import post_merge_checklist as pm

PR = {"number": 9, "title": "اختبار", "mergedAt": "2026-10-02T10:00:00Z", "mergeCommit": {"oid": "abcdef1234567"}}


def test_messages_carry_commit_and_card():
    m = pm.build(PR, "W-1", [])
    assert "abcdef12" in m["0105"] and "W-1" in m["0702"]


def test_sensitive_path_makes_scan_mandatory():
    hits = pm.sensitive_hits(["core/permissions.py", "docs/x.md"], ["core/permissions*.py"])
    assert hits == ["core/permissions.py"]
    assert "إلزاميّ" in pm.build(PR, None, hits)["0105"]


def test_session_and_maestro_get_publish_notice():
    m = pm.build(PR, "W-1", [], "0408 · واجهة")
    assert "0408 · واجهة" in m and "مذكّرةَ تسليمٍ" in m["0408 · واجهة"]
    assert "قرّري أرشفتَها" in m["0101"]
