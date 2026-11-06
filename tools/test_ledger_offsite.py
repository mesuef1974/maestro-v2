# ruff: noqa: S603, S607
"""النسخة الخارجية على مستودع محلّيّ عارٍ بدل GitHub."""
import json
import os
import shutil
import subprocess

import pytest

import ledger_offsite as lo


@pytest.fixture
def env(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    home = tmp_path / "home"
    root = tmp_path / "src"
    (root / "ledger").mkdir(parents=True)
    (root / "requests").mkdir()
    (root / "archive_local" / "fail_diffs").mkdir(parents=True)
    (root / "ledger" / "events.jsonl").write_text('{"id":"W-1"}\n', encoding="utf-8")
    (root / "requests" / "web-1.done").write_text("منتهٍ\n", encoding="utf-8")
    (root / "requests" / "web-2.md").write_text("لم يُنفَّذ\n", encoding="utf-8")
    (root / "archive_local" / "fail_diffs" / "W-1.diff").write_text("+x\n", encoding="utf-8")
    monkeypatch.setattr(lo, "REMOTE", str(remote))
    monkeypatch.setattr(lo, "HOME", home)
    monkeypatch.setattr(lo, "CLONE", home / "clone")
    monkeypatch.setattr(lo, "STATE", home / "state.json")
    refs = []
    monkeypatch.setattr(lo, "refer", refs.append)
    return root, remote, refs


def show(remote, name):
    return subprocess.run(["git", "--git-dir", str(remote), "show", f"{lo.BRANCH}:{name}"], capture_output=True, text=True,
                          encoding="utf-8")


def commits(remote):
    out = subprocess.run(["git", "--git-dir", str(remote), "rev-list", "--count", lo.BRANCH], capture_output=True, text=True)
    return int(out.stdout)


def test_first_run_pushes_finished_work_only(env):
    root, remote, _ = env
    assert lo.run(root) == 0
    assert show(remote, "ledger/events.jsonl").stdout == '{"id":"W-1"}\n'
    assert show(remote, "requests/web-1.done").returncode == 0
    assert show(remote, "requests/web-2.md").returncode != 0
    assert show(remote, "fail_diffs/W-1.diff").returncode == 0


def test_manifest_matches_what_was_pushed(env):
    root, remote, _ = env
    lo.run(root)
    table = json.loads(show(remote, "MANIFEST.json").stdout)
    assert table["files"]["ledger/events.jsonl"]["sha256"] == lo.read_state()["ledger_sha256"]


def test_second_run_without_change_adds_no_commit(env):
    root, remote, _ = env
    lo.run(root)
    lo.run(root)
    assert commits(remote) == 1


def test_changed_ledger_adds_one_commit_on_a_fresh_clone(env):
    root, remote, _ = env
    lo.run(root)
    shutil.rmtree(lo.CLONE, onerror=lambda f, p, _e: (os.chmod(p, 0o700), f(p)))
    (root / "ledger" / "events.jsonl").write_text('{"id":"W-1"}\n{"id":"W-2"}\n', encoding="utf-8")
    assert lo.run(root) == 0
    assert commits(remote) == 2


def test_a_secret_stops_the_push_and_reaches_the_owner(env):
    root, remote, refs = env
    (root / "requests" / "web-3.done").write_text("pass" + "word = 'abcdefgh12345'\n", encoding="utf-8")  # مقسومة كي لا يوقف فحصُ الدفع هذا الملف
    assert lo.run(root) == 2
    assert subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "--verify", "-q", lo.BRANCH]).returncode != 0
    assert len(refs) == 1 and "abcdefgh12345" not in refs[0] and "web-3.done" in refs[0]
    assert not lo.due()  # لا يتكرّر السطر في الطابور كلّ دورة


def test_once_a_day(env):
    root, _remote, _ = env
    assert lo.due()
    lo.run(root)
    assert not lo.due()


def test_failure_is_recorded_not_raised(env, monkeypatch):
    monkeypatch.setattr(lo, "run", lambda: (_ for _ in ()).throw(RuntimeError("no network")))
    assert lo.main([]) == 1
    assert lo.read_state()["ok"] is False and not lo.due()
    monkeypatch.setattr(lo, "RETRY_S", 0)
    assert lo.due()
