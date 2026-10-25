"""اختباراتُ صحة المضخّة (W-20261025-002): تصعيد 30/90 دقيقةً بلا تكرار، والسجلُّ اليوميّ idempotent، ونسبةُ العبور."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402
import pump_health as ph  # noqa: E402

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=ledger.DOHA)


def _st(state, minutes_ago, held="0701"):
    return {"state": state, "state_ts": (NOW - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds"), "held_by": held}


def test_under_30_no_escalation():
    assert ph.plan_escalations({"W-1": _st("approved", 29)}, [], NOW) == []


def test_non_pump_stage_ignored():
    assert ph.plan_escalations({"W-1": _st("ready_for_review", 500)}, [], NOW) == []


def test_30_then_90_and_no_repeat(tmp_path):
    lp, log, rep = tmp_path / "e.jsonl", tmp_path / "esc.jsonl", tmp_path / "rep.txt"
    ledger.append_event("created", "W-20261025-901", {"title": "x"}, lp)
    st = {"W-20261025-901": _st("pushed", 35)}
    out = ph.escalation_pass(st, True, NOW, log, rep, lp)
    assert len(out) == 1 and "إعادةُ إحالة" in out[0] and not rep.exists()
    assert ph.escalation_pass(st, True, NOW, log, rep, lp) == []  # مرّةً واحدة
    st = {"W-20261025-901": {**st["W-20261025-901"]}}
    st["W-20261025-901"]["state_ts"] = (NOW - timedelta(minutes=95)).isoformat(timespec="seconds")
    out = ph.escalation_pass(st, True, NOW, log, rep, lp)
    assert any("تقرير 0101" in o for o in out)
    assert "W-20261025-901" in rep.read_text(encoding="utf-8")


def test_dry_run_writes_nothing(tmp_path):
    log, rep = tmp_path / "esc.jsonl", tmp_path / "rep.txt"
    out = ph.escalation_pass({"W-1": _st("merged", 100)}, False, NOW, log, rep, tmp_path / "e.jsonl")
    assert out and not log.exists() and not rep.exists()


def _ev(ts, state, by):
    return {"ts": ts.isoformat(timespec="seconds"), "id": "W-1", "kind": "state", "data": {"state": state, "by": by}}


def test_pass_through_rate():
    evs = [_ev(NOW - timedelta(hours=1), "pushed", "0101"), _ev(NOW - timedelta(hours=2), "merged", "0601"),
           _ev(NOW - timedelta(hours=30), "pushed", "0601"), _ev(NOW - timedelta(hours=1), "approved", "0501")]
    r = ph.pass_through(evs, NOW)
    assert r == {"total": 2, "by_pump": 1, "rate": 0.5}
    assert ph.pass_through([], NOW)["rate"] is None


def test_daily_log_idempotent_and_weekly(tmp_path):
    counter = tmp_path / "c.json"
    counter.write_text(json.dumps({"sessions": {"0701": {"count": 4}}}), encoding="utf-8")
    h = tmp_path / "h.jsonl"
    st = {"W-1": _st("pushed", 12)}
    assert ph.write_daily(st, [], NOW, h, counter) is True
    assert ph.write_daily(st, [], NOW, h, counter) is False
    row = json.loads(h.read_text(encoding="utf-8").splitlines()[0])
    assert row["messages"] == {"0701": 4} and row["ages"]["W-1"]["age_min"] == 12
    w = ph.weekly_summary(h, 7, NOW)
    assert w["days"] == 1 and w["oldest_age_min"] == 12 and w["messages_latest"] == {"0701": 4}
