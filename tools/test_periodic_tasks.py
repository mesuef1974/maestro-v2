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


def test_every_send_is_logged_in_the_ledger_with_its_due_time(tmp_path):
    root = _root(tmp_path, T)
    pt.run_due(SUN, root)
    log = pt.read_log(root)
    assert [(r["k"], r["id"]) for r in log] == [("sent", "a"), ("sent", "b")]
    assert all(r["owner"] == "0301" and r["ts"].startswith("2026-10-25") for r in log)
    assert pt.run_due(SUN, root, dry_run=True) == {}  # عرضٌ جافّ: لا سطرَ جديد
    assert len(pt.read_log(root)) == 2


def test_unrecorded_task_is_resent_after_six_hours_then_stops_at_cap(tmp_path):
    import inbox

    root = _root(tmp_path, T)
    pt.run_due(SUN, root)
    assert pt.run_due(SUN + timedelta(hours=5, minutes=59), root) == {}  # قبل 6 ساعات
    assert pt.run_due(SUN + timedelta(hours=6), root) == {"0301": ["a", "b"]}  # أُعيدت
    resent = inbox.pending("0301", root)[-1]["text"]
    assert "إعادة" in resent and "فحص أ" in resent and "done" in resent
    assert pt.run_due(SUN + timedelta(hours=6, minutes=15), root) == {}  # لا تكرارَ قبل 6 ساعات أخرى
    assert pt.run_due(SUN + timedelta(hours=12), root) == {"0301": ["a", "b"]}  # الإعادة الثانية
    assert pt.run_due(SUN + timedelta(hours=18), root) == {}  # بلغت السقف (إرسالٌ + إعادتان)
    assert len(inbox.pending("0301", root)) == 3


def test_recorded_result_stops_resending_only_that_task(tmp_path):
    root = _root(tmp_path, T)
    pt.run_due(SUN, root)
    pt.mark_done("a", "0301", SUN + timedelta(hours=2), root)
    assert pt.run_due(SUN + timedelta(hours=6), root) == {"0301": ["b"]}


def test_mark_done_rejects_unknown_task_and_cli_records_it(tmp_path, monkeypatch):
    root = _root(tmp_path, T)
    with pytest.raises(ValueError):
        pt.mark_done("zzz", "0301", SUN, root)
    monkeypatch.setattr(pt, "ROOT", root)
    assert pt.main(["done", "a", "--by", "0301"]) == 0
    assert [r["k"] for r in pt.read_log(root)] == ["done"]


def test_resend_does_not_cross_days(tmp_path):
    root = _root(tmp_path, T)
    pt.run_due(SUN, root)
    nxt = SUN + timedelta(days=1, hours=1)  # الاثنين: لا إعادةَ لمهمّة الأمس
    assert pt.run_due(nxt, root) == {}
