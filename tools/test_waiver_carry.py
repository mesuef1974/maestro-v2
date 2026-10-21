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


# ── D-451م: تنازلاتُ المضخّة (0101) وحلقةُ tests-only محمولةٌ بإعادة تحقّق، والأدلّةُ البصريّة تُورث ──


def only_tests_note(base, new, by="0101"):
    return f"استثناءُ رأسٍ تافه بتوقيع {by}: {base}→{new} — إصلاحُ اختباراتٍ فقط بلا حراسةٍ أمنيّة (تحقّق آليّ) — t"


def test_a_pump_waiver_signed_0101_carries_like_0501(tmp_path, monkeypatch):
    repo, approved = setup(tmp_path)
    new = merge_main(repo)
    wire(monkeypatch, repo, approved, [main_note(approved, new).replace("0501", "0101")])
    assert ac.waiver_carry("W-1", new, "W-1")


def test_a_tests_only_hop_is_reverified_and_carried(tmp_path, monkeypatch):
    repo, approved = setup(tmp_path)
    new = commit(repo, "tests/test_x.py", "def test_x():\n    assert 1\n")
    wire(monkeypatch, repo, approved, [only_tests_note(approved, new)])
    out = ac.waiver_carry("W-1", new, "W-1")
    assert out and "D-451م" in out[0][0]


def test_a_tests_only_note_over_a_code_change_is_not_carried(tmp_path, monkeypatch):
    repo, approved = setup(tmp_path)
    new = commit(repo, "work.py", "x=2")
    wire(monkeypatch, repo, approved, [only_tests_note(approved, new)])
    assert ac.waiver_carry("W-1", new, "W-1") == []


def test_a_waiver_signed_by_another_session_is_not_carried(tmp_path, monkeypatch):
    repo, approved = setup(tmp_path)
    new = merge_main(repo)
    wire(monkeypatch, repo, approved, [main_note(approved, new).replace("0501", "0702")])
    assert ac.waiver_carry("W-1", new, "W-1") == []


def wire_git(monkeypatch, repo, card):
    """ledger.py show ← البطاقة، وgit حقيقيٌّ على المستودع المؤقّت (فرقُ الواجهة وإعادةُ التحقّق)."""
    real = ac.run
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: real(cmd, cwd) if cmd[0] == "git" else (0, json.dumps(card)))
    monkeypatch.setattr(ac, "REPO_DIR", str(repo))


def ui_setup(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "a.txt", "1")
    git(repo, "update-ref", "refs/remotes/origin/main", "main")
    git(repo, "checkout", "-q", "-b", "feature")
    return repo, commit(repo, "templates/p.html", "<p>")


def visual(monkeypatch, repo, notes, evidenced):
    import visual_gate

    card = {"files": ["templates/p.html"], "created": "2026-10-21T08:00", "notes": [{"text": n} for n in notes]}
    wire_git(monkeypatch, repo, card)
    monkeypatch.setattr(visual_gate, "evidence_status", lambda c, h: (h[:8] == evidenced, f"لا أدلة بصرية للرأس {h[:8]}"))


def test_visual_evidence_is_inherited_over_a_reverified_tests_only_hop(tmp_path, monkeypatch):
    repo, approved = ui_setup(tmp_path)
    new = commit(repo, "tests/test_p.py", "def test_p():\n    assert 1\n")
    visual(monkeypatch, repo, [only_tests_note(approved, new)], approved)
    info: list[str] = []
    assert ac.visual_problem("W-1", new, info=info) is None
    assert "موروثةٌ من الرأس " + approved in info[0]


def test_visual_evidence_is_not_inherited_over_a_chain_that_brings_ui(tmp_path, monkeypatch):
    repo, approved = ui_setup(tmp_path)
    git(repo, "checkout", "-q", "main")
    commit(repo, "templates/other.html", "<q>")
    git(repo, "update-ref", "refs/remotes/origin/main", "main")
    git(repo, "checkout", "-q", "feature")
    commit(repo, "tests/test_p.py", "def test_p():\n    assert 1\n")
    new = merge_main(repo)
    visual(monkeypatch, repo, [chain_note(approved, new)], approved)
    assert "لا أدلة بصرية" in ac.visual_problem("W-1", new)


def test_without_a_waiver_the_visual_gate_still_blocks(tmp_path, monkeypatch):
    repo, approved = ui_setup(tmp_path)
    new = commit(repo, "tests/test_p.py", "def test_p():\n    assert 1\n")
    visual(monkeypatch, repo, [], approved)
    assert "لا أدلة بصرية" in ac.visual_problem("W-1", new)


CARD = "W-20261020-009"


def confirmations(tmp_path, monkeypatch, *quotes_at):
    f = tmp_path / "owner_confirmations.md"
    f.write_text("\n".join(f"| 2026-10-21 07:41 | 0101 (إفادةُ جلسة) مصدره: مباشر | {CARD} | «{q}» | {CARD} @{h} |" for q, h in quotes_at),
                 encoding="utf-8")
    monkeypatch.setattr(ac, "ROOT", tmp_path)


def test_approval_base_and_security_approval_follow_reverified_waivers(tmp_path, monkeypatch):
    repo, approved = setup(tmp_path)
    new = merge_main(repo)
    confirmations(tmp_path, monkeypatch, (f"أقرّ أمنياً لـ#1203 على {approved} (Recommended)", approved))
    wire_git(monkeypatch, repo, {"notes": [{"text": main_note(approved, new).replace("0501", "0101")}]})
    base, rows = ac.approval_base(CARD, new)
    assert base == approved and ac.owner_direct(rows)
    assert ac.security_approved(CARD, new) == approved
    wire_git(monkeypatch, repo, {"notes": []})
    assert ac.approval_base(CARD, new) is None
    assert ac.security_approved(CARD, new) is None


def test_a_d443_delegation_row_is_not_an_owner_direct_quote(tmp_path, monkeypatch):
    repo, approved = setup(tmp_path)
    confirmations(tmp_path, monkeypatch, ("اعتماد الراس عندك الا المستثنى يعرض على المالك فقط", approved))
    wire_git(monkeypatch, repo, {"notes": []})
    base, rows = ac.approval_base(CARD, approved)
    assert base == approved and not ac.owner_direct(rows)
    assert ac.security_approved(CARD, approved) is None
