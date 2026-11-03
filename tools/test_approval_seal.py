"""اختباراتُ ختم هويّة اعتماد 0101 وموانع تفويض قاعدة الاعتماد (W-20261103-011)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import approval_seal as aseal  # noqa: E402
import ledger  # noqa: E402

TS = "2026-11-03T22:30:00+03:00"


@pytest.fixture()
def key(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRO_SEAL_KEY", str(tmp_path / "k" / "seal.key"))
    return aseal.load_key(create=True)


def test_seal_roundtrip_and_tamper_detection(key):
    s = aseal.seal("W-1", "abcdef12", "0101", TS, key)
    assert aseal.verify("W-1", "abcdef12", "0101", TS, s, key)
    assert aseal.verify("W-1", "abcdef12999", "0101", TS, s, key)  # الرأس يُقصّ إلى 8 أحرف
    for args in (("W-2", "abcdef12", "0101", TS), ("W-1", "abcdef13", "0101", TS), ("W-1", "abcdef12", "0501", TS), ("W-1", "abcdef12", "0101", TS[:-1] + "1")):
        assert not aseal.verify(*args, s, key)
    assert not aseal.verify("W-1", "abcdef12", "0101", TS, None, key)
    assert not aseal.verify("W-1", "abcdef12", "0101", TS, "0" * 32, key)


def test_another_key_cannot_forge(key, tmp_path):
    other = b"x" * 64
    forged = aseal.seal("W-1", "abcdef12", "0101", TS, other)
    assert not aseal.verify("W-1", "abcdef12", "0101", TS, forged, key)


def test_shadow_mode_accepts_but_logs(key, tmp_path):
    ev = {"by": "0101", "head": "abcdef12", "ts": TS}
    assert aseal.problem(ev, "W-1", tmp_path, key) is None
    assert "بلا ختم" in (tmp_path / "seal_shadow.log").read_text(encoding="utf-8")


def test_enforced_mode_rejects_unsealed_and_forged_after_cutover(key, tmp_path):
    (tmp_path / "seal_enforce_from").write_text("2026-11-03T22:00:00+03:00", encoding="utf-8")
    ev = {"by": "0101", "head": "abcdef12", "ts": TS}
    assert "بلا ختم" in aseal.problem(ev, "W-1", tmp_path, key)
    assert "غيرُ صالح" in aseal.problem({**ev, "seal": "0" * 32}, "W-1", tmp_path, key)
    good = {**ev, "seal": aseal.seal("W-1", "abcdef12", "0101", TS, key)}
    assert aseal.problem(good, "W-1", tmp_path, key) is None


def test_events_before_the_cutover_are_accepted_unsealed(key, tmp_path):
    (tmp_path / "seal_enforce_from").write_text("2026-11-04T00:00:00+03:00", encoding="utf-8")
    assert aseal.problem({"by": "0101", "head": "abcdef12", "ts": TS}, "W-1", tmp_path, key) is None


def test_non_sealed_actors_are_not_checked(key, tmp_path):
    (tmp_path / "seal_enforce_from").write_text("2026-01-01T00:00:00+03:00", encoding="utf-8")
    assert aseal.problem({"by": "0501", "head": "abcdef12", "ts": TS}, "W-1", tmp_path, key) is None


def test_record_delegation_seals_the_event_and_it_verifies(key, tmp_path):
    lp = tmp_path / "e.jsonl"
    ledger.append_event("created", "W-20261103-901", {"title": "x"}, lp)
    ledger.append_event("state", "W-20261103-901", {"state": "ready_for_review", "by": "0701", "ready_head": "abcdef12"}, lp)
    ledger.record_delegation("W-20261103-901", "abcdef12", "0101", path=lp, changed=["tools/other.py"])
    ev = [json.loads(x) for x in lp.read_text(encoding="utf-8").splitlines() if '"approval"' in x][0]
    assert ev["data"]["seal"] and aseal.verify("W-20261103-901", ev["data"]["head"], "0101", ev["ts"], ev["data"]["seal"], key)


def test_auth_rule_files_need_a_literal_owner_quote(monkeypatch):
    assert ledger.delegation_blockers(["tools/other.py", "docs/x.md"]) == []
    for f in ("tools/ledger.py", "tools/approval_check.py", "tools/flow_pump.py", "tools/approval_seal.py", "tools/push_approved.py", "decisions.md"):
        assert ledger.delegation_blockers([f]), f
    assert ledger.delegation_blockers(["tools/ledger.py"], "قول المالك")  # ما لم يثبت الاقتباس
    monkeypatch.setattr(ledger, "find_owner_order", lambda q, *a, **k: "2026-11-03T22:00")
    assert ledger.delegation_blockers(["tools/ledger.py"], "قول المالك الحرفي المسجل") == []
    monkeypatch.setattr(ledger, "find_owner_order", lambda q, *a, **k: (_ for _ in ()).throw(ledger.LedgerError("غير موجود")))
    assert ledger.delegation_blockers(["tools/ledger.py"], "اقتباس مزعوم")


def test_record_delegation_refuses_auth_rule_files_without_the_quote(key, tmp_path):
    lp = tmp_path / "e.jsonl"
    ledger.append_event("created", "W-20261103-902", {"title": "x"}, lp)
    ledger.append_event("state", "W-20261103-902", {"state": "ready_for_review", "by": "0701", "ready_head": "abcdef12"}, lp)
    with pytest.raises(ledger.LedgerError):
        ledger.record_delegation("W-20261103-902", "abcdef12", "0101", path=lp, changed=["tools/flow_pump.py"])
