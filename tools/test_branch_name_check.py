import branch_name_check as b

CARDS = {"W-20261014-008": "in_progress", "W-20261001-001": "published", "W-20261002-002": "merged"}


def test_live_ended_unknown_none_exempt():
    assert b.classify("claude/W-20261014-008-git-names", CARDS) == "live"
    assert b.classify("claude/W-20261001-001", CARDS) == "ended"
    assert b.classify("claude/W-20261002-002", CARDS) == "live"
    assert b.classify("claude/W-20269999-999-x", CARDS) == "unknown"
    assert b.classify("claude/schedule-fix", CARDS) == "none"
    assert b.classify("main", CARDS) == "exempt"
    assert b.classify("backup-2026-09-13-before-pii-fix", CARDS) == "exempt"


def test_conforms_pattern():
    assert b.conforms("claude/W-20261014-008")
    assert b.conforms("claude/W-20261014-008-abc")
    assert not b.conforms("claude/0417-w001-block-tests")
    assert not b.conforms("W-20261014-008")


def test_report_counts_and_violations():
    rep = b.report(["main", "claude/W-20261014-008", "claude/old-thing", "claude/W-20261001-001"], CARDS)
    assert rep["counts"]["live"] == 1 and rep["counts"]["none"] == 1 and rep["counts"]["exempt"] == 1
    assert rep["violations"] == ["claude/old-thing"]
    assert rep["live_pct"] == 33.3


def test_warning_nonblocking_and_suggestion():
    assert b.warning_for("claude/W-20261014-008-x", "W-20261014-008", CARDS) is None
    w = b.warning_for("claude/old-thing", "W-20261014-008", CARDS)
    assert "claude/W-20261014-008-old-thing" in w and "2026-10-28" in w
    assert b.warning_for("main", None, CARDS) is None


def test_suggest():
    assert b.suggest("W-20261014-008", "git names!") == "claude/W-20261014-008-git-names"
