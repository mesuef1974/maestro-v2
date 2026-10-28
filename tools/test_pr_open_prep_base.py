"""اختباراتُ فحوص ما قبل «جاهز» في pr_open_prep (W-20261014-012): الأساس المدفوع والحديث وإصدار mypy، قراءةٌ فقط."""

from __future__ import annotations

import subprocess

import pr_open_prep as prep
import pytest


def git(repo, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=repo, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout.strip()


def commit(repo, name, text, msg="c"):
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-qm", msg)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    work = tmp_path / "w"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    commit(work, "a.txt", "1", "base")
    commit(work, "shared.py", "s=1", "shared")
    git(work, "branch", "-M", "main")
    git(work, "push", "-q", "origin", "main")
    git(work, "fetch", "-q", "origin")
    return work


def test_pushed_base_passes(repo):
    git(repo, "checkout", "-q", "-b", "feat")
    commit(repo, "f.py", "x")
    assert prep.check_base_pushed(str(repo)) == []


def test_unpushed_local_base_branch_is_rejected(repo):
    git(repo, "checkout", "-q", "-b", "parent")
    commit(repo, "p.py", "p")
    git(repo, "checkout", "-q", "-b", "child")
    commit(repo, "c.py", "c")
    msgs = prep.check_base_pushed(str(repo))
    assert len(msgs) == 1 and "parent" in msgs[0] and "لم يُدفع" in msgs[0]


def test_pushed_parent_branch_passes(repo):
    git(repo, "checkout", "-q", "-b", "parent")
    commit(repo, "p.py", "p")
    git(repo, "push", "-q", "origin", "parent")
    git(repo, "fetch", "-q", "origin")
    git(repo, "checkout", "-q", "-b", "child")
    commit(repo, "c.py", "c")
    assert prep.check_base_pushed(str(repo)) == []


def test_branch_from_main_passes_even_with_main_alias(repo):
    git(repo, "checkout", "-q", "-b", "feat")
    commit(repo, "f.py", "x")
    assert prep.check_base_pushed(str(repo), "origin/main") == []


def test_stale_base_with_overlap_is_rejected(repo):
    git(repo, "checkout", "-q", "-b", "feat")
    commit(repo, "shared.py", "s=2", "mine")
    git(repo, "checkout", "-q", "main")
    commit(repo, "shared.py", "s=1\nt=1", "main edit")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "fetch", "-q", "origin")
    git(repo, "checkout", "-q", "feat")
    assert prep.check_base_fresh(str(repo)) == ["shared.py"]


def test_stale_base_without_overlap_passes(repo):
    git(repo, "checkout", "-q", "-b", "feat")
    commit(repo, "mine.py", "m")
    git(repo, "checkout", "-q", "main")
    commit(repo, "other.py", "o")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "fetch", "-q", "origin")
    git(repo, "checkout", "-q", "feat")
    assert prep.check_base_fresh(str(repo)) == []


def test_mypy_version_mismatch_names_both_versions(tmp_path):
    (tmp_path / "requirements-mypy.txt").write_text("mypy==1.10.0\ndjango-stubs==5.0.2\n", encoding="utf-8")
    msgs = prep.check_mypy_version(str(tmp_path), installed={"mypy": "2.1.0", "django-stubs": "5.0.2"}.get)
    assert any("mypy" in m and "1.10.0" in m and "2.1.0" in m for m in msgs)
    assert not any("django-stubs:" in m for m in msgs)
    assert any("requirements-mypy.txt" in m for m in msgs)


def test_missing_checker_is_a_failure(tmp_path):
    (tmp_path / "requirements-mypy.txt").write_text("mypy==1.10.0\n", encoding="utf-8")
    msgs = prep.check_mypy_version(str(tmp_path), installed=lambda n: None)
    assert any("غائب" in m for m in msgs)


def test_matching_versions_pass(tmp_path):
    (tmp_path / "requirements-mypy.txt").write_text("mypy==1.10.0\n", encoding="utf-8")
    assert prep.check_mypy_version(str(tmp_path), installed=lambda n: "1.10.0") == []


def test_preflight_exit_codes_and_no_writes(repo, monkeypatch, capsys):
    (repo / "requirements-mypy.txt").write_text("mypy==1.10.0\n", encoding="utf-8")
    monkeypatch.setattr(prep, "check_mypy_version", lambda r: [])
    git(repo, "checkout", "-q", "-b", "feat")
    commit(repo, "f.py", "x")
    before = git(repo, "status", "--porcelain")
    assert prep.preflight(str(repo), "origin/main") == 0
    monkeypatch.setattr(prep, "check_mypy_version", lambda r: ["mypy: تحكم البوّابةُ 1.10.0 والمثبَّتُ عندك 2.1.0"])
    assert prep.preflight(str(repo), "origin/main") == 6
    assert "2.1.0" in capsys.readouterr().out
    assert git(repo, "status", "--porcelain") == before


def test_a_governance_repo_without_a_mypy_gate_is_not_a_preflight_failure(tmp_path):
    """(10-29) maestro-v2 بلا requirements-mypy.txt ولا بوّابة mypy: كان الفحصُ المسبق يفشل فيُعفى يدويّاً بطاقةً بطاقة."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "ledger.py").write_text("", encoding="utf-8")
    assert prep.check_mypy_version(str(tmp_path), installed=lambda n: None) == []
