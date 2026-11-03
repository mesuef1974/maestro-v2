"""اختباراتُ أرشفة الدفتر (W-20261027-015)."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402
import ledger_archive as la  # noqa: E402

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=ledger.DOHA)


def _ev(card, kind, data, days_ago):
    return {"ts": (NOW - timedelta(days=days_ago)).isoformat(timespec="seconds"), "id": card, "kind": kind, "data": data}


def _ledger(tmp_path):
    p = tmp_path / "events.jsonl"
    evs = [
        _ev("W-OLD", "created", {"title": "قديمة"}, 60), _ev("W-OLD", "state", {"state": "published", "by": "0601"}, 40),
        _ev("W-OLDOPEN", "created", {"title": "قديمة مفتوحة"}, 60),
        _ev("W-NEWPUB", "created", {"title": "حديثة"}, 10), _ev("W-NEWPUB", "state", {"state": "published", "by": "0601"}, 5),
        _ev("W-CLOSED", "created", {"title": "مغلقة"}, 90), _ev("W-CLOSED", "state", {"state": "closed", "by": "0101"}, 80),
    ]
    p.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in evs), encoding="utf-8")
    return p, evs


def test_plan_picks_only_old_terminal_cards(tmp_path):
    _, evs = _ledger(tmp_path)
    assert la.plan(evs, NOW) == {"W-CLOSED": "2026-08", "W-OLD": "2026-09"}


def test_apply_moves_whole_cards_and_keeps_live_state_intact(tmp_path):
    p, evs = _ledger(tmp_path)
    before = ledger.reduce_state(evs)
    res = la.apply(p, NOW)
    assert res["cards"] == 2 and res["events"] == 4
    live = ledger.reduce_state(ledger.load_events(p))
    assert set(live) == {"W-OLDOPEN", "W-NEWPUB"}
    assert live["W-NEWPUB"] == before["W-NEWPUB"] and live["W-OLDOPEN"] == before["W-OLDOPEN"]
    assert [e["kind"] for e in la.events_of("W-OLD", p)] == ["created", "state"]
    assert la.events_of("W-NEWPUB", p) == []


def test_apply_is_idempotent(tmp_path):
    p, _ = _ledger(tmp_path)
    la.apply(p, NOW)
    text = p.read_text(encoding="utf-8")
    assert la.apply(p, NOW) == {"cards": 0, "events": 0, "files": []}
    assert p.read_text(encoding="utf-8") == text


def test_dry_run_changes_nothing(tmp_path, capsys, monkeypatch):
    p, _ = _ledger(tmp_path)
    monkeypatch.setenv("LEDGER_PATH", str(p))
    text = p.read_text(encoding="utf-8")
    assert la.main(["--days", "30"]) == 0
    assert p.read_text(encoding="utf-8") == text and not (tmp_path / "archive").exists()
    assert "عرض" in capsys.readouterr().out
