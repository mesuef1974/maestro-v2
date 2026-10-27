"""W-20261026-013: approve.py ينفّذ اعتمادَ 0101 بالتفويض ذرّياً (فحص ← سطر ← دفتر ← تحقّق) ويرفض بسببٍ واحد قبل أيّ كتابة."""
import approve
import ledger
import pytest

HEAD = "abcdef12"
FULL = HEAD + "0" * 32
REVIEWED = "راجعتُ الفرق: أداة قراءة فقط واختباراتها"
STANDING = (
    "| 2026-10-18 10:00 | 0101 (إفادةُ جلسة) مصدره: مباشر | q | «نعم، دائم» | standing-head-approval |\n"
    "| 2026-10-18 10:01 | 0101 (إفادةُ جلسة) مصدره: مباشر | q | «نعم، دائم يغني (Recommended)» | delegations-no-expiry |\n"
)


def _git(diff="tools/a.py\ntests/t.py"):
    def git(tree, *args):
        return FULL if args[0] == "rev-parse" else diff

    return git


@pytest.fixture
def env(tmp_path):
    p = tmp_path / "ev.jsonl"
    cid = ledger.add_item("owner", "bug", "م", "أ", "ق", path=p, start="2026-10-25T10:00", priority="P2")
    ledger.append_event("state", cid, {"state": "ready_for_review", "by": "0301", "ready_head": HEAD}, p)
    conf = tmp_path / "owner_confirmations.md"
    conf.write_text(STANDING, encoding="utf-8")
    return cid, p, conf


def _run(env, check=lambda c, h: (True, "✔ ثابت"), **kw):
    cid, p, conf = env
    args = {"head": HEAD, "by": "0101", "reviewed": REVIEWED, "tree": None, "ledger_path": p, "confirmations": conf, "check": check, "git": _git()}
    args.update(kw)
    return approve.approve(cid, args.pop("head"), args.pop("by"), args.pop("reviewed"), args.pop("tree"), "origin/main", **args)


def test_happy_path_writes_row_event_and_verifies(env):
    cid, p, conf = env
    line = _run(env)
    item = ledger.reduce_state(ledger.load_events(p))[cid]
    assert item["state"] == "approved" and item["approved_head"] == HEAD and item["approvals"][-1]["via"] == ledger.DELEGATION_VIA
    text = conf.read_text(encoding="utf-8")
    assert text.startswith(STANDING) and f"@{HEAD}" in text and cid in text and "بتفويض D-443م" in text
    assert "✔" in line and HEAD in line


def test_other_head_than_declared_is_refused_and_nothing_written(env):
    cid, p, conf = env
    n = len(ledger.load_events(p))
    with pytest.raises(approve.RefusedError, match="الرأسُ المعلَن جاهزاً"):
        _run(env, head="deadbeef")
    assert len(ledger.load_events(p)) == n and conf.read_text(encoding="utf-8") == STANDING


def test_wrong_state_is_refused(env):
    cid, p, conf = env
    _run(env)
    with pytest.raises(approve.RefusedError, match="اعتُمدت أصلاً"):
        _run(env)
    assert conf.read_text(encoding="utf-8").count(f"@{HEAD}") == 1  # لا سطرَ مكرَّر


def test_only_0101_and_reviewed_required(env):
    with pytest.raises(approve.RefusedError, match="لـ0101 وحدَها"):
        _run(env, by="0501")
    with pytest.raises(approve.RefusedError, match="--reviewed"):
        _run(env, reviewed="قصير")


def test_ui_or_governing_diff_is_refused(env):
    cid, p, conf = env
    with pytest.raises(approve.RefusedError):
        _run(env, git=_git("tools/a.py\ntemplates/x.html"))
    assert conf.read_text(encoding="utf-8") == STANDING and ledger.reduce_state(ledger.load_events(p))[cid]["state"] == "ready_for_review"


def test_ledger_failure_rolls_back_the_confirmation_row(env, monkeypatch):
    cid, p, conf = env

    def boom(*a, **k):
        raise ledger.LedgerError("رُفض في الدفتر")

    monkeypatch.setattr(ledger, "record_delegation", boom)
    with pytest.raises(approve.RefusedError, match="رفضه الدفتر"):
        _run(env)
    assert conf.read_text(encoding="utf-8") == STANDING  # ذرّيّ: لا سطرَ بلا حدث


def test_unconfirmed_by_approval_check_is_reported_as_failure(env):
    with pytest.raises(RuntimeError, match="لم يؤكّده"):
        _run(env, check=lambda c, h: (False, "✘ سبب"))


def test_main_exit_codes(env, monkeypatch, capsys):
    cid, p, conf = env
    monkeypatch.setattr(approve, "approve", lambda *a, **k: (_ for _ in ()).throw(approve.RefusedError("سبب واحد")))
    assert approve.main([cid, "--head", HEAD, "--by", "0101", "--reviewed", REVIEWED]) == 2
    assert "✘ لا اعتماد: سبب واحد" in capsys.readouterr().err
