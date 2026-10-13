"""اختبار --brief لـledger show وmy_state (W-20261013-033): ≤12 سطراً، والافتراضي لا يتغيّر."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

T = Path(__file__).resolve().parent
sys.path.insert(0, str(T))
import ledger  # noqa: E402
import my_state  # noqa: E402


def run(*args):
    return subprocess.run([sys.executable, str(T / args[0]), *args[1:]], capture_output=True, text=True, encoding="utf-8").stdout


def test_show_brief_all_cards_max_12():
    ids = list(ledger.reduce_state(ledger.load_events()))
    assert ids
    items = ledger.reduce_state(ledger.load_events())
    for i in ids[:60]:
        assert len(ledger.brief_lines(items[i], i)) <= 12


def test_show_brief_missing_card():
    assert ledger.brief_lines(None, "X") == ["بطاقةٌ غيرُ موجودة: X"]
    assert len(run("ledger.py", "show", "NOPE", "--brief").splitlines()) <= 12


def test_show_default_unchanged_json():
    out = run("ledger.py", "show", "W-20261013-033")
    assert out.lstrip().startswith("{") and "المواصفة — " in out


@pytest.mark.parametrize("s", ["0301", "0103", "04"])
def test_my_state_brief_max_12(s):
    sess = s if len(s) == 4 else "0401"
    out = my_state.brief_report(sess, ledger.load_events())
    assert len(out.splitlines()) <= 12
