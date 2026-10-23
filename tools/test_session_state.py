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
