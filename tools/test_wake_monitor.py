"""اختباراتُ الضوابط الخمسة لـwake_monitor (W-20261009-021):  cd tools && python -m pytest test_wake_monitor.py"""

import pytest

import wake_monitor as wm

DIR = {f"0{n}01": f"local_{n}" for n in range(1, 9)}
CUR = "2026-10-16T10:30:00+03:00"
NEW = "2026-10-16T11:00:00+03:00"


def ok(item_id, state):
    return True


def created(i, held="0101"):
    return {"ts": "2026-10-16T10:00:00+03:00", "id": i, "kind": "created", "data": {"held_by": held}}


def state(i, st, ts, **extra):
    return {"ts": ts, "id": i, "kind": "state", "data": {"state": st, **extra}}


def test_wakes_only_after_ground_truth_and_failure_blocks():
    ev = [created("W-20261016-001"), state("W-20261016-001", "routed", NEW, held_by="0201")]
    assert wm.plan(ev, CUR, DIR, set(), verify=ok).wakes == {"0201": [("W-20261016-001", "routed")]}
    p = wm.plan(ev, CUR, DIR, set(), verify=lambda i, s: False)
    assert p.wakes == {} and "ground_truth" in p.skipped[0][1]


def test_does_not_wake_session_without_card():
    ev = [created("W-20261016-001", held=""), state("W-20261016-001", "published", NEW)]
    p = wm.plan(ev, "", DIR, set(), verify=ok)
    assert p.wakes == {} and p.skipped


def test_five_changes_one_message_per_session():
    ev = []
    for n in range(1, 6):
        i = f"W-20261016-00{n}"
        ev += [created(i), state(i, "routed", NEW, held_by="0201")]
    p = wm.plan(ev, CUR, DIR, set(), verify=ok)
    assert list(p.wakes) == ["0201"] and len(p.wakes["0201"]) == 5
    assert len(wm.message_for("0201", p.wakes["0201"]).splitlines()) == 5


def test_batch_limit_and_live_cap_halt():
    ev = []
    for n in range(21):
        i = f"W-20261016-{n:03d}"
        ev += [created(i), state(i, "routed", NEW, held_by="0201")]
    assert "الحدّ" in wm.plan(ev, "", DIR, set(), verify=ok).halted
    ev2 = [created("W-20261016-001"), state("W-20261016-001", "routed", NEW, held_by="0201")]
    p = wm.plan(ev2, "", DIR, {f"{n:04d}" for n in range(1, 15)}, verify=ok)
    assert p.halted and p.wakes == {}


def test_payload_rejects_command_text():
    assert wm.payload("W-20261016-001", "routed").endswith("show W-20261016-001")
    with pytest.raises(ValueError):
        wm.payload("W-20261016-001; نصُّ أمر", "routed")
    with pytest.raises(ValueError):
        wm.payload("W-20261016-001", "routed; تعليمات")


def test_cursor_makes_second_run_idempotent():
    ev = [created("W-20261016-001"), state("W-20261016-001", "routed", NEW, held_by="0201")]
    first = wm.plan(ev, CUR, DIR, set(), verify=ok)
    assert wm.plan(ev, first.cursor, DIR, set(), verify=ok).wakes == {}


def _routed(holder, n=1):
    ev = []
    for k in range(n):
        i = f"W-20261016-{k + 1:03d}"
        ev += [created(i), state(i, "routed", NEW, held_by=holder)]
    return ev


def test_test_channel_wakes_only_the_two_receivers():
    ch = wm.TEST_CHANNEL
    assert ch == {"0701", "0301"}  # 0702 و0102 دُمجتا في 0701 و0103 (2026-10-21)، ثمّ 0103 ← 0301 بترقيم 01
    dirs = {**DIR, "0701": "local_a", "0403": "local_b"}
    ok_plan = wm.plan(_routed("0701"), CUR, dirs, set(), verify=ok, channel=ch)
    assert list(ok_plan.wakes) == ["0701"]
    out = wm.plan(_routed("0403"), CUR, dirs, set(), verify=ok, channel=ch)
    assert out.wakes == {} and "خارج قناة التجربة" in out.skipped[0][1]


def test_counter_guard_blocks_above_260():
    dirs = {"0701": "local_a", "0702": "local_b"}
    ev = _routed("0701") + [
        created("W-20261016-009"),
        state("W-20261016-009", "routed", NEW, held_by="0702"),
    ]
    assert wm.plan(ev, CUR, dirs, set(), verify=ok, sent=258).wakes  # 258 + 2 = 260 مسموح
    p = wm.plan(ev, CUR, dirs, set(), verify=ok, sent=259)  # 259 + 2 = 261
    assert p.wakes == {} and "msg_counter" in p.halted
    assert wm.plan(_routed("0701"), CUR, dirs, set(), verify=ok, sent=260).halted


