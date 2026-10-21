"""بوّابتا «جاهزٌ للمعاينة» (W-20261020-013): تصادمٌ فعليٌّ مع main، وأمرُ approval_check ready."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import approval_check as ac
import ledger
import pytest
from test_waive_patch_id import commit, git


def repo_with_feature(tmp_path, clash: bool):
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "a.txt", "1", "base")
    git(repo, "checkout", "-q", "-b", "feature")
    commit(repo, "a.txt", "feature", "feature edit")
    git(repo, "checkout", "-q", "main")
    commit(repo, "a.txt" if clash else "b.txt", "main", "main edit")
    git(repo, "update-ref", "refs/remotes/origin/main", "main")
    git(repo, "checkout", "-q", "feature")
    return repo


def write_receipt(repo, ok=True):
    head = git(repo, "rev-parse", "--short=8", "HEAD")
    gitdir = Path(git(repo, "rev-parse", "--absolute-git-dir"))
    (gitdir / ledger.RECEIPT_NAME).write_text(json.dumps({"head": head, "ok": ok}), encoding="utf-8")


def test_merge_conflicts_detected(tmp_path):
    repo = repo_with_feature(tmp_path, clash=True)
    assert ledger._merge_conflicts(str(repo)) == ["a.txt"]


def test_no_conflict_when_files_differ(tmp_path):
    repo = repo_with_feature(tmp_path, clash=False)
    assert ledger._merge_conflicts(str(repo)) == []


def test_missing_origin_main_is_unknown_not_clash(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "a.txt", "1", "base")
    assert ledger._merge_conflicts(str(repo)) is None


def test_receipt_gate_warns_on_clash_in_shadow_and_refuses_enforced(tmp_path, monkeypatch):
    repo = repo_with_feature(tmp_path, clash=True)
    write_receipt(repo)
    monkeypatch.setenv("PREPUSH_RECEIPT_ENFORCE", "0")
    assert "تصادمٌ فعليٌّ" in ledger.check_prepush_receipt(str(repo))
    monkeypatch.setenv("PREPUSH_RECEIPT_ENFORCE", "1")
    with pytest.raises(ledger.LedgerError, match="تصادمٌ فعليٌّ"):
        ledger.check_prepush_receipt(str(repo))


def test_ready_problem_passes_with_receipt_and_clean_main(tmp_path):
    repo = repo_with_feature(tmp_path, clash=False)
    write_receipt(repo)
    assert ac.ready_problem(str(repo)) is None


def test_ready_problem_refuses_without_receipt(tmp_path):
    repo = repo_with_feature(tmp_path, clash=False)
    assert "make prepush" in ac.ready_problem(str(repo))


def test_ready_problem_refuses_after_head_changed(tmp_path):
    repo = repo_with_feature(tmp_path, clash=False)
    write_receipt(repo)
    commit(repo, "c.txt", "x", "after prepush")
    assert "make prepush" in ac.ready_problem(str(repo))


def test_ready_problem_refuses_failed_prepush(tmp_path):
    repo = repo_with_feature(tmp_path, clash=False)
    write_receipt(repo, ok=False)
    assert ac.ready_problem(str(repo))


def test_cli_ready_exit_codes(tmp_path):
    repo = repo_with_feature(tmp_path, clash=False)
    tool = Path(ac.__file__)
    run = lambda: subprocess.run([sys.executable, str(tool), "ready", "x", "--repo", str(repo)], capture_output=True, text=True, encoding="utf-8")
    assert run().returncode == 4
    write_receipt(repo)
    assert run().returncode == 0
