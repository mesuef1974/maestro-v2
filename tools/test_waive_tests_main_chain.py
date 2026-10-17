from __future__ import annotations

import subprocess

import ledger
import pytest


def git(repo, *a):
    return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def commit(repo, name, text, msg="c"):
    f = repo / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", msg)
    return git(repo, "rev-parse", "HEAD")


def merge_main(repo):
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-ff", "-m", "merge main", "main")
    return git(repo, "rev-parse", "HEAD")


def setup(tmp_path):
    """feature فيها عملٌ معتمَد؛ main تتقدّم بتغييرٍ؛ origin/main يحاكي main."""
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "a.txt", "1", "base")
    git(repo, "checkout", "-q", "-b", "feature")
    approved = commit(repo, "work.py", "x=1", "session work")
    git(repo, "checkout", "-q", "main")
    commit(repo, "main_only.txt", "m", "main change")
    git(repo, "update-ref", "refs/remotes/origin/main", "main")
    git(repo, "checkout", "-q", "feature")
    return repo, approved


def test_tests_fix_then_main_merge_passes(tmp_path):
    repo, approved = setup(tmp_path)
    commit(repo, "tests/test_x.py", "assert 1", "fix test")
    new = merge_main(repo)
    files = ledger.check_tests_main_chain(approved, new, str(repo))
    assert "tests/test_x.py" in files and "main_only.txt" in files


def test_main_merge_then_tests_fix_passes(tmp_path):
    repo, approved = setup(tmp_path)
    merge_main(repo)
    new = commit(repo, "tests/test_y.py", "assert 1", "fix test")
    assert "tests/test_y.py" in ledger.check_tests_main_chain(approved, new, str(repo))


def test_ui_commit_in_chain_drops_whole_chain(tmp_path):
    repo, approved = setup(tmp_path)
    commit(repo, "tests/test_x.py", "assert 1")
    commit(repo, "templates/page.html", "<p>")
    new = merge_main(repo)
    with pytest.raises(ledger.LedgerError, match="يُسقط السلسلة"):
        ledger.check_tests_main_chain(approved, new, str(repo))


@pytest.mark.parametrize("name", ["docs/governance/flow.md", "app/migrations/0001_x.py", "tests/test_security_gate.py", "CLAUDE.md"])
def test_governing_migration_guard_commits_drop_chain(tmp_path, name):
    repo, approved = setup(tmp_path)
    commit(repo, name, "x")
    new = merge_main(repo)
    with pytest.raises(ledger.LedgerError):
        ledger.check_tests_main_chain(approved, new, str(repo))


def test_session_code_commit_is_rejected(tmp_path):
    repo, approved = setup(tmp_path)
    commit(repo, "more.py", "y=2")
    with pytest.raises(ledger.LedgerError):
        ledger.check_tests_main_chain(approved, commit(repo, "tests/t.py", "1"), str(repo))


def test_chain_longer_than_max_rejected(tmp_path):
    repo, approved = setup(tmp_path)
    new = approved
    for i in range(ledger.CHAIN_MAX + 1):
        new = commit(repo, f"tests/test_{i}.py", str(i))
    with pytest.raises(ledger.LedgerError, match="الحدّ"):
        ledger.check_tests_main_chain(approved, new, str(repo))


def test_chain_at_max_passes(tmp_path):
    repo, approved = setup(tmp_path)
    new = approved
    for i in range(ledger.CHAIN_MAX):
        new = commit(repo, f"tests/test_{i}.py", str(i))
    assert len(ledger.check_tests_main_chain(approved, new, str(repo))) == ledger.CHAIN_MAX


def test_no_diff_and_unrelated_head_rejected(tmp_path):
    repo, approved = setup(tmp_path)
    with pytest.raises(ledger.LedgerError):
        ledger.check_tests_main_chain(approved, approved, str(repo))
    git(repo, "checkout", "-q", "main")
    other = commit(repo, "tests/o.py", "1")
    git(repo, "checkout", "-q", "feature")
    with pytest.raises(ledger.LedgerError):
        ledger.check_tests_main_chain(approved, other, str(repo))


def test_existing_checkers_unchanged_for_single_kinds(tmp_path):
    repo, approved = setup(tmp_path)
    new = merge_main(repo)
    assert ledger.check_main_merge(approved, new, str(repo)) == ["main_only.txt"]


def test_waive_head_records_chain_waiver(tmp_path):
    repo, approved = setup(tmp_path)
    commit(repo, "tests/test_x.py", "assert 1")
    new = merge_main(repo)
    path = tmp_path / "events.jsonl"
    ledger.append_event("created", "W-T-1", {"problem": "x"}, path)
    ledger.append_event("state", "W-T-1", {"state": "approved", "by": "0501", "head": approved[:8]}, path)
    ledger.waive_head("W-T-1", new[:8], "0501", "اختبار", path=path, kind="tests-main-chain", repo=str(repo))
    notes = ledger.reduce_state(ledger.load_events(path))["W-T-1"]["notes"]
    assert any("سلسلةُ إصلاح tests/" in n["text"] for n in notes)
    assert ledger.reduce_state(ledger.load_events(path))["W-T-1"]["approved_head"] == new[:8]
