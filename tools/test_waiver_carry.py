from __future__ import annotations

import json
import subprocess

import approval_check as ac


def git(repo, *a):
    return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def commit(repo, name, text):
    f = repo / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c")
    return git(repo, "rev-parse", "HEAD")[:8]


def merge_main(repo):
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-ff", "-m", "m", "main")
    return git(repo, "rev-parse", "HEAD")[:8]


def setup(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "a.txt", "1")
    git(repo, "checkout", "-q", "-b", "feature")
    approved = commit(repo, "work.py", "x=1")
    git(repo, "checkout", "-q", "main")
    commit(repo, "main_only.txt", "m")
    git(repo, "update-ref", "refs/remotes/origin/main", "main")
    git(repo, "checkout", "-q", "feature")
    return repo, approved


def wire(monkeypatch, repo, approved, notes):
    card = {"notes": [{"text": n} for n in notes]}
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (0, json.dumps(card)))
    monkeypatch.setattr(ac, "REPO_DIR", str(repo))
    monkeypatch.setattr(ac, "confirmations_evidence", lambda target, head=None, **k: [("owner_confirmations.md: x", "ok")] if head == approved else [])


def chain_note(base, new):
    return f"استثناءُ رأسٍ تافه بتوقيع 0501: {base}→{new} — سلسلةُ إصلاح tests/ ودمج main فقط (تحقّق آليّ، W-20261017-012) — t"


def main_note(base, new):
    return f"استثناءُ رأسٍ تافه بتوقيع 0501: {base}→{new} — دمجُ main فقط (تحقّق آليّ) — t"


def test_chain_waiver_carries_approval(tmp_path, monkeypatch):
    repo, approved = setup(tmp_path)
    commit(repo, "tests/test_x.py", "1")
    new = merge_main(repo)
    wire(monkeypatch, repo, approved, [chain_note(approved, new)])
    out = ac.waiver_carry("W-1", new, "W-1")
    assert out and out[0][1] == "ok" and "محمولٌ" in out[0][0]


def test_main_merge_waiver_still_carries(tmp_path, monkeypatch):
    repo, approved = setup(tmp_path)
    new = merge_main(repo)
    wire(monkeypatch, repo, approved, [main_note(approved, new)])
    assert ac.main_merge_carry("W-1", new, "W-1")


def test_successive_waivers_are_followed(tmp_path, monkeypatch):
    repo, approved = setup(tmp_path)
    mid = commit(repo, "tests/test_x.py", "1")
    new = merge_main(repo)
    wire(monkeypatch, repo, approved, [chain_note(approved, mid), chain_note(mid, new)])
    assert ac.waiver_carry("W-1", new, "W-1")


def test_ui_commit_chain_is_not_carried(tmp_path, monkeypatch):
    repo, approved = setup(tmp_path)
    commit(repo, "templates/p.html", "<p>")
    new = merge_main(repo)
    wire(monkeypatch, repo, approved, [chain_note(approved, new)])
    assert ac.waiver_carry("W-1", new, "W-1") == []


def test_no_waiver_or_no_direct_approval_is_not_carried(tmp_path, monkeypatch):
    repo, approved = setup(tmp_path)
    commit(repo, "tests/test_x.py", "1")
    new = merge_main(repo)
    wire(monkeypatch, repo, approved, [])
    assert ac.waiver_carry("W-1", new, "W-1") == []
    wire(monkeypatch, repo, "ffffffff", [chain_note(approved, new)])
    assert ac.waiver_carry("W-1", new, "W-1") == []
