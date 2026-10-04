from __future__ import annotations

import pr_red as r


def chk(name, conclusion, when, url="https://github.com/x/y/actions/runs/77/job/1"):
    return {"name": name, "conclusion": conclusion, "status": "COMPLETED", "completedAt": when, "detailsUrl": url}


def test_cancelled_superseded_by_newer_success_is_not_red():
    c = r.classify([chk("pytest", "CANCELLED", "2026-10-02T10:00"), chk("pytest", "SUCCESS", "2026-10-02T10:30")])
    assert c["failed"] == [] and c["cancelled"] == []


def test_real_failure_is_red_and_cancelled_alone_is_info():
    c = r.classify([chk("axe", "FAILURE", "2026-10-02T10:00"), chk("lint", "CANCELLED", "2026-10-02T10:00")])
    assert [x["name"] for x in c["failed"]] == ["axe"] and [x["name"] for x in c["cancelled"]] == ["lint"]


def test_newer_run_replaces_older_failure():
    c = r.classify([chk("pytest", "FAILURE", "2026-10-02T10:00"), chk("pytest", "SUCCESS", "2026-10-02T11:00")])
    assert c["failed"] == []


def test_report_has_check_error_card_and_session():
    pr = {"number": 9, "title": "إصلاح (W-20261002-013)", "body": "", "headRefName": "claude/x",
          "statusCheckRollup": [chk("ملخص بوابة الجودة", "FAILURE", "2026-10-02T10:00")]}
    rep = r.report_for(pr, runner=lambda rid: "x\nFAILED tests/test_a.py::t - assert 1 == 2\n", session_lookup=lambda b: "0405 · واجهة")
    assert rep["card"] == "W-20261002-013" and rep["session"] == "0405 · واجهة"
    assert "FAILED tests/test_a.py" in rep["checks"][0]["error"]
    text = r.render(rep)
    assert "ملخص بوابة الجودة" in text and "W-20261002-013" in text and "0405" in text


def test_green_pr_has_no_report():
    pr = {"number": 1, "title": "t", "body": "", "headRefName": "b", "statusCheckRollup": [chk("a", "SUCCESS", "2026-10-02T10:00")]}
    assert r.report_for(pr) is None
