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


def test_states_outside_wait_map_ignored_and_ready_for_review_goes_to_0101():
    """D-512م: ready_for_review راكدةٌ تُدفع إلى 0101 (المعتمِدة)؛ والمنشورةُ والمغلقةُ لا تُدفع."""
    assert ph.plan_escalations({"W-1": _st("published", 500), "W-2": _st("closed", 500)}, [], NOW) == []
    plan = ph.plan_escalations({"W-1": _st("ready_for_review", 500)}, [], NOW)
    assert [p["level"] for p in plan] == [90] and plan[0]["skipped"] == [30] and ph.nudge_target(plan[0]) == "0101"  # مستوىً واحدٌ في الدورة
    assert ph.plan_escalations({"W-1": _st("routed", 8 * 1440)}, [], NOW) == []  # أقدمُ من أسبوع تراكمٌ لا ركود


def test_routed_and_in_progress_nudge_holder_after_two_days_only():
    assert ph.plan_escalations({"W-1": _st("routed", 1439), "W-2": _st("in_progress", 1000)}, [], NOW) == []
    plan = ph.plan_escalations({"W-1": _st("routed", 1500, "0426")}, [], NOW)
    assert [p["level"] for p in plan] == [1440] and ph.nudge_target(plan[0]) == "0426"


def test_30_then_90_and_no_repeat(tmp_path):
    lp, log, rep = tmp_path / "e.jsonl", tmp_path / "esc.jsonl", tmp_path / "rep.txt"
    ledger.append_event("created", "W-20261025-901", {"title": "x"}, lp)
    sent: list[tuple[str, str]] = []
    send = lambda to, text: sent.append((to, text))  # noqa: E731
    st = {"W-20261025-901": _st("pushed", 35)}
    out = ph.escalation_pass(st, True, NOW, log, rep, lp, send)
    assert len(out) == 1 and "إعادةُ إحالة" in out[0] and not rep.exists()
    assert sent == [("0701", ph.nudge_text({"card": "W-20261025-901", "age": 35, "state": "pushed"}))]  # الحاملُ يُوقَظ بخطوته
    assert ph.escalation_pass(st, True, NOW, log, rep, lp, send) == [] and len(sent) == 1  # مرّةً واحدة
    st = {"W-20261025-901": {**st["W-20261025-901"]}}
    st["W-20261025-901"]["state_ts"] = (NOW - timedelta(minutes=95)).isoformat(timespec="seconds")
    out = ph.escalation_pass(st, True, NOW, log, rep, lp, send)
    assert any("تقرير 0101" in o for o in out)
    assert "W-20261025-901" in rep.read_text(encoding="utf-8")
    assert [s[0] for s in sent[1:]] == ["0701", "0101"]  # الثانية: الحامل ثمّ 0101


def test_merged_nudges_0601_regardless_of_holder(tmp_path):
    lp = tmp_path / "e.jsonl"
    ledger.append_event("created", "W-20261025-902", {"title": "x"}, lp)
    sent = []
    ph.escalation_pass({"W-20261025-902": _st("merged", 40, "0421")}, True, NOW, tmp_path / "esc.jsonl", tmp_path / "rep.txt", lp, lambda to, t: sent.append(to))
    assert sent == ["0601"]


def test_per_target_cap_defers_the_rest(tmp_path):
    lp = tmp_path / "e.jsonl"
    st = {}
    for i in range(5):
        cid = f"W-20261025-91{i}"
        ledger.append_event("created", cid, {"title": "x"}, lp)
        st[cid] = _st("merged", 40, "0421")
    sent = []
    out = ph.escalation_pass(st, True, NOW, tmp_path / "esc.jsonl", tmp_path / "rep.txt", lp, lambda to, t: sent.append(to))
    assert sent == ["0601"] * 3 and sum("مؤجَّلة" in o for o in out) == 2


