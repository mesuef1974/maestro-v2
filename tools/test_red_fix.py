from __future__ import annotations

import ledger
import pytest
from test_waive_tests_only import commit, setup


def test_pushed_plain_fix_passes(tmp_path):
    repo, approved = setup(tmp_path)
    new = commit(repo, "app.py", "2")
    assert ledger.check_red_fix({"state": "pushed"}, approved, new, str(repo)) == ["app.py"]


def test_unpushed_rejected(tmp_path):
    repo, approved = setup(tmp_path)
    new = commit(repo, "app.py", "2")
    with pytest.raises(ledger.LedgerError):
        ledger.check_red_fix({"state": "approved"}, approved, new, str(repo))


@pytest.mark.parametrize("name", ["templates/a.html", "static/css/a.css", "static/js/a.js", "core/migrations/0009_x.py", "core/permissions.py", "CLAUDE.md"])
def test_sensitive_paths_are_accepted_under_d506(tmp_path, name):
    """D-506م: رأسُ إصلاح CI/lint يعتمده 0101 بلا عودة لأي صنفٍ مدفوع."""
    repo, approved = setup(tmp_path)
    new = commit(repo, name, "x")
    assert ledger.check_red_fix({"state": "pushed"}, approved, new, str(repo)) == [name]
