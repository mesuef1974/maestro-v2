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


def test_counter_guard_blocks_above_the_quota_margin():
    g = wm.COUNTER_GUARD
    dirs = {"0701": "local_a", "0702": "local_b"}
    ev = _routed("0701") + [
        created("W-20261016-009"),
        state("W-20261016-009", "routed", NEW, held_by="0702"),
    ]
    assert wm.plan(ev, CUR, dirs, set(), verify=ok, sent=g - 2).wakes  # الحدُّ نفسُه مسموح
    p = wm.plan(ev, CUR, dirs, set(), verify=ok, sent=g - 1)  # تجاوزٌ بواحد
    assert p.wakes == {} and "msg_counter" in p.halted
    assert wm.plan(_routed("0701"), CUR, dirs, set(), verify=ok, sent=g).halted


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


def test_counter_guard_follows_msg_counter_quota():
    assert wm.COUNTER_GUARD == wm.msg_counter.LIMIT - wm.COUNTER_MARGIN == 540


def test_halt_text_reports_the_read_quota_not_a_hardcoded_one():
    p = wm.plan(_routed("0701"), CUR, {"0701": "local_x"}, set(), verify=ok, sent=wm.COUNTER_GUARD)
    assert p.halted and str(wm.msg_counter.LIMIT) in p.halted and "من 150" not in p.halted


# ── الإيقاظ بالتغيير لا بالزمن (بصمة الحالة) ──────────────────────────────────

from datetime import datetime, timedelta  # noqa: E402

T0 = datetime.fromisoformat("2026-10-16T11:30:00+03:00")


def test_fingerprint_is_stable_for_the_same_ledger():
    ev = _routed("0701")
    assert wm.fingerprint(ev, T0) == wm.fingerprint(list(ev), T0)


def test_fingerprint_changes_when_a_card_state_or_holder_changes():
    a = wm.fingerprint(_routed("0701"), T0)
    ev = _routed("0701") + [state("W-20261016-001", "in_progress", "2026-10-16T11:10:00+03:00", held_by="0701")]
    assert wm.fingerprint(ev, T0) != a
    assert wm.fingerprint(_routed("0501"), T0) != a


def test_fingerprint_changes_when_a_card_crosses_its_stale_limit():
    ev = _routed("0701")  # routed منذ 11:00: حدُّها ثلاث ساعات
    before = wm.fingerprint(ev, T0)
    assert wm.fingerprint(ev, T0 + timedelta(hours=1)) == before
    assert wm.fingerprint(ev, T0 + timedelta(hours=3)) != before


def test_fingerprint_includes_the_pr_snapshot_and_ignores_finished_cards():
    ev = _routed("0701")
    assert wm.fingerprint(ev, T0, "pr 1 clean") != wm.fingerprint(ev, T0, "pr 1 blocked")
    done = ev + [state("W-20261016-001", "published", "2026-10-16T11:20:00+03:00")]
    assert wm.fingerprint(done, T0) == wm.fingerprint([], T0)


def test_read_fingerprint_missing_or_corrupt_counts_as_changed(tmp_path):
    assert wm.read_fingerprint(tmp_path / "none.json") == ""
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    assert wm.read_fingerprint(bad) == ""
    good = tmp_path / "ok.json"
    wm.write_fingerprint("abc123", good)
    assert wm.read_fingerprint(good) == "abc123" and not list(tmp_path.glob("*.tmp"))


def test_report_is_a_script_line_with_counts_and_stale():
    line = wm.report(_routed("0701"), T0 + timedelta(hours=4), "fp1")
    assert "fp1" in line and "routed 1 (عالقة 1)" in line