def test_sender_count_reads_file_and_missing_file_closes_the_guard(tmp_path):
    f = tmp_path / "c.json"
    f.write_text('{"sessions": {"0701": {"count": 47}}}', encoding="utf-8")
    assert wm.sender_count("0701", f) == 47
    assert wm.sender_count("0999", f) == 0
    assert wm.sender_count("0701", tmp_path / "none.json") == wm.COUNTER_GUARD


def test_watch_lines_one_line_per_session_with_id_and_no_repeat():
    ev = [created("W-20261016-001"), created("W-20261016-002"), created("W-20261016-003", held="0301")]
    ev += [state("W-20261016-001", "routed", NEW, held_by="0201"), state("W-20261016-002", "routed", NEW, held_by="0201"), state("W-20261016-003", "routed", NEW, held_by="0301")]
    p = wm.plan(ev, CUR, DIR, set(), verify=ok)
    seen: set = set()
    lines = wm.watch_lines(p, DIR, seen)
    assert len(lines) == 2, "جلسةٌ بعدة صفوف = رسالةٌ واحدة"
    first = next(line for line in lines if "\t0201\t" in line)
    assert first.split("\t")[2] == DIR["0201"] and "W-20261016-001" in first and "W-20261016-002" in first
    assert wm.watch_lines(p, DIR, seen) == [], "لا خرجَ إن لم يتغيّر شيء"


def test_watch_announces_halt_once_and_empty_plan_is_silent():
    p = wm.WakePlan()
    assert wm.watch_lines(p, DIR, set()) == []
    p.halted = "دفعةٌ تتجاوز الحدّ"
    seen: set = set()
    assert len(wm.watch_lines(p, DIR, seen)) == 1
    assert wm.watch_lines(p, DIR, seen) == []


