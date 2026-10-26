"""اختباراتُ خطّاف ready_mark — unittest بلا اعتمادٍ خارجيّ:  python -m unittest test_ready_mark_hook"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import ledger
import ready_mark_hook as hook

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
CARD = "W-20261015-777"


def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, encoding="utf-8", check=True, env=ENV).stdout.strip()


class Hook(unittest.TestCase):
    def setUp(self):
        # الفحصُ المسبق صار يعمل آلياً متى كانت الشجرةُ على الرأس (W-20261014-007): هنا يُستبدل بنجاحٍ وهميّ كي لا يطلب مستودعاتٍ تجريبيّةً كاملة
        real = ledger._run_preflight
        ledger._run_preflight = lambda card, repo: (0, "ok")
        self.addCleanup(setattr, ledger, "_run_preflight", real)
        # هذه الاختباراتُ لا تغطّي بوّابةَ الإيصال: تُبقى إنذاراً هنا (الإلزامُ مُختبَرٌ في test_prepush_receipt)
        _p = mock.patch.dict(os.environ, {"PREPUSH_RECEIPT_ENFORCE": "0", "PREMERGE_GATE_ENFORCE": "0"}); _p.start(); self.addCleanup(_p.stop)
        self.tmp = tempfile.mkdtemp()
        self.repo = str(Path(self.tmp) / "r")
        Path(self.repo).mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        (Path(self.repo) / "a").write_text("x", encoding="utf-8")
        git(self.repo, "add", "a")
        git(self.repo, "commit", "-q", "-m", "base")
        git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(self.repo, "checkout", "-q", "-b", "w")
        (Path(self.repo) / "b").write_text("y", encoding="utf-8")
        git(self.repo, "add", "b")
        git(self.repo, "commit", "-q", "-m", f"{CARD}: عمل")
        self.head = git(self.repo, "rev-parse", "--short=8", "HEAD")
        self.ledger = Path(self.tmp) / "events.jsonl"
        ledger.append_event("created", CARD, {"problem": "م", "state": "captured", "type": "ui", "files": ["templates/"]}, self.ledger)
        ledger.append_event("state", CARD, {"state": "in_progress", "by": "0702", "held_by": "0702"}, self.ledger)

    def payload(self, text, tool="SendMessage"):
        return {"tool_name": tool, "session_id": "sid", "cwd": "D:/x", "tool_input": {"to": "local_x", "message": text}}

    def msg(self, head=None, card=CARD, by="0702"):
        return f"جاهزٌ للمعاينة ({by}) {card} الرأس {head or self.head} الرابط http://localhost:8500/x/ الدور principal"

    sender = "0702"

    def run_hook(self, payload):
        title = None if self.sender is None else f"{self.sender} · جلسة"
        with mock.patch.dict(os.environ, {"SCHOOLOS_REPO": self.repo}), mock.patch.object(hook.session_identity, "app_title", return_value=(title, [])):
            return hook.handle(payload, path=self.ledger)

    def state(self):
        return ledger.reduce_state(ledger.load_events(self.ledger))[CARD]["state"]

    def test_a_valid_ready_message_marks_the_card(self):
        out = self.run_hook(self.payload(self.msg()))
        self.assertTrue(out[0].startswith("ok:"), out)
        self.assertEqual(self.state(), "ready_for_review")

    def test_other_text_or_other_tools_do_nothing(self):
        self.assertEqual(self.run_hook(self.payload("مرحباً " + self.msg())), [])
        self.assertEqual(self.run_hook(self.payload(self.msg(), tool="Bash")), [])
        self.assertEqual(self.state(), "in_progress")

    def test_a_message_missing_card_head_or_session_does_nothing(self):
        for text in (f"جاهزٌ للمعاينة (0702) الرأس {self.head}", f"جاهزٌ للمعاينة (0702) {CARD}"):
            self.assertEqual(self.run_hook(self.payload(text)), [])
        self.assertEqual(self.state(), "in_progress")

    def test_a_wrong_head_is_refused_by_ready_mark_gates(self):
        out = self.run_hook(self.payload(self.msg(head="deadbeef")))
        self.assertIn("تخطّي", out[0])
        self.assertEqual(self.state(), "in_progress")

    def test_a_session_cannot_mark_a_card_held_by_another(self):
        self.sender = "0409"
        out = self.run_hook(self.payload(self.msg(by="0409")))
        self.assertIn("حاملتُها", out[0])
        self.assertEqual(self.state(), "in_progress")

    def test_sender_comes_from_session_id_not_message_text(self):
        # جلسةٌ 0409 تنتحل 0702 في النصّ: يُرفض ولا تُسجَّل
        self.sender = "0409"
        out = self.run_hook(self.payload(self.msg(by="0702")))
        self.assertIn("يخالف", out[0])
        self.assertEqual(self.state(), "in_progress")

    def test_text_without_number_uses_derived_sender(self):
        text = f"جاهزٌ للمعاينة {CARD} الرأس {self.head}"
        out = self.run_hook(self.payload(text))
        self.assertTrue(out[0].startswith("ok:"), out)

    def test_unresolvable_sender_is_skipped_even_if_text_names_holder(self):
        self.sender = None
        out = self.run_hook(self.payload(self.msg()))
        self.assertIn("تعذّر", out[0])
        self.assertEqual(self.state(), "in_progress")

    def test_main_is_always_silent_and_exits_0_even_on_garbage_or_missing_ledger(self):
        for raw in ("", "ليس json", json.dumps(self.payload(self.msg()))):
            with mock.patch("sys.stdin", io.StringIO(raw)), mock.patch.dict(os.environ, {"LEDGER_PATH": str(Path(self.tmp) / "none.jsonl")}):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    self.assertEqual(hook.main(), 0)
                self.assertEqual(buf.getvalue(), "")

    def test_the_hook_calls_only_ready_mark_not_approval(self):
        src = Path(hook.__file__).read_text(encoding="utf-8")
        for forbidden in ("approved", "push", "approval_check", "subprocess"):
            self.assertNotIn(forbidden, src)


if __name__ == "__main__":
    unittest.main()
