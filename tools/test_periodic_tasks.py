"""W-20261026-011: جدولٌ واحد للمهامّ الدوريّة يرسل الكنّاسُ بموجبه لصاحب كلّ مهمّةٍ رسالةً واحدةً في موعدها، مرّةً في اليوم."""
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import periodic_tasks as pt
import pytest
import wake_monitor as wm

DOHA = timezone(timedelta(hours=3))
ROOT = Path(__file__).resolve().parent.parent
SUN = datetime(2026, 10, 25, 7, 45, tzinfo=DOHA)  # الأحد
WED = datetime(2026, 10, 28, 9, 30, tzinfo=DOHA)
THU = datetime(2026, 10, 29, 7, 45, tzinfo=DOHA)


def _root(tmp_path, tasks):
    (tmp_path / "projects" / "schoolos").mkdir(parents=True)
    (tmp_path / "projects" / "schoolos" / "periodic_tasks.json").write_text(json.dumps({"tasks": tasks}, ensure_ascii=False), encoding="utf-8")
    return tmp_path


T = [
    {"id": "a", "owner": "0301", "days": ["sun"], "time": "07:30", "what": "فحص أ", "cmd": "python x.py"},
    {"id": "b", "owner": "0301", "days": ["sun", "thu"], "time": "07:30", "what": "فحص ب", "cmd": ""},
    {"id": "c", "owner": "0701", "days": ["wed"], "time": "09:00", "what": "عيّنة"},
]


def test_live_schedule_is_valid_and_its_tools_exist():
    tasks = pt.load_tasks()
    assert tasks and pt.validate(tasks) == []
    for t in tasks:
        for tool in __import__("re").findall(r"tools/([\w]+\.py)", t.get("cmd", "")):
            assert (ROOT / "tools" / tool).exists(), f"{t['id']}: {tool} غير موجود"


def test_validate_rejects_bad_rows():
    bad = [{"id": "x", "owner": "03", "days": ["sunday"], "time": "7:30", "what": ""}, {"id": "x", "owner": "0301", "days": ["sun"], "time": "07:30", "what": "ok"}]
    msgs = " ".join(pt.validate(bad))
    assert "owner" in msgs and "days" in msgs and "time" in msgs and "what" in msgs and "مكرَّر" in msgs


def test_due_by_weekday_time_and_once_per_day():
    assert [t["id"] for t in pt.due(T, SUN, {})] == ["a", "b"]
    assert pt.due(T, SUN.replace(hour=7, minute=29), {}) == []  # قبل الموعد
    assert [t["id"] for t in pt.due(T, SUN, {"a": "2026-10-25"})] == ["b"]  # أُرسلت اليوم
    assert [t["id"] for t in pt.due(T, SUN, {"a": "2026-10-18"})] == ["a", "b"]  # أسبوعٌ سابق
    assert [t["id"] for t in pt.due(T, WED, {})] == ["c"] and [t["id"] for t in pt.due(T, THU, {})] == ["b"]
    assert pt.due(T, SUN.astimezone(UTC), {}) == pt.due(T, SUN, {})  # المنطقة الزمنيّة لا تغيّر اليوم


def test_run_due_sends_one_message_per_owner_and_is_idempotent(tmp_path):
    root = _root(tmp_path, T)
    sent = pt.run_due(SUN, root)
    assert sent == {"0301": ["a", "b"]}
    import inbox

    msgs = inbox.pending("0301", root)
    assert len(msgs) == 1 and "فحص أ" in msgs[0]["text"] and "python x.py" in msgs[0]["text"] and "فحص ب" in msgs[0]["text"] and msgs[0]["from"] == "0000"
    assert pt.run_due(SUN + timedelta(minutes=15), root) == {}  # الدورةُ التالية لا تكرّر
    assert len(inbox.pending("0301", root)) == 1
    assert pt.run_due(THU, root) == {"0301": ["b"]}  # الخميس: ب وحدها


def test_late_sweeper_still_sends_same_day_but_dry_run_sends_nothing(tmp_path):
    root = _root(tmp_path, T)
    assert pt.run_due(SUN, root, dry_run=True) == {"0301": ["a", "b"]}
    import inbox

    assert inbox.pending("0301", root) == [] and pt.load_state(root) == {}
    assert pt.run_due(SUN.replace(hour=15), root) == {"0301": ["a", "b"]}


def test_failed_send_does_not_mark_task_done(tmp_path):
    root = _root(tmp_path, T)

    def boom(owner, text):
        raise OSError("قرص ممتلئ")

    with pytest.raises(OSError):
        pt.run_due(SUN, root, send=boom)
    assert pt.load_state(root) == {}  # لم يُسجَّل شيء فتُعاد في الدورة التالية