def _setup_main(tmp_path, monkeypatch, events):
    import json

    import session_directory as sd

    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n", encoding="utf-8")
    monkeypatch.setattr(wm, "EVENTS", path)
    monkeypatch.setattr(wm, "CURSOR", tmp_path / "cursor.json")
    monkeypatch.setattr(wm, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(wm, "FINGERPRINT", tmp_path / "fp.json")
    monkeypatch.setattr(sd, "entries", lambda: {"0701": {"id": "local_x"}})
    monkeypatch.setattr(wm, "live_sessions", lambda: set())
    monkeypatch.setattr(wm, "ground_truth_ok", lambda i, s: True)
    monkeypatch.setattr(wm, "sender_count", lambda *a, **k: 0)


def test_changed_only_is_silent_and_idempotent_when_nothing_changed(tmp_path, monkeypatch, capsys):
    _setup_main(tmp_path, monkeypatch, _routed("0701"))
    wm.main(["--changed-only", "--commit", "--all"])
    first = capsys.readouterr().out
    assert "تغيّرت الحالة" in first
    assert (tmp_path / "fp.json").is_file()
    wm.main(["--changed-only", "--commit", "--all"])
    second = capsys.readouterr().out
    assert "لا تغيّر" in second and "إلى " not in second
    assert len((tmp_path / "log.jsonl").read_text(encoding="utf-8").splitlines()) == 1  # لا كتابةَ ثانيةً في السجلّ


def test_changed_only_without_commit_never_saves_the_fingerprint(tmp_path, monkeypatch, capsys):
    _setup_main(tmp_path, monkeypatch, _routed("0701"))
    wm.main(["--changed-only", "--all"])
    capsys.readouterr()
    assert not (tmp_path / "fp.json").exists()
    wm.main(["--changed-only", "--all"])
    assert "لا تغيّر" not in capsys.readouterr().out


def test_halted_plan_does_not_save_the_fingerprint_so_it_is_retried(tmp_path, monkeypatch, capsys):
    _setup_main(tmp_path, monkeypatch, _routed("0701"))
    halted = wm.WakePlan()
    halted.halted = "سقفٌ"
    monkeypatch.setattr(wm, "make_plan", lambda *a, **k: halted)
    wm.main(["--changed-only", "--commit", "--all"])
    assert "توقّف" in capsys.readouterr().out
    assert not (tmp_path / "fp.json").exists()


def test_watch_changed_only_prints_one_report_then_stays_silent(tmp_path, monkeypatch, capsys):
    _setup_main(tmp_path, monkeypatch, _routed("0701"))
    wm.write_fingerprint("old", tmp_path / "fp.json")
    wm.main(["--watch", "--once", "--changed-only", "--all"])
    assert "تغيّرت الحالة" in capsys.readouterr().out
    wm.write_fingerprint(wm.fingerprint(wm.read_events(tmp_path / "events.jsonl"), datetime.now().astimezone()), tmp_path / "fp.json")
    wm.main(["--watch", "--once", "--changed-only", "--all"])
    assert capsys.readouterr().out == ""


def test_live_cap_is_six_and_excess_sessions_are_queued_not_dropped():
    """W-20261023-004 (0.13): لا جلسةَ سابعةً تُوقَظ؛ الزائدُ يُؤجَّل ويبقى المؤشّرُ فيُعاد."""
    assert wm.MAX_LIVE == 6
    ev = []
    for n, holder in enumerate(("0201", "0301", "0501", "0601", "0701", "0801", "0901")):
        i = f"W-20261016-{n:03d}"
        ev += [created(i), state(i, "routed", NEW, held_by=holder)]
    dirs = {h: f"local_{h}" for h in ("0201", "0301", "0501", "0601", "0701", "0801", "0901")}
    live = {"0101", "0102", "0103", "0104"}  # سقفُ الدقيقة 3 يُدخل ثلاثاً فيصير المجموع 7: يُؤجَّل واحدٌ بسقف التزامن
    p = wm.plan(ev, CUR, dirs, live, verify=ok, recent=0)
    assert len(set(p.wakes) | live) <= 6 and p.deferred and len(p.wakes) == 2
    assert any("سقفُ 6" in why for _i, why in p.skipped)


def test_an_already_live_session_is_woken_even_when_the_cap_is_full():
    ev = [created("W-20261016-001"), state("W-20261016-001", "routed", NEW, held_by="0201")]
    live = {f"{n:04d}" for n in (201, 301, 501, 601, 701, 801)}
    p = wm.plan(ev, CUR, DIR, live, verify=ok)
    assert list(p.wakes) == ["0201"] and not p.halted


# ===== إيقاظ ما بعد المسح (W-20261025-001) =====
from datetime import datetime, timedelta, timezone  # noqa: E402

_NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone(timedelta(hours=3)))


def test_after_clear_wakes_idle_session_with_card_reading_message():
    p = wm.stale_plan([], DIR, set(), _NOW, verify=ok, cleared={"0201": "x"})
    assert p.wakes == {"0201": [(wm.CLEAR_ID, "pending_clear")]}
    msg = wm.message_for("0201", p.wakes["0201"])
    assert "role_cards/0201.md" in msg and "my_state.py 0201" in msg


def test_after_clear_skips_live_or_outside_channel_or_unknown():
    assert wm.stale_plan([], DIR, {"0201"}, _NOW, verify=ok, cleared={"0201": "x"}).wakes == {}
    assert wm.stale_plan([], DIR, set(), _NOW, verify=ok, channel={"0301"}, cleared={"0201": "x"}).wakes == {}
    p = wm.stale_plan([], DIR, set(), _NOW, verify=ok, cleared={"0999": "x"})
    assert p.wakes == {} and p.skipped


def test_after_clear_payload_needs_valid_number():
    with pytest.raises(ValueError):
        wm.payload(wm.CLEAR_ID, "pending_clear", "")
    with pytest.raises(ValueError):
        wm.payload(wm.CLEAR_ID, "pending_clear", "rm -rf")


def test_after_clear_watch_lines_use_session_number():
    p = wm.stale_plan([], DIR, set(), _NOW, verify=ok, cleared={"0201": "x"})
    out = wm.watch_lines(p, DIR, set())
    assert len(out) == 1 and "role_cards/0201.md" in out[0]


def test_cleared_session_not_live_by_window_but_running_wins():
    """W-20261025-001: علامةُ مسحٍ معلَّقةٌ تُسقط الحياةَ المقدَّرةَ بالنافذة؛ و`--running` الفعليُّ يحكم وحدَه."""
    assert wm.live_minus_cleared({"0301", "0501"}, {"0301": "x"}, None) == {"0501"}
    assert wm.live_minus_cleared({"0301"}, {"0301": "x"}, {"0301"}) == {"0301"}
    p = wm.stale_plan([], DIR, wm.live_minus_cleared({"0201"}, {"0201": "x"}, None), _NOW, verify=lambda *_: True, cleared={"0201": "x"})
    assert "0201" in p.wakes