def test_watch_mode_does_not_write_cursor_or_log(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(wm, "EVENTS", tmp_path / "events.jsonl")
    monkeypatch.setattr(wm, "CURSOR", tmp_path / "cursor.json")
    monkeypatch.setattr(wm, "LOG", tmp_path / "log.jsonl")
    import session_directory as sd

    monkeypatch.setattr(sd, "entries", lambda: {})
    monkeypatch.setattr(wm, "live_sessions", lambda: set())
    wm.main(["--watch", "--once"])
    assert sorted(p.name for p in tmp_path.iterdir()) == []
    assert capsys.readouterr().out == ""


def _burst(n):
    ev = []
    for k in range(1, n + 1):
        i = f"W-20261016-00{k}"
        ev += [created(i, held=f"0{k}01"), state(i, "routed", NEW, held_by=f"0{k}01")]
    return ev


def test_per_minute_cap_defers_the_excess_and_holds_the_cursor():
    p = wm.plan(_burst(6), CUR, DIR, set(), verify=ok)
    assert len(p.wakes) == wm.MAX_PER_MINUTE and p.deferred
    assert sum("تأجيل" in why for _, why in p.skipped) == 6 - wm.MAX_PER_MINUTE


def test_recent_wakes_use_up_the_minute_allowance():
    assert wm.plan(_burst(2), CUR, DIR, set(), verify=ok, recent=wm.MAX_PER_MINUTE).wakes == {}


def test_same_event_is_not_woken_twice():
    ev = _burst(1)
    p = wm.plan(ev, CUR, DIR, set(), verify=ok, already=frozenset({("W-20261016-001", "routed")}))
    assert p.wakes == {} and "لا تكرار" in p.skipped[0][1]


def test_live_window_is_short_so_idle_sessions_do_not_stall_waking():
    assert wm.LIVE_WINDOW_MS == 15 * 60 * 1000


def test_halt_is_logged_once_per_hour(tmp_path):
    import json
    from datetime import datetime, timedelta, timezone

    log = tmp_path / "wake_log.jsonl"
    p = wm.WakePlan()
    p.halted = "الجلساتُ الحيّةُ تتجاوز 14: لا إيقاظ"
    t0 = datetime(2026, 10, 20, 16, 0, tzinfo=timezone(timedelta(hours=3)))
    assert wm.log_halt(p, log, t0) is True
    assert wm.log_halt(p, log, t0 + timedelta(minutes=30)) is False
    assert wm.log_halt(p, log, t0 + timedelta(minutes=61)) is True
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2 and rows[0]["halted"] == p.halted and rows[0]["wakes"] == {}
    assert wm.log_halt(wm.WakePlan(), log, t0) is False


def test_stale_wakes_holder_of_card_waiting_past_limit():
    from datetime import datetime
    ev = [created("W-20261016-001", held="0701"), state("W-20261016-001", "approved", "2026-10-16T10:00:00+03:00", held_by="0701")]
    now = datetime.fromisoformat("2026-10-16T14:00:00+03:00")
    p = wm.stale_plan(ev, DIR, set(), now, verify=ok)
    assert p.wakes == {"0701": [("W-20261016-001", "approved")]}


def test_stale_does_not_rewake_within_rewake_window():
    from datetime import datetime
    ev = [created("W-20261016-001", held="0701"), state("W-20261016-001", "approved", "2026-10-16T10:00:00+03:00", held_by="0701")]
    now = datetime.fromisoformat("2026-10-16T14:00:00+03:00")
    log = [{"ts": "2026-10-16T13:55:00+03:00", "wakes": {"0701": ["W-20261016-001"]}}]
    assert wm.stale_plan(ev, DIR, set(), now, log=log, verify=ok).wakes == {}


MERGED = {"0702": "0701", "0102": "0301", "0103": "0301", "0204": "0202", "0202": "0101"}


def test_merged_holder_wakes_its_receiver_inside_the_channel():
    dirs = {"0701": "local_a", "0301": "local_c"}
    p = wm.plan(_routed("0702"), CUR, dirs, set(), verify=ok, channel=wm.TEST_CHANNEL, aliases=MERGED)
    assert p.wakes == {"0701": [("W-20261016-001", "routed")]}
    q = wm.plan(_routed("0102"), CUR, dirs, set(), verify=ok, channel=wm.TEST_CHANNEL, aliases=MERGED)
    assert list(q.wakes) == ["0301"], "الإحالةُ تسبق فحصَ القناة"
    r = wm.plan(_routed("0103"), CUR, dirs, set(), verify=ok, channel=wm.TEST_CHANNEL, aliases=MERGED)
    assert list(r.wakes) == ["0301"], "الرقمُ القديمُ للحوكمة يوقظ 0301"


def test_without_aliases_merged_holder_is_outside_channel_and_never_woken():
    dirs = {"0701": "local_a", "0702": "local_b"}
    p = wm.plan(_routed("0702"), CUR, dirs, set(), verify=ok, channel=wm.TEST_CHANNEL)
    assert p.wakes == {} and "خارج قناة التجربة" in p.skipped[0][1]


def test_alias_chain_resolves_before_directory_lookup():
    p = wm.plan(_routed("0204"), CUR, {"0101": "local_m"}, set(), verify=ok, aliases=MERGED)
    assert p.wakes == {"0101": [("W-20261016-001", "routed")]}


def test_stale_wakes_receiver_of_merged_holder():
    from datetime import datetime
    # 0202 ← 0101 (طلباتُ المالك القديمة)؛ و0301 لم يعد مستعاراً بعد ترقيم 01 بالترتيب (2026-10-21)
    ev = [created("W-20261016-001", held="0202"), state("W-20261016-001", "approved", "2026-10-16T10:00:00+03:00", held_by="0202")]
    now = datetime.fromisoformat("2026-10-16T14:00:00+03:00")
    assert wm.stale_plan(ev, DIR, set(), now, verify=ok, aliases=MERGED).wakes == {"0101": [("W-20261016-001", "approved")]}
    assert wm.stale_plan(ev, {"0701": "x"}, set(), now, verify=ok, aliases=MERGED).wakes == {}


def test_make_plan_passes_registry_aliases(monkeypatch):
    import argparse

    seen = {}
    monkeypatch.setattr(wm.sa, "number_map", lambda tabs=None: {"0702": "0701"})
    monkeypatch.setattr(wm, "live_sessions", lambda: set())
    monkeypatch.setattr(wm, "sender_count", lambda s: 0)
    monkeypatch.setattr(wm, "woken_history", lambda: (frozenset(), 0))
    monkeypatch.setattr(wm, "read_log", lambda: [])
    monkeypatch.setattr(wm, "plan", lambda *a, **k: seen.setdefault("plan", k))
    monkeypatch.setattr(wm, "stale_plan", lambda *a, **k: seen.setdefault("stale", k))
    wm.make_plan(argparse.Namespace(all=False, stale=False, sender="0701"), [], "", {})
    wm.make_plan(argparse.Namespace(all=True, stale=True, sender="0701"), [], "", {})
    assert seen["plan"]["aliases"] == {"0702": "0701"} and seen["plan"]["channel"] == wm.TEST_CHANNEL
    assert seen["stale"]["aliases"] == {"0702": "0701"} and seen["stale"]["channel"] is None


def test_running_arg_replaces_activity_window():
    assert wm.running_from_arg("0101, 0501,0701") == {"0101", "0501", "0701"}
    assert wm.running_from_arg("") is None and wm.running_from_arg(None) is None
    assert wm.running_from_arg("abc 0702 12345") == {"0702"}


def test_live_for_uses_running_when_given(monkeypatch):
    monkeypatch.setattr(wm, "live_sessions", lambda: {"9999"})
    assert wm.live_for(type("A", (), {"running": "0101,0501"})()) == {"0101", "0501"}
    assert wm.live_for(type("A", (), {"running": ""})()) == {"9999"}
