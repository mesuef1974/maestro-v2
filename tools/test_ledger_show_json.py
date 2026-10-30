"""ledger show يطبع وثيقة JSON واحدة على stdout (W-20261028-015)؛ سطر المواصفة إلى stderr."""
from __future__ import annotations

import json
import sys
from pathlib import Path

T = Path(__file__).resolve().parent
sys.path.insert(0, str(T))
import ledger  # noqa: E402


def test_show_stdout_is_one_valid_json_document(monkeypatch, capsys):
    ev = [{"ts": "2026-10-29T10:00:00+03:00", "id": "W-20261029-901", "kind": "created",
           "data": {"problem": "ع", "impact": "أ", "accept": "ق", "priority": "P2", "type": "tooling", "source": "discovery", "start": "2026-10-29T10:00"}}]
    monkeypatch.setattr(ledger, "load_events", lambda *a, **k: ev)
    monkeypatch.setattr(sys, "argv", ["ledger.py", "show", "W-20261029-901"])
    ledger.main()
    out, err = capsys.readouterr()
    assert json.loads(out)["id"] == "W-20261029-901"  # لا نصَّ بعد الوثيقة
    assert "المواصفة" in err and "المواصفة" not in out
