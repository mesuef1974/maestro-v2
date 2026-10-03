from __future__ import annotations

import watch_once as w


def test_below_warn_is_quiet():
    assert w.commit_alert(80.0) is None
    assert w.commit_alert(None) is None


def test_severity_ladder():
    assert w.commit_alert(86.0)["severity"] == "warn"
    assert w.commit_alert(91.0)["severity"] == "high"
    assert w.commit_alert(97.5)["severity"] == "critical"


def test_threshold_override_from_config():
    assert w.commit_alert(80.0, {"warn": 70.0})["severity"] == "warn"


def test_live_percent_in_range_on_windows():
    p = w.commit_percent()
    assert p is None or 0 <= p <= 100
