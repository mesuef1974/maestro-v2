"""اختباراتُ استثناء patch-id (W-20261014-006): يمرّ عند تطابق عمل الفرع تماماً ويُرفض ما اختلف أو مسّ الحاكم والهجرات والأمن."""

from __future__ import annotations

import subprocess

import ledger
import pytest


def git(repo, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=repo, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout.strip()


def commit(repo, name, text, msg):
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-qm", msg)
    return git(repo, "rev-parse", "HEAD")


def setup(tmp_path, work=("work.py", "x=1")):
    """main يحوي a.txt؛ فرعٌ feature يضيف ملف عمل؛ ثمّ يتقدّم main بإيداعٍ آخر ويُحدَّث origin/main."""
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "a.txt", "1", "base")
    git(repo, "update-ref", "refs/remotes/origin/main", "main")
    git(repo, "checkout", "-q", "-b", "feature")
    approved = commit(repo, *work, "session work")
    git(repo, "checkout", "-q", "main")
    commit(repo, "main_only.txt", "m", "main change")
    git(repo, "update-ref", "refs/remotes/origin/main", "main")
    return repo, approved


def rebase_onto_main(repo):
    git(repo, "checkout", "-q", "feature")
    git(repo, "rebase", "-q", "main")
    return git(repo, "rev-parse", "HEAD")


def merge_main(repo):
    git(repo, "checkout", "-q", "feature")
    git(repo, "merge", "-q", "--no-ff", "-m", "merge main", "main")
    return git(repo, "rev-parse", "HEAD")


def test_rebased_identical_work_passes(tmp_path):
    repo, approved = setup(tmp_path)
    new = rebase_onto_main(repo)
    assert new != approved
    assert ledger.check_patch_id(approved, new, str(repo)) == ["work.py"]


def test_clean_main_merge_with_same_work_passes(tmp_path):
    repo, approved = setup(tmp_path)
    new = merge_main(repo)
    assert ledger.check_patch_id(approved, new, str(repo)) == ["work.py"]


def test_changed_work_is_rejected(tmp_path):
    repo, approved = setup(tmp_path)
    git(repo, "checkout", "-q", "feature")
    commit(repo, "work.py", "x=2", "edit after approval")
    new = merge_main(repo)
    with pytest.raises(ledger.LedgerError, match="patch-id"):
        ledger.check_patch_id(approved, new, str(repo))


def test_extra_file_is_rejected(tmp_path):
    repo, approved = setup(tmp_path)
    git(repo, "checkout", "-q", "feature")
    commit(repo, "extra.py", "y=1", "extra")
    with pytest.raises(ledger.LedgerError):
        ledger.check_patch_id(approved, git(repo, "rev-parse", "HEAD"), str(repo))


@pytest.mark.parametrize("path", ["CLAUDE.md", ".claude/rules/x.md", "docs/governance/flow.md",
                                  "app/migrations/0001_x.py", "core/permissions.py", "core/settings.py"])
def test_governing_migration_and_security_files_are_rejected(tmp_path, path):
    repo, approved = setup(tmp_path, work=(path, "v"))
    new = rebase_onto_main(repo)
    with pytest.raises(ledger.LedgerError, match="تُعرض على المالك"):
        ledger.check_patch_id(approved, new, str(repo))


def test_empty_diff_is_rejected(tmp_path):
    repo, _ = setup(tmp_path)
    git(repo, "checkout", "-q", "main")
    head = git(repo, "rev-parse", "HEAD")
    with pytest.raises(ledger.LedgerError, match="فارغ"):
        ledger.check_patch_id(head, head, str(repo))


def test_waive_head_patch_id_records_note_and_moves_head(tmp_path):
    repo, approved = setup(tmp_path)
    new = rebase_onto_main(repo)
    p = tmp_path / "ev.jsonl"
    iid = ledger.add_item("owner", "bug", "م", "أ", "ق", path=p, start="2026-10-02T10:00", priority="P2")
    ledger.append_event("state", iid, {"state": "approved", "by": "0501", "head": approved[:8]}, p)
    with pytest.raises(ledger.LedgerError):
        ledger.waive_head(iid, new[:8], "0405", "x", path=p, kind="patch-id", repo=str(repo))
    ledger.waive_head(iid, new[:8], "0501", "إعادة أساس", path=p, kind="patch-id", repo=str(repo))
    item = ledger.reduce_state(ledger.load_events(p))[iid]
    assert item["approved_head"] == new[:8]
    notes = [e["data"]["text"] for e in ledger.load_events(p) if e["kind"] == "note"]
    assert any("patch-id" in n and "0501" in n for n in notes)
