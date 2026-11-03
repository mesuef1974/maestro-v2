"""W-20261101-012 (D-510م): سجلّ الجلسة قبل المسح — رفض الدور والمسح بسجلٍّ قديم، وتجربةُ 0501/0601 وحدَها."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import inbox  # noqa: E402
import session_record as sr  # noqa: E402
import session_state as ss  # noqa: E402


def git(repo, *a):
    return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()  # noqa: S603,S607


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "root"
    (root / "ledger").mkdir(parents=True)
    ev = [{"id": "W-1", "ts": "2026-11-02T10:00:00+03:00", "kind": "created", "data": {"source": "owner", "problem": "م", "held_by": "0501"}},
          {"id": "W-1", "ts": "2026-11-02T10:05:00+03:00", "kind": "state", "data": {"state": "approved", "by": "0501", "held_by": "0501"}}]
    (root / "ledger" / "events.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in ev) + "\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "a")
    return root, str(repo)


def test_no_record_is_a_violation_only_for_trial_sessions(env):
    root, repo = env
    assert sr.stop_block("0501", repo, root) != ""
    assert sr.stop_block("0108", repo, root) == ""  # خارج التجربة: لا رفض


def test_fresh_record_passes_and_head_change_without_update_is_refused(env):
    root, repo = env
    sr.update("0501", {"next_step": "افحص W-1"}, repo, root)
    assert sr.check("0501", repo, root) == []
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "b")
    assert any("رأسُ git" in x for x in sr.check("0501", repo, root))
    assert "session_record.py set 0501" in sr.stop_block("0501", repo, root)
    sr.update("0501", {"next_step": "بعد الإيداع"}, repo, root)
    assert sr.check("0501", repo, root) == []


def test_card_state_change_and_new_message_are_refused(env):
    root, repo = env
    sr.update("0501", {"next_step": "x"}, repo, root)
    inbox.send("0501", "0101", "طلب جديد", root)
    assert any("وصلت رسالةٌ" in x for x in sr.check("0501", repo, root))
    sr.update("0501", {}, repo, root)
    ev = json.loads((root / "ledger" / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    ev2 = {"id": "W-1", "ts": "2026-11-02T11:00:00+03:00", "kind": "state", "data": {"state": "pushed", "by": "0501", "held_by": "0501"}}
    with (root / "ledger" / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev2, ensure_ascii=False) + "\n")
    assert ev["id"] == "W-1"
    assert any("حالةُ بطاقة" in x for x in sr.check("0501", repo, root))


def test_clear_refused_when_record_older_than_last_action(env):
    root, repo = env
    old = sr._now() - timedelta(days=30)
    sr.update("0501", {"next_step": "قديم"}, repo, root, now=old)
    issues = sr.clear_issues("0501", repo, root)
    assert any("أقدمُ من آخر فعل" in x for x in issues)
    sr.update("0501", {"next_step": "جديد"}, repo, root)
    assert sr.clear_issues("0501", repo, root) == []
    assert sr.clear_issues("0108", repo, root) == []


def test_lists_are_appended_deduped_capped_and_done_promise_removed(env):
    root, repo = env
    sr.update("0601", {"promises": ["أبلغ 0101 بالدمج"], "tried_failed": ["push رُفض"]}, repo, root)
    rec = sr.update("0601", {"promises": ["أبلغ 0101 بالدمج", "نظّف الفرع"], "tried_failed": ["push رُفض"]}, repo, root)
    assert rec["promises"] == ["أبلغ 0101 بالدمج", "نظّف الفرع"] and rec["tried_failed"] == ["push رُفض"]
    rec = sr.update("0601", {"done_promises": ["نظّف"]}, repo, root)
    assert rec["promises"] == ["أبلغ 0101 بالدمج"]
    for i in range(30):
        rec = sr.update("0601", {"decisions": [f"قرار {i}"]}, repo, root)
    assert len(rec["decisions"]) == sr.LIST_MAX and rec["decisions"][-1] == "قرار 29"
    assert set(rec) >= {"next_step", "tried_failed", "decisions", "promises", "work_set", "summary"}


def test_stop_hook_blocks_trial_session_and_logs_refusal_and_report(env, monkeypatch):
    root, repo = env
    monkeypatch.setattr(ss, "main_root", lambda r=None: root)
    hook = json.dumps({"cwd": repo, "session_id": "s"})
    titles = lambda c, i: ("0501 · الجودة", [])  # noqa: E731
    inbox.beat("0501", root)
    out = ss.cmd_stop_hook(hook, root, titles)
    assert json.loads(out)["decision"] == "block" and "سجلّ" in json.loads(out)["reason"]
    active = json.dumps({"cwd": repo, "session_id": "s", "stop_hook_active": True})
    assert ss.cmd_stop_hook(active, root, titles) == ""  # لا حلقةَ منع
    assert "رفضُ دور 1" in sr.report(root)
    sr.update("0501", {"next_step": "ok"}, repo, root)
    assert ss.cmd_stop_hook(hook, root, titles) == ""
