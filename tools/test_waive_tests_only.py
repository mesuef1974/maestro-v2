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


def setup(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "app.py", "1")
    return repo, git(repo, "rev-parse", "HEAD")


def test_plain_test_fix_passes(tmp_path):
    repo, approved = setup(tmp_path)
    new = commit(repo, "tests/test_schedule_lab.py", "assert 1")
    assert ledger.check_tests_only(approved, new, str(repo)) == ["tests/test_schedule_lab.py"]


@pytest.mark.parametrize("name", [
    "tests/test_security_gate.py", "tests/test_every_route_is_guarded.py", "tests/test_permissions.py", "tests/test_erasure.py",
    "tests/test_parent_derived_rls.py", "tests/conftest.py", "tests/test_export_guards.py",
])
def test_guard_tests_are_rejected(tmp_path, name):
    repo, approved = setup(tmp_path)
    new = commit(repo, name, "assert 1")
    with pytest.raises(ledger.LedgerError):
        ledger.check_tests_only(approved, new, str(repo))


def test_code_outside_tests_is_rejected(tmp_path):
    repo, approved = setup(tmp_path)
    commit(repo, "tests/test_ok.py", "x")
    new = commit(repo, "app.py", "2")
    with pytest.raises(ledger.LedgerError):
        ledger.check_tests_only(approved, new, str(repo))


def test_waive_tests_only_is_0501_only_and_recorded(tmp_path):
    repo, approved = setup(tmp_path)
    new = commit(repo, "tests/test_a.py", "x")
    p = tmp_path / "ev.jsonl"
    iid = ledger.add_item("owner", "bug", "م", "أ", "ق", path=p, start="2026-10-02T10:00", priority="P2")
    ledger.append_event("state", iid, {"state": "approved", "by": "0501", "head": approved[:8]}, p)
    with pytest.raises(ledger.LedgerError):
        ledger.waive_head(iid, new[:8], "0405", "x", path=p, kind="tests-only", repo=str(repo))
    ledger.waive_head(iid, new[:8], "0501", "فشل CI", path=p, kind="tests-only", repo=str(repo))
    st = ledger.reduce_state(ledger.load_events(p))[iid]
    assert st["approved_head"] == new[:8] and "إصلاحُ اختباراتٍ فقط" in st["notes"][-1]["text"]


@pytest.mark.parametrize("name", [
    "tests/test_api_jwt_disabled.py", "tests/test_csrf_cookie_httponly.py", "tests/test_mfa_session.py", "tests/test_pii_masking.py",
    "tests/test_dlq_tenant_boundary.py", "tests/test_admin_school_scope.py", "tests/test_capability_grants.py",
    "tests/test_production_runtime_settings.py", "tests/test_ci_sharding.py", "tests/test_excel_formula_injection.py",
])
def test_0105_extended_guard_names_are_rejected(tmp_path, name):
    repo, approved = setup(tmp_path)
    new = commit(repo, name, "assert 1")
    with pytest.raises(ledger.LedgerError):
        ledger.check_tests_only(approved, new, str(repo))


def test_weakened_assertion_in_plain_test_is_rejected(tmp_path):
    repo, approved = setup(tmp_path)
    commit(repo, "tests/test_plain_thing.py", "def test_a():\n    assert 1 == 1\n    assert 2 == 2\n")
    approved2 = git(repo, "rev-parse", "HEAD")
    new = commit(repo, "tests/test_plain_thing.py", "def test_a():\n    assert 1 == 1\n")
    with pytest.raises(ledger.LedgerError):
        ledger.check_tests_only(approved2, new, str(repo))


def test_added_skip_is_rejected_but_assert_rewrite_passes(tmp_path):
    repo, _ = setup(tmp_path)
    commit(repo, "tests/test_plain_thing.py", "def test_a():\n    assert 1 == 1\n")
    base = git(repo, "rev-parse", "HEAD")
    skipped = commit(repo, "tests/test_plain_thing.py", "import pytest\n@pytest.mark.skip\ndef test_a():\n    assert 1 == 1\n")
    with pytest.raises(ledger.LedgerError):
        ledger.check_tests_only(base, skipped, str(repo))
    rewritten = commit(repo, "tests/test_plain_thing.py", "import pytest\ndef test_a():\n    assert 1 == 2 - 1\n")
    assert ledger.check_tests_only(skipped, rewritten, str(repo)) == ["tests/test_plain_thing.py"]
