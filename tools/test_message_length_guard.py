"""اختبارات حارس طول الرسائل (W-20261013-032)."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import message_length_guard as g  # noqa: E402

LONG = "ا" * (g.THRESHOLD + 50)


def _p(tool="SendMessage", **tool_in):
    return {"tool_name": tool, "tool_input": tool_in, "session_id": "abcd1234"}


def test_short_message_passes_and_long_is_warned_then_blocked(monkeypatch):
    monkeypatch.delenv("MESSAGE_LENGTH_GUARD_MODE", raising=False)
    monkeypatch.setattr(g, "MODE_FILE", Path("none.mode"))
    assert g.decide(_p(message="رسالة قصيرة"))[0] == "allow"
    verdict, msg = g.decide(_p(message=LONG))
    assert verdict == "warn" and "handover_notes" in msg
    monkeypatch.setenv("MESSAGE_LENGTH_GUARD_MODE", "block")
    assert g.decide(_p(message=LONG))[0] == "deny"
    assert g.decide(_p("mcp__ccd_session_mgmt__send_message", message=LONG))[0] == "deny"


def test_message_with_a_real_file_path_or_urgent_tag_passes(monkeypatch):
    monkeypatch.setenv("MESSAGE_LENGTH_GUARD_MODE", "block")
    assert g.decide(_p(message="ملخص " + LONG + " handover_notes/msg_0103_0101_2026-10-13.md"))[0] == "allow"
    assert g.decide(_p(message="[عاجل] " + LONG))[0] == "allow"


def test_other_tools_pass_and_faults_allow(monkeypatch):
    monkeypatch.setenv("MESSAGE_LENGTH_GUARD_MODE", "block")
    assert g.decide(_p("Bash", command=LONG))[0] == "allow"
    here = Path(__file__).parent / "message_length_guard.py"
    out = subprocess.run([sys.executable, str(here)], input="not json", capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout == ""