def test_wake_monitor_runs_periodic_only_on_commit_or_watch(monkeypatch):
    calls = []
    monkeypatch.setattr(wm, "run_periodic", lambda now: calls.append(now) or {})
    import inbox as ib

    monkeypatch.setattr(ib, "pending_nums", lambda root=None: {})
    monkeypatch.setattr(wm, "live_for", lambda a: set())
    monkeypatch.setattr(wm, "sender_count", lambda s: 0)
    monkeypatch.setattr(wm, "read_log", lambda: [])
    base = {"all": True, "stale": True, "bells_only": False, "running": None, "sender": "0701"}
    wm.make_plan(wm.argparse.Namespace(**base), [], "", {})
    assert calls == []  # عرضٌ جافّ
    wm.make_plan(wm.argparse.Namespace(**base, commit=True), [], "", {})
    wm.make_plan(wm.argparse.Namespace(**base, watch=True), [], "", {})
    assert len(calls) == 2


def test_run_periodic_swallows_errors(monkeypatch, capsys):
    monkeypatch.setattr(pt, "run_due", lambda now, root: (_ for _ in ()).throw(ValueError("جدول معيب")))
    assert wm.run_periodic(SUN) == {}
    assert "جدول معيب" in capsys.readouterr().err


def _sent_log(root):
    return [json.loads(x) for x in pt.log_path(root).read_text(encoding="utf-8").splitlines()]


def test_every_send_is_logged_with_its_time(tmp_path):
    root = _root(tmp_path, T)
    pt.run_due(SUN, root, send=lambda o, t: None)
    rows = _sent_log(root)
    assert {(r["task"], r["kind"], r["owner"]) for r in rows} == {("a", "sent", "0301"), ("b", "sent", "0301")}
    assert all(r["ts"] == SUN.isoformat(timespec="seconds") for r in rows)


def test_dry_run_logs_nothing(tmp_path):
    root = _root(tmp_path, T)
    pt.run_due(SUN, root, send=lambda o, t: None, dry_run=True)
    assert not pt.log_path(root).exists()


def test_unfinished_task_is_resent_after_six_hours_at_most_twice_and_not_across_days(tmp_path):
    root = _root(tmp_path, [T[0]])
    sent = []
    send = lambda o, t: sent.append(t)  # noqa: E731
    pt.run_due(SUN, root, send=send)  # 07:45 أول إرسال
    pt.run_due(SUN + timedelta(hours=5, minutes=59), root, send=send)
    assert len(sent) == 1  # قبل 6 ساعات لا إعادة
    pt.run_due(SUN + timedelta(hours=6), root, send=send)  # 13:45
    assert len(sent) == 2 and "إعادة" in sent[1]
    pt.run_due(SUN + timedelta(hours=12), root, send=send)  # 19:45
    assert len(sent) == 3
    pt.run_due(SUN + timedelta(hours=16), root, send=send)  # 23:45: سقف الإعادتين
    assert len(sent) == 3
    assert [r["kind"] for r in _sent_log(root)] == ["sent", "resent", "resent"]
    next_sun = SUN + timedelta(days=7)
    pt.run_due(next_sun, root, send=send)  # الأسبوع التالي: إرسالٌ جديدٌ لا إعادة
    assert len(sent) == 4 and "إعادة" not in sent[3].splitlines()[1]


def test_done_stops_that_task_only_and_unknown_id_is_rejected(tmp_path):
    root = _root(tmp_path, T)
    sent = []
    send = lambda o, t: sent.append(t)  # noqa: E731
    pt.run_due(SUN, root, send=send)
    assert pt.mark_done("a", SUN + timedelta(hours=1), root) == "0301"
    with pytest.raises(ValueError):
        pt.mark_done("zzz", SUN, root)
    pt.run_due(SUN + timedelta(hours=6), root, send=send)
    assert len(sent) == 2
    resent_lines = [x for x in sent[1].splitlines() if "[إعادة:" in x]
    assert len(resent_lines) == 1 and "فحص ب" in resent_lines[0]  # b وحدها، لا a


def test_message_tells_how_to_record_completion(tmp_path):
    root = _root(tmp_path, [T[0]])
    sent = []
    pt.run_due(SUN, root, send=lambda o, t: sent.append(t))
    assert "periodic_tasks.py done a" in sent[0]


def test_done_command_exit_codes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pt, "ROOT", _root(tmp_path, T))
    assert pt.main(["done", "a"]) == 0
    assert pt.main(["done", "nope"]) == 2
    assert "مجهول" in capsys.readouterr().err
