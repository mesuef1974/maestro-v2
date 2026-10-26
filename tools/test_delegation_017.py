"""W-20261025-017 (D-443م وD-489م): سجلُّ تفويض 0101 في الدفتر يقبله approval_check تفويضاً، ويُرفض آلياً الماسُّ بواجهة أو هجرة أو صلاحيات أو حاكم؛ وwaive-head يحترم --repo."""
import approval_check as ac
import ledger
import pytest


@pytest.fixture
def card(tmp_path):
    p = tmp_path / "ev.jsonl"
    cid = ledger.add_item("owner", "bug", "م", "أ", "ق", path=p, start="2026-10-25T10:00", priority="P2")
    ledger.append_event("state", cid, {"state": "ready_for_review", "by": "0301"}, p)
    return cid, p


def _show_from(p, cid):
    return lambda _c: ledger.reduce_state(ledger.load_events(p)).get(cid)


def _no_git(monkeypatch):
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (1, ""))


def test_blockers_cover_ui_migration_permissions_governing():
    bad = ledger.delegation_blockers(["templates/a.html", "static/css/x.css", "core/migrations/0001.py", "core/permissions.py",
                                      "CLAUDE.md", ".claude/rules/a.md", "role_cards/COMMON.md", "tools/ledger.py", "decisions.md"])
    assert len(bad) == 9
    assert ledger.delegation_blockers(["tools/session_state.py", "docs/a.md", "tests/test_x.py"]) == []


def test_only_0101_may_delegate(card):
    cid, p = card
    with pytest.raises(ledger.LedgerError):
        ledger.record_delegation(cid, "abcd1234", "0501", path=p, repo=str(p.parent), changed=["tools/a.py"])


def test_blocked_files_are_refused_and_nothing_is_written(card):
    cid, p = card
    n = len(ledger.load_events(p))
    with pytest.raises(ledger.LedgerError, match="يُعرض على المالك"):
        ledger.record_delegation(cid, "abcd1234", "0101", path=p, repo=str(p.parent), changed=["tools/a.py", "templates/x.html"])
    assert len(ledger.load_events(p)) == n


def test_delegation_records_approval_and_head(card):
    cid, p = card
    files = ledger.record_delegation(cid, "abcd1234", "0101", path=p, repo=str(p.parent), changed=["tools/a.py", "tests/t.py"])
    item = ledger.reduce_state(ledger.load_events(p))[cid]
    assert files == ["tools/a.py", "tests/t.py"] and item["state"] == "approved" and item["approved_head"] == "abcd1234"
    a = item["approvals"][-1]
    assert a["by"] == "0101" and a["via"] == ledger.DELEGATION_VIA and a["n"] == 2


def test_only_ready_cards_can_be_delegated(tmp_path):
    p = tmp_path / "e.jsonl"
    cid = ledger.add_item("owner", "bug", "م", "أ", "ق", path=p, start="2026-10-25T10:00", priority="P2")
    with pytest.raises(ledger.LedgerError, match="جاهزةٍ للمعاينة"):
        ledger.record_delegation(cid, "abcd1234", "0101", path=p, repo=str(p.parent), changed=["tools/a.py"])


def test_approval_check_shows_delegation_not_direct_word(card, monkeypatch):
    cid, p = card
    ledger.record_delegation(cid, "abcd1234", "0101", path=p, repo=str(p.parent), changed=["tools/a.py"])
    monkeypatch.setattr(ac, "_show", _show_from(p, cid))
    _no_git(monkeypatch)
    ev = ac.delegation_evidence(cid, "abcd1234ffff")
    assert len(ev) == 1 and ev[0][1] == "ok" and "تفويضٌ لا قولٌ مباشرٌ" in ev[0][0] and ac._owner_direct(ev[0])


def test_delegation_on_other_head_is_stale(card, monkeypatch):
    cid, p = card
    ledger.record_delegation(cid, "abcd1234", "0101", path=p, repo=str(p.parent), changed=["tools/a.py"])
    monkeypatch.setattr(ac, "_show", _show_from(p, cid))
    _no_git(monkeypatch)
    assert ac.delegation_evidence(cid, "ffff0000")[0][1] == "stale"


def test_tampered_record_with_blocked_file_becomes_conflict(card, monkeypatch):
    cid, p = card
    ledger.append_event("approval", cid, {"by": "0101", "via": ledger.DELEGATION_VIA, "head": "abcd1234", "n": 1, "files": ["static/js/a.js"]}, p)
    monkeypatch.setattr(ac, "_show", _show_from(p, cid))
    _no_git(monkeypatch)
    ev = ac.delegation_evidence(cid, "abcd1234")
    assert ev[0][1] == "conflict" and "مرفوضٌ آلياً" in ev[0][0]


def test_actual_diff_wider_than_recorded_is_conflict(card, monkeypatch):
    cid, p = card
    ledger.record_delegation(cid, "abcd1234", "0101", path=p, repo=str(p.parent), changed=["tools/a.py"])
    monkeypatch.setattr(ac, "_show", _show_from(p, cid))
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (0, "tools/a.py\ntools/b.py\n"))
    ev = ac.delegation_evidence(cid, "abcd1234")
    assert ev[0][1] == "conflict" and "أوسع" in ev[0][0]


def test_other_approver_or_via_is_ignored(card, monkeypatch):
    cid, p = card
    ledger.append_event("approval", cid, {"by": "0501", "via": ledger.DELEGATION_VIA, "head": "abcd1234", "files": ["tools/a.py"]}, p)
    ledger.append_event("approval", cid, {"by": "0101", "via": "قولٌ", "head": "abcd1234", "files": ["tools/a.py"]}, p)
    monkeypatch.setattr(ac, "_show", _show_from(p, cid))
    assert ac.delegation_evidence(cid, "abcd1234") == []


def test_waive_head_docs_honours_repo(tmp_path, monkeypatch):
    """--repo يصل إلى git diff في نوع docs (كان يُهمَل فيُقرأ المستودع الافتراضيّ)."""
    seen = {}

    def fake_git(cmd, repo=None):
        seen["repo"] = repo
        return "docs/a.md\n"

    monkeypatch.setattr(ledger, "_git_read", fake_git)
    assert ledger._docs_changed_files("aaaa1111", "bbbb2222", None, "C:/tree") == ["docs/a.md"]
    assert seen["repo"] == "C:/tree"
