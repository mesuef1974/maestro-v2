"""اختباراتُ session_state: الحجم، الاستعادة المتطابقة، رفض النصّ الحرّ، غياب كلمات الاعتماد، UTF-8، idempotent."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import session_state as ss  # noqa: E402

DOHA = timezone(timedelta(hours=3))
NOW = datetime(2026, 10, 23, 20, 0, tzinfo=DOHA)


def _ev(ts, item, kind, data):
    return {"ts": ts, "id": item, "kind": kind, "data": data}


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "ledger").mkdir()
    events = [
        _ev("2026-10-23T10:00:00+03:00", "W-1", "created", {"source": "owner", "problem": "مسألةٌ", "held_by": "0108"}),
        _ev("2026-10-23T11:00:00+03:00", "W-1", "state", {"state": "approved", "by": "0108", "held_by": "0108"}),
        _ev("2026-10-23T12:00:00+03:00", "W-2", "created", {"source": "owner", "problem": "أخرى"}),
        _ev("2026-10-23T12:30:00+03:00", "W-2", "state", {"state": "merged", "by": "0108"}),
    ]
    (tmp_path / "ledger" / "events.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n", encoding="utf-8")
    pr = [{"kind": "add", "n": 1, "ts": "2026-10-23T09:00+03:00", "to": "0108", "about": "نصٌّ حرٌّ لا يدخل الحالة"},
          {"kind": "add", "n": 2, "ts": "2026-10-23T09:05+03:00", "to": "0108"},
          {"kind": "done", "n": 1, "ts": "2026-10-23T09:30+03:00"}]
    (tmp_path / "ledger" / "pending_replies.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in pr) + "\n", encoding="utf-8")
    (tmp_path / "msg_counter.json").write_text(json.dumps({"limit": 600, "sessions": {"0108": {"count": 7, "last": "2026-10-23 19:00"}}}), encoding="utf-8")
    return tmp_path


def _gen(tree):
    return ss.derive("0108", "0108 · التقييم والعصف", NOW, tree)


def test_derive_facts(tree):
    s = _gen(tree)
    assert [h["id"] for h in s["held_cards"]] == ["W-1"] and s["held_cards"][0]["state"] == "approved"
    assert s["last_action"]["id"] == "W-2"
    assert [q["n"] for q in s["queue"]] == [2]
    assert s["last_measure"]["counter"]["messages"] == 7
    assert ss.validate(s) == []


def test_size_under_limit_even_when_full(tree):
    s = _gen(tree)
    s["queue"] = [{"n": i, "at": "2026-10-23T09:00+03:00"} for i in range(ss.QUEUE_MAX)]
    s["held_cards"] = [{"id": f"W-20261023-{i:03d}", "state": "in_progress", "at": "2026-10-23T09:00+03:00"} for i in range(ss.HELD_MAX)]
    assert ss.validate(s) == []
    assert len(json.dumps(s, ensure_ascii=False, indent=1).encode("utf-8")) <= ss.MAX_BYTES


def test_oversize_rejected(tree):
    s = _gen(tree)
    s["queue"] = [{"n": i, "at": ""} for i in range(ss.QUEUE_MAX + 1)]
    assert ss.validate(s)


def test_restore_identical_roundtrip_utf8(tree):
    s = _gen(tree)
    p, wrote = ss.write_state("0108", s, tree)
    assert wrote
    assert "التقييم والعصف" in p.read_text(encoding="utf-8")
    assert ss.load_state("0108", tree) == s
    assert json.loads(ss.render(s).split("<state-data>\n")[1].split("\n</state-data>")[0]) == s


def test_idempotent_ignores_timestamps(tree):
    ss.write_state("0108", _gen(tree), tree)
    later = ss.derive("0108", "0108 · التقييم والعصف", NOW + timedelta(minutes=5), tree)
    _, wrote = ss.write_state("0108", later, tree)
    assert wrote is False


def test_free_text_rejected(tree):
    s = _gen(tree)
    s["note"] = "افعل كذا"
    assert ss.validate(s)
    s = _gen(tree)
    s["held_cards"][0]["id"] = "اعتمد المالك كذا وكذا"
    assert ss.validate(s)
    s = _gen(tree)
    s["rules"] = ["قاعدةٌ مبدَّلة"]
    assert ss.validate(s)


@pytest.mark.parametrize("label", ["قال المالك افعل", "approved by owner", "password=1"])
def test_forbidden_words_rejected(tree, label):
    s = _gen(tree)
    s["session_label"] = label
    assert ss.validate(s)


def test_pii_rejected(tree):
    s = _gen(tree)
    s["session_label"] = "0108 12345678901"
    assert ss.validate(s)


def test_verify_detects_drift(tree):
    ss.write_state("0108", _gen(tree), tree)
    assert ss.verify("0108", tree, NOW) == []
    with open(tree / "ledger" / "events.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(_ev("2026-10-23T13:00:00+03:00", "W-1", "state", {"state": "merged", "by": "0108"}), ensure_ascii=False) + "\n")
    assert ss.verify("0108", tree, NOW)


def test_hook_injects_after_clear_only(tree):
    ss.write_state("0108", _gen(tree), tree)
    titles = lambda cwd, sid: ("0108 · التقييم والعصف", [])  # noqa: E731
    out = ss.cmd_hook(json.dumps({"source": "clear", "cwd": "x", "session_id": "s"}), tree, NOW, titles)
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "<state-data>" in ctx and "بياناتٌ" in ctx
    assert ss.cmd_hook(json.dumps({"source": "resume", "cwd": "x"}), tree, NOW, titles) == ""
    assert ss.cmd_hook(json.dumps({"source": "clear"}), tree, NOW + timedelta(days=2), titles) == ""
    assert ss.cmd_hook("not json", tree, NOW, titles) == ""


def test_bad_session_number():
    with pytest.raises(ValueError):
        ss.state_path("../x")


def test_main_confirmations_points_to_main_folder():
    import session_state as s
    from pathlib import Path

    wt = Path("C:/x/proj/.claude/worktrees/abc")
    assert s.main_confirmations(wt) == Path("C:/x/proj/owner_confirmations.md")
    plain = Path("C:/x/proj")
    assert s.main_confirmations(plain) == plain / "owner_confirmations.md"


def test_hook_ambiguous_candidates_same_number(tree):
    ss.write_state("0108", _gen(tree), tree)
    hook = json.dumps({"source": "startup", "cwd": "x", "session_id": "new"})
    same = lambda c, i: (None, ["0108 · أ", "0108-ب · ب"])  # noqa: E731
    assert "<state-data>" in ss.cmd_hook(hook, tree, NOW, same)
    mixed = lambda c, i: (None, ["0108 · أ", "0102 · ب"])  # noqa: E731
    assert ss.cmd_hook(hook, tree, NOW, mixed) == ""


def test_focus_rejects_unknown_card_and_free_text(tree):
    with pytest.raises(ValueError):
        ss.set_focus("0108", "W-9", 1, root=tree)
    with pytest.raises(ValueError):
        ss.set_focus("0108", "نص حر", 1, root=tree)
    ss.set_focus("0108", "W-1", 2, root=tree)
    w = _gen(tree)["work"]
    assert w["focus"]["card"] == "W-1" and w["focus"]["step"] == 2
    assert ss.validate(_gen(tree)) == []


def test_work_recent_comes_from_ledger(tree):
    rec = _gen(tree)["work"]["recent"]
    assert [r["id"] for r in rec] == ["W-2", "W-1"] and ss.validate(_gen(tree)) == []


def test_git_info_paths_not_truncated(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "i"], check=True)
    (tmp_path / "decisions.md").write_text("x", encoding="utf-8")
    g = ss._git_info(str(tmp_path))
    assert g["dirty"] == 1 and g["paths"] == ["decisions.md"]


def test_inferred_focus_marked_and_overridden_by_declared(tree):
    f = _gen(tree)["work"]["focus"]
    assert f == {"card": "W-2", "step": 0, "at": "2026-10-23T12:30:00+03:00", "inferred": True}
    assert ss.validate(_gen(tree)) == []
    ss.set_focus("0108", "W-1", 3, root=tree)
    f = _gen(tree)["work"]["focus"]
    assert f["card"] == "W-1" and "inferred" not in f


def test_inferred_flag_cannot_be_false_or_extra(tree):
    s = _gen(tree)
    s["work"]["focus"]["inferred"] = False
    assert ss.validate(s) != []
    s["work"]["focus"] = {"card": "W-1", "step": 1, "at": "2026-10-23T12:30:00+03:00", "extra": True}
    assert ss.validate(s) != []


def test_guard_refuses_without_declared_focus(tree):
    errs = ss.focus_guard("0108", tree)
    assert errs and "focus" in errs[0]


def test_guard_refuses_stale_and_passes_when_fresh(tree):
    fp = ss.focus_path("0108", tree)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps({"card": "W-1", "step": 1, "at": "2026-10-23T12:00:00+03:00"}), encoding="utf-8")
    assert "أقدمُ" in ss.focus_guard("0108", tree)[0]  # آخر حدثٍ للجلسة 12:30
    ss.set_focus("0108", "W-1", 2, root=tree)
    assert ss.focus_guard("0108", tree) == []


def test_guard_skips_session_without_held_card(tree):
    assert ss.focus_guard("0999", tree) == []


def test_prepare_clear_blocked_by_guard_unless_owner_override(tree, monkeypatch, capsys):
    monkeypatch.setattr(ss, "ROOT", tree)
    monkeypatch.setattr(ss, "check_owner_quote", lambda q: "سطر 1" if q in ("مسح", "تجاوز") else (_ for _ in ()).throw(ValueError("لا")))
    assert ss.main(["prepare-clear", "0108", "--owner-quote", "مسح"]) == 5
    assert not ss.state_path("0108", tree).exists()  # الرفضُ قبل أي كتابة
    assert ss.main(["prepare-clear", "0108", "--owner-quote", "مسح", "--skip-guard-quote", "مزيّف"]) == 3
    assert ss.main(["prepare-clear", "0108", "--owner-quote", "مسح", "--skip-guard-quote", "تجاوز"]) == 7  # الواجباتُ غيرُ مسجَّلة
    assert not ss.state_path("0108", tree).exists()
    ss.set_duties("0108", none=True, root=tree, now=NOW)
    assert ss.main(["prepare-clear", "0108", "--owner-quote", "مسح", "--skip-guard-quote", "تجاوز"]) == 0
    assert ss.state_path("0108", tree).exists()
    ss.set_focus("0108", "W-1", 1, root=tree)
    assert ss.main(["prepare-clear", "0108", "--owner-quote", "مسح"]) == 0
    assert ss.main(["guard", "0108"]) == 0


# ---- W-20261024-005: علامةُ المسح المعلَّق لكلّ شجرة ----
TREE = "D:/shschool_mvp/.claude/worktrees/abc"
HOOK = json.dumps({"source": "clear", "cwd": TREE, "session_id": "new"})


def UNKNOWN(cwd, sid):  # عنوانٌ مجهول ولا مرشّحين: لا يُحسم إلا بالعلامة
    return None, []


def _ready(tree, num="0108"):
    ss.set_duties(num, none=True, root=tree, now=NOW)
    ss.write_state(num, ss.derive(num, num, NOW, tree), tree)


def _ctx(out):
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


def test_pending_resolves_when_title_unknown_and_is_single_use(tree):
    _ready(tree)
    ss.write_pending("0108", TREE, tree, NOW)
    ctx = _ctx(ss.cmd_hook(HOOK, tree, NOW, UNKNOWN))
    assert "مستنتج من ملف معلَّق" in ctx and "<state-data>" in ctx
    assert ss.cmd_hook(HOOK, tree, NOW, UNKNOWN) == ""  # استُهلكت
    assert not list((tree / "handover_notes").glob("pending_clear_*"))


def test_pending_expired_or_other_tree_or_two_sessions_gives_empty(tree):
    _ready(tree)
    ss.write_pending("0108", TREE, tree, NOW - timedelta(seconds=ss.PENDING_TTL_S + 5))
    assert ss.cmd_hook(HOOK, tree, NOW, UNKNOWN) == ""  # منتهية
    ss.write_pending("0108", "D:/other/tree", tree, NOW)
    assert ss.cmd_hook(HOOK, tree, NOW, UNKNOWN) == ""  # شجرةٌ أخرى
    ss.write_pending("0108", TREE, tree, NOW)
    _ready(tree, "0109")
    ss.write_pending("0109", TREE, tree, NOW)
    assert ss.cmd_hook(HOOK, tree, NOW, UNKNOWN) == ""  # علامتان صالحتان: لا حسم


def test_pending_ignored_when_state_stale_or_invalid(tree):
    _ready(tree)
    later = NOW + timedelta(days=2)
    ss.write_pending("0108", TREE, tree, later)
    assert ss.cmd_hook(HOOK, tree, later, UNKNOWN) == ""  # الحالةُ أقدمُ من 24 ساعة
    p = ss.state_path("0108", tree)
    st = json.loads(p.read_text(encoding="utf-8"))
    st["queue"] = [{"n": "x"}]
    p.write_text(json.dumps(st), encoding="utf-8")
    assert ss.cmd_hook(HOOK, tree, NOW, UNKNOWN) == ""


def test_title_wins_over_pending_and_pending_is_consumed(tree):
    _ready(tree)
    ss.write_pending("0108", TREE, tree, NOW)
    ctx = _ctx(ss.cmd_hook(HOOK, tree, NOW, lambda c, i: ("0108 · س", [])))
    assert "مستنتج" not in ctx
    assert not list((tree / "handover_notes").glob("pending_clear_*"))


def test_injection_logged_in_ledger_without_staling_focus(tree):
    _ready(tree)
    ss.set_focus("0108", "W-1", 1, root=tree)
    ss.write_pending("0108", TREE, tree, NOW)
    assert ss.cmd_hook(HOOK, tree, NOW, UNKNOWN)
    evs = [json.loads(x) for x in (tree / "ledger" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(e["kind"] == "note" and ss.INJECT_MARK in e["data"]["text"] for e in evs)
    assert ss.focus_guard("0108", tree) == []  # ملاحظةُ الحقن لا تُبطل focus


# ---- W-20261024-006: الواجباتُ الدائمة ----
def test_duties_register_validate_and_render(tree):
    assert ss.duties_guard("0108", tree)  # غيرُ مسجَّلة = رفض
    ss.set_duties("0108", add={"id": "poll-pr", "every_min": 30, "what": "فحص طلبات الدمج المفتوحة"}, root=tree, now=NOW)
    assert ss.duties_guard("0108", tree) == []
    s = _gen(tree)
    assert s["duties"][0]["id"] == "poll-pr" and ss.validate(s) == []
    assert "فحص طلبات الدمج" in ss.render(s) and "30" in ss.render(s)
    ss.set_duties("0108", add={"id": "poll-pr", "every_min": 60, "what": "فحص أبطأ"}, root=tree, now=NOW)  # استبدالٌ بالمعرّف
    assert [d["every_min"] for d in _gen(tree)["duties"]] == [60]


def test_duties_reject_bad_input(tree):
    for bad in ({"id": "x", "every_min": 5000, "what": "ok"}, {"id": "x", "every_min": 5, "what": "اعتمد المالك كذا"},
                {"id": "x", "every_min": True, "what": "ok"}, {"id": "نص حر", "every_min": 5, "what": "ok"}):
        with pytest.raises(ValueError):
            ss.set_duties("0108", add=bad, root=tree, now=NOW)
    for i in range(ss.DUTIES_MAX):
        ss.set_duties("0108", add={"id": f"d{i}", "every_min": 0, "what": "ok"}, root=tree, now=NOW)
    with pytest.raises(ValueError):
        ss.set_duties("0108", add={"id": "extra", "every_min": 0, "what": "ok"}, root=tree, now=NOW)


def test_duties_none_declares_empty_and_clear_removes(tree):
    ss.set_duties("0108", none=True, root=tree, now=NOW)
    assert ss.duties_guard("0108", tree) == [] and _gen(tree)["duties"] == []
    ss.set_duties("0108", clear=True, root=tree)
    assert ss.duties_guard("0108", tree)


def test_duties_cli_needs_owner_quote(tree, monkeypatch):
    monkeypatch.setattr(ss, "ROOT", tree)
    monkeypatch.setattr(ss, "check_owner_quote", lambda q: "سطر" if q == "أمر" else (_ for _ in ()).throw(ValueError("لا")))
    assert ss.main(["duties", "0108", "--add", "d1", "--every", "10", "--what", "واجب", "--owner-quote", "مزيّف"]) == 3
    assert ss.main(["duties", "0108", "--add", "d1", "--every", "10", "--what", "واجب", "--owner-quote", "أمر"]) == 0
    assert ss.load_duties("0108", tree)["items"][0]["id"] == "d1"


# ---- clear_all والسيناريو الحاسم ----
def test_clear_all_ready_list_and_shared_tree(tree):
    ss.set_focus("0108", "W-1", 1, root=tree)
    ss.set_duties("0108", none=True, root=tree, now=NOW)
    ss.set_duties("0109", none=True, root=tree, now=NOW)
    rows = ss.clear_all([{"num": "0108", "title": "0108 · التقييم", "tree": TREE},
                         {"num": "0109", "title": "0109 · ب", "tree": TREE},
                         {"num": "0110", "title": "0110 · ج", "tree": "D:/x"}], root=tree, now=NOW)
    by = {r["num"]: r for r in rows}
    assert by["0108"]["ok"] and by["0108"]["pending"]
    assert not by["0109"]["ok"] and "مشتركة" in by["0109"]["reasons"][0]
    assert not by["0110"]["ok"] and "واجبات" in by["0110"]["reasons"][0]
    assert len(list((tree / "handover_notes").glob("pending_clear_*"))) == 1


def test_clear_all_blocked_by_guard_and_skip(tree):
    ss.set_duties("0108", none=True, root=tree, now=NOW)
    r = ss.clear_all([{"num": "0108", "title": "0108", "tree": TREE}], root=tree, now=NOW)[0]
    assert not r["ok"] and "focus" in r["reasons"][0]
    r = ss.clear_all([{"num": "0108", "title": "0108", "tree": TREE}], skip_guard=True, root=tree, now=NOW)[0]
    assert r["ok"], r


def test_live_sessions_skips_archived_and_dedups(tmp_path):
    d = tmp_path / "a" / "b"
    d.mkdir(parents=True)
    rows = [("local_1", {"title": "0201 · ق", "cwd": "D:/m", "isArchived": False, "lastActivityAt": 1}),
            ("local_2", {"title": "0201 · ق", "cwd": "D:/new", "isArchived": False, "lastActivityAt": 9}),
            ("local_3", {"title": "0202 · ر", "cwd": "D:/m", "isArchived": True}),
            ("local_4", {"title": "بلا رقم", "cwd": "D:/m"})]
    for n, v in rows:
        (d / f"{n}.json").write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
    out = ss.live_sessions(tmp_path)
    assert [(x["num"], x["tree"]) for x in out] == [("0201", "D:/new")]


def test_decisive_clear_again_injects_identity_and_duties_by_itself(tree):
    """0201 يُمسح مرةً ثانية: الخطّافُ يحقن هويّتَه وواجباتِه وحدَه بلا عنوانٍ معروف."""
    ss.set_focus("0108", "W-1", 1, root=tree)
    ss.set_duties("0108", add={"id": "poll-ci", "every_min": 20, "what": "راقب حالة CI"}, root=tree, now=NOW)
    rows = ss.clear_all([{"num": "0108", "title": "0108 · التقييم", "tree": TREE}], root=tree, now=NOW)
    assert rows[0]["ok"], rows
    ctx = _ctx(ss.cmd_hook(HOOK, tree, NOW, UNKNOWN))
    assert '"role"' in ctx or "0108" in ctx
    assert "poll-ci" in ctx and "راقب حالة CI" in ctx
    # مسحٌ ثانٍ بعد الحقن: يمرّ الحارسُ (ملاحظةُ الحقن لا تُبطل focus) وتعود الدورةُ كاملة
    t2 = NOW + timedelta(minutes=1)
    rows = ss.clear_all([{"num": "0108", "title": "0108 · التقييم", "tree": TREE}], root=tree, now=t2)
    assert rows[0]["ok"], rows
    assert "poll-ci" in _ctx(ss.cmd_hook(HOOK, tree, t2, UNKNOWN))
