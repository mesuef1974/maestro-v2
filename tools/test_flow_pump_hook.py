"""اختباراتُ مشغّل المضخّة من داخل الجلسات:  python -m pytest test_flow_pump_hook.py"""

import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import flow_pump_hook as hook

PLATFORM = "D:\\shschool_mvp\\.claude\\worktrees\\x"


def _bash(command, cwd=PLATFORM, event="PostToolUse", tool="Bash"):
    return {"hook_event_name": event, "tool_name": tool, "cwd": cwd, "tool_input": {"command": command}}


class Interval(unittest.TestCase):
    def test_flow_commands_trigger_a_short_cycle(self):
        for cmd in (
            "git push -u origin claude/x",
            "gh pr merge 1204 --squash",
            "gh pr create --title t",
            "python tools/ledger.py move W-1 approved --head abc",
            "python tools/ledger.py reapprove W-1 --head abc --by 0101 --note n",
            "python tools/ledger_sync.py --apply",
            "python tools/record_owner_confirmation.py --session 0101",
            "python tools/approval_check.py card W-1 --head abc",
        ):
            self.assertEqual(hook.interval("PostToolUse", "Bash", cmd), hook.FLOW_INTERVAL_S, cmd)

    def test_powershell_commands_count_too(self):
        self.assertEqual(hook.interval("PostToolUse", "PowerShell", "git push origin x"), hook.FLOW_INTERVAL_S)

    def test_reads_do_not_trigger(self):
        for cmd in ("git status", "python tools/ledger.py list", "python tools/ledger.py show W-1", "gh pr view 1"):
            self.assertIsNone(hook.interval("PostToolUse", "Bash", cmd), cmd)

    def test_other_tools_do_not_trigger(self):
        self.assertIsNone(hook.interval("PostToolUse", "Edit", "git push"))

    def test_turn_end_and_session_start_are_the_fallback(self):
        self.assertEqual(hook.interval("Stop", "", ""), hook.IDLE_INTERVAL_S)
        self.assertEqual(hook.interval("SessionStart", "", ""), hook.IDLE_INTERVAL_S)


class Decide(unittest.TestCase):
    NOW = 1_000_000.0

    def test_a_push_after_a_minute_fires(self):
        self.assertTrue(hook.decide(_bash("git push"), self.NOW, self.NOW - 61, off=False))

    def test_a_push_within_the_minute_waits(self):
        self.assertFalse(hook.decide(_bash("git push"), self.NOW, self.NOW - 30, off=False))

    def test_the_first_ever_cycle_fires(self):
        self.assertTrue(hook.decide(_bash("git push"), self.NOW, None, off=False))

    def test_stop_waits_five_minutes(self):
        stop = {"hook_event_name": "Stop", "cwd": PLATFORM}
        self.assertFalse(hook.decide(stop, self.NOW, self.NOW - 120, off=False))
        self.assertTrue(hook.decide(stop, self.NOW, self.NOW - 301, off=False))

    def test_the_off_switch_stops_everything(self):
        self.assertFalse(hook.decide(_bash("git push"), self.NOW, None, off=True))

    def test_sessions_outside_the_platform_and_the_ledger_are_ignored(self):
        self.assertFalse(hook.decide(_bash("git push", cwd="C:\\Users\\mesue\\other"), self.NOW, None, off=False))
        self.assertTrue(
            hook.decide(_bash("git push", cwd="C:/Users/mesue/delivery_manager_work"), self.NOW, None, off=False)
        )


class Main(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        patches = {
            "STAMP": self.tmp / "flow_pump.stamp",
            "OFF": self.tmp / "flow_pump.off",
            "OUT": self.tmp / "flow_pump.out",
            "LOCK": self.tmp / "flow_pump.lock",
        }
        for name, value in patches.items():
            p = mock.patch.object(hook, name, value)
            p.start()
            self.addCleanup(p.stop)

    def _run(self, payload):
        with mock.patch.object(hook, "spawn") as spawn, mock.patch("sys.stdin", io.StringIO(payload)):
            self.assertEqual(hook.main(), 0)
        return spawn

    def test_a_flow_command_launches_the_pump(self):
        self.assertTrue(self._run(json.dumps(_bash("git push"))).called)

    def test_a_running_pump_is_not_doubled(self):
        hook.LOCK.touch()
        self.assertFalse(self._run(json.dumps(_bash("git push"))).called)

    def test_a_stale_lock_does_not_block(self):
        hook.LOCK.touch()
        old = time.time() - hook.STALE_LOCK_S - 5
        import os

        os.utime(hook.LOCK, (old, old))
        self.assertTrue(self._run(json.dumps(_bash("git push"))).called)

    def test_garbage_input_never_breaks_the_session(self):
        for raw in ("", "not json", "[1, 2]", '{"tool_input": 5}'):
            self.assertFalse(self._run(raw).called, raw)

    def test_spawn_stamps_and_detaches(self):
        with mock.patch("subprocess.Popen") as popen:
            hook.spawn()
        self.assertTrue(hook.STAMP.exists())
        args = popen.call_args.args[0]
        self.assertIn("--apply", args)
        self.assertIn("W-20261001-006", args)
        self.assertEqual(popen.call_args.kwargs["stdin"], hook.subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