def test_dry_run_writes_nothing(tmp_path):
    log, rep = tmp_path / "esc.jsonl", tmp_path / "rep.txt"
    sent = []
    out = ph.escalation_pass({"W-1": _st("merged", 100)}, False, NOW, log, rep, tmp_path / "e.jsonl", lambda to, t: sent.append(to))
    assert out and not log.exists() and not rep.exists() and sent == []


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


def test_missed_window_alert_once_and_only_after_it_ends(tmp_path):
    state, rep = tmp_path / "w.json", tmp_path / "rep.txt"
    state.write_text(json.dumps({"2026-10-30:1": {"eligible": [7, 8], "armed": [8], "blocked": [], "alerted": False}}), encoding="utf-8")
    inside = datetime(2026, 10, 30, 16, 29, tzinfo=ledger.DOHA)
    assert ph.missed_window_pass(True, inside, state, rep) == []  # النافذة لم تنتهِ
    after = datetime(2026, 10, 30, 16, 30, tzinfo=ledger.DOHA)
    out = ph.missed_window_pass(True, after, state, rep)
    assert len(out) == 1 and "#7" in out[0] and "#8" not in out[0]
    assert "#7" in rep.read_text(encoding="utf-8")
    assert ph.missed_window_pass(True, after, state, rep) == []  # لا تكرار


def test_missed_window_no_alert_when_all_eligible_were_armed(tmp_path):
    state = tmp_path / "w.json"
    state.write_text(json.dumps({"2026-10-30:2": {"eligible": [9], "armed": [9], "alerted": False}}), encoding="utf-8")
    after = datetime(2026, 10, 30, 21, 0, tzinfo=ledger.DOHA)
    assert ph.missed_window_pass(True, after, state, tmp_path / "r.txt") == []


def test_missed_window_preview_does_not_write(tmp_path):
    state, rep = tmp_path / "w.json", tmp_path / "rep.txt"
    state.write_text(json.dumps({"2026-10-29:2": {"eligible": [5], "armed": [], "alerted": False}}), encoding="utf-8")
    after = datetime(2026, 10, 30, 8, 0, tzinfo=ledger.DOHA)
    assert len(ph.missed_window_pass(False, after, state, rep)) == 1
    assert not rep.exists() and json.loads(state.read_text(encoding="utf-8"))["2026-10-29:2"]["alerted"] is False


def test_pushed_with_open_pr_is_not_called_pushed_without_pr(tmp_path):
    """(W-20261028-028) pushed وطلبُها مفتوح: الدفعُ إلى 0601 بنصٍّ يذكر الطلب، لا «دُفع بلا طلبٍ مفتوح» إلى الحامل."""
    lp = tmp_path / "e.jsonl"
    ledger.append_event("created", "W-20261028-950", {"title": "x"}, lp)
    texts = []
    st = {"W-20261028-950": _st("pushed", 40, "0701")}
    ph.escalation_pass(st, True, NOW, tmp_path / "esc.jsonl", tmp_path / "rep.txt", lp, lambda to, t: texts.append((to, t)), open_prs={"W-20261028-950": 1234})
    assert [to for to, _ in texts] == ["0601"]
    assert "#1234" in texts[0][1] and "بلا طلب" not in texts[0][1]


def test_pushed_without_pr_keeps_the_original_message(tmp_path):
    lp = tmp_path / "e.jsonl"
    ledger.append_event("created", "W-20261028-951", {"title": "x"}, lp)
    texts = []
    ph.escalation_pass({"W-20261028-951": _st("pushed", 40, "0701")}, True, NOW, tmp_path / "esc.jsonl", tmp_path / "rep.txt", lp,
                       lambda to, t: texts.append((to, t)), open_prs={})
    assert texts[0][0] == "0701" and "بلا طلب" in texts[0][1]


def test_recorded_pr_field_is_used_only_when_open_prs_were_not_read():
    item = {"state": "pushed", "pr": 77}
    assert ph.pr_of("W-1", item, None) == 77
    assert ph.pr_of("W-1", item, {}) is None  # قُرئت الطلباتُ ولا طلبَ مفتوحاً (أُغلق بلا دمج)
