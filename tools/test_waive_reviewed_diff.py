"""اختباراتُ استثناء reviewed-diff (أمر المالك 2026-10-20): يمرّ بعد فحص 0101 لعملٍ لم يتّسع ولم يمسّ الحاكم/الهجرات/الأمن."""

from __future__ import annotations

import ledger
import pytest
from test_waive_patch_id import commit, git, merge_main, setup


def test_requires_named_reviewer(tmp_path):
    repo, approved = setup(tmp_path)
    new = merge_main(repo)
    with pytest.raises(ledger.LedgerError, match="reviewed-by"):
        ledger.check_reviewed_diff(approved, new, None, str(repo))
    with pytest.raises(ledger.LedgerError, match="reviewed-by"):
        ledger.check_reviewed_diff(approved, new, "0405", str(repo))


def test_ci_fix_inside_same_files_passes(tmp_path):
    repo, approved = setup(tmp_path)
    git(repo, "checkout", "-q", "feature")
    commit(repo, "work.py", "x=2", "ci fix")
    new = merge_main(repo)
    assert ledger.check_reviewed_diff(approved, new, "0101", str(repo)) == ["work.py"]


def test_wider_scope_rejected(tmp_path):
    repo, approved = setup(tmp_path)
    git(repo, "checkout", "-q", "feature")
    commit(repo, "other.py", "y=1", "extra")
    new = merge_main(repo)
    with pytest.raises(ledger.LedgerError, match="نطاق"):
        ledger.check_reviewed_diff(approved, new, "0101", str(repo))


@pytest.mark.parametrize("name", ["core/permissions.py", "ops/migrations/0001_x.py", "CLAUDE.md", ".claude/rules/a.md"])
def test_sensitive_rejected(tmp_path, name):
    repo, approved = setup(tmp_path, work=(name, "x"))
    new = merge_main(repo)
    with pytest.raises(ledger.LedgerError, match="تُعرض على المالك"):
        ledger.check_reviewed_diff(approved, new, "0101", str(repo))


def _cli(monkeypatch, tmp_path, repo, approved, new, reviewed_by):
    """يستدعي main() بوسيطات سطر الأوامر الحقيقيّة على دفترٍ مؤقّت لبطاقةٍ معتمَدةٍ بالرأس approved."""
    path = str(tmp_path / "e.jsonl")
    cid = ledger.add_item("owner", "tool", "سكربت", "أ", "ق", start="2026-10-20T09:00", priority="P2", path=path)
    ledger.append_event("state", cid, {"state": "approved", "by": "0501", "head": approved[:8]}, path)
    monkeypatch.setenv("LEDGER_PATH", path)
    argv = ["ledger.py", "waive-head", cid, "--head", new[:8], "--by", "0501", "--reason", "فحص", "--kind", "reviewed-diff", "--repo", str(repo)]
    if reviewed_by:
        argv += ["--reviewed-by", reviewed_by]
    monkeypatch.setattr("sys.argv", argv)
    return path, cid


def test_cli_waive_head_reviewed_diff_records_note(tmp_path, monkeypatch, capsys):
    repo, approved = setup(tmp_path)
    git(repo, "checkout", "-q", "feature")
    commit(repo, "work.py", "x=2", "ci fix")
    new = merge_main(repo)
    path, cid = _cli(monkeypatch, tmp_path, repo, approved, new, "0101")
    ledger.main()
    assert "ok" in capsys.readouterr().out
    item = ledger.reduce_state(ledger.load_events(path))[cid]
    assert item["approved_head"][:8] == new[:8] or any("فحص 0101" in n["text"] for n in item["notes"])


def test_cli_without_reviewer_exits_with_error(tmp_path, monkeypatch):
    repo, approved = setup(tmp_path)
    new = merge_main(repo)
    _cli(monkeypatch, tmp_path, repo, approved, new, None)
    with pytest.raises(SystemExit):
        ledger.main()
