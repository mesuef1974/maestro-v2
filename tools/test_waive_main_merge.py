from __future__ import annotations

import subprocess

import ledger
import pytest


def git(repo, *a):
    return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def commit(repo, name, text, msg):
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", msg)
    return git(repo, "rev-parse", "HEAD")


def setup(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    base = commit(repo, "a.txt", "1", "base")
    git(repo, "checkout", "-q", "-b", "feature")
    approved = commit(repo, "work.py", "x=1", "session work")
    git(repo, "checkout", "-q", "main")
    commit(repo, "main_only.txt", "m", "main change")
    # الأبُ الثاني يجب أن يكون سلفاً لـorigin/main (تشديد check_main_merge): نُحاكي البعيدَ بمرجعٍ محلّيّ
    git(repo, "update-ref", "refs/remotes/origin/main", "main")
    return repo, approved


def merge(repo):
    git(repo, "checkout", "-q", "feature")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-ff", "-m", "merge main", "main")
    return git(repo, "rev-parse", "HEAD")


def test_clean_main_merge_passes(tmp_path):
    repo, approved = setup(tmp_path)
    new = merge(repo)
    assert ledger.check_main_merge(approved, new, str(repo)) == ["main_only.txt"]


def test_session_code_after_approval_is_rejected(tmp_path):
    repo, approved = setup(tmp_path)
    git(repo, "checkout", "-q", "feature")
    commit(repo, "more.py", "y=2", "new session code")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-ff", "-m", "merge main", "main")
    new = git(repo, "rev-parse", "HEAD")
    with pytest.raises(ledger.LedgerError):
        ledger.check_main_merge(approved, new, str(repo))


def test_non_merge_commit_is_rejected(tmp_path):
    repo, approved = setup(tmp_path)
    git(repo, "checkout", "-q", "feature")
    new = commit(repo, "w2.py", "z", "plain commit")
    with pytest.raises(ledger.LedgerError):
        ledger.check_main_merge(approved, new, str(repo))


def test_waive_head_main_merge_only_for_0501_and_records_reason(tmp_path):
    repo, approved = setup(tmp_path)
    new = merge(repo)
    p = tmp_path / "ev.jsonl"
    iid = ledger.add_item("owner", "bug", "م", "أ", "ق", path=p, start="2026-10-02T10:00", priority="P2")
    ledger.append_event("state", iid, {"state": "approved", "by": "0501", "head": approved[:8]}, p)
    with pytest.raises(ledger.LedgerError):
        ledger.waive_head(iid, new[:8], "0405", "x", path=p, kind="main-merge", repo=str(repo))
    ledger.waive_head(iid, new[:8], "0501", "تحقّقتُ", path=p, kind="main-merge", repo=str(repo))
    st = ledger.reduce_state(ledger.load_events(p))[iid]
    assert st["approved_head"] == new[:8] and "دمجُ main فقط" in st["notes"][-1]["text"]
