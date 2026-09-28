"""اختباراتُ maestro_git_scope.py — تشمل سيناريو العطل الحقيقيّ الذي وقع لـ0101 عند 23:03..23:05."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import maestro_git_scope as g  # noqa: E402

MAESTRO = "C:/Users/mesue/delivery_manager_work"
PLATFORM_TREE = "D:/shschool_mvp/.claude/worktrees/distracted-blackwell-e9c85c"


class MaestroGitScope(unittest.TestCase):
    def test_incident_scenario_now_allowed(self):
        # العطلُ الحقيقيّ: git merge --ff-only من داخل مستودع المايسترو — كان يُحجب، يجب أن يُسمح الآن
        self.assertIsNone(g.check("git merge --ff-only origin/main", MAESTRO))

    def test_platform_tree_push_denied(self):
        self.assertIsNotNone(g.check("git push origin main", PLATFORM_TREE))

    def test_unknown_dir_fails_closed(self):
        self.assertIsNotNone(g.check("git push origin main", "C:/Users/mesue/some_other_work"))
        self.assertIsNotNone(g.check("git push origin main", None))

    def test_maestro_compound_chain_allowed(self):
        cmd = "git add tools/x.py && git commit -m 'y' && git push origin main"
        self.assertIsNone(g.check(cmd, MAESTRO))

    def test_maestro_subpath_allowed(self):
        self.assertIsNone(g.check("git push", MAESTRO + "/tools"))

    def test_non_denied_verbs_always_allowed(self):
        for cmd in ("git status", "git log --oneline -5", "bash scripts/preview.sh status",
                    "gh pr list", "gh pr view 700"):
            self.assertIsNone(g.check(cmd, PLATFORM_TREE), cmd)

    def test_gh_pr_merge_denied_outside_maestro(self):
        self.assertIsNotNone(g.check("gh pr merge 700 --squash", PLATFORM_TREE))
        self.assertIsNone(g.check("gh pr merge 700 --squash", MAESTRO))

    def test_railway_denied_outside_maestro(self):
        self.assertIsNotNone(g.check("railway up", PLATFORM_TREE))

    def test_docker_compose_up_down_denied_but_status_like_allowed(self):
        self.assertIsNotNone(g.check("docker compose up -d", PLATFORM_TREE))
        self.assertIsNotNone(g.check("docker compose down", PLATFORM_TREE))
        self.assertIsNone(g.check("docker compose ps", PLATFORM_TREE))

    def test_preview_up_down_denied_status_allowed(self):
        self.assertIsNotNone(g.check("bash scripts/preview.sh up", PLATFORM_TREE))
        self.assertIsNotNone(g.check("bash scripts/preview.sh down", PLATFORM_TREE))
        self.assertIsNone(g.check("bash scripts/preview.sh status", PLATFORM_TREE))

    def test_windows_backslash_cwd_normalized(self):
        self.assertIsNone(g.check("git push", r"C:\Users\mesue\delivery_manager_work"))
        self.assertIsNotNone(g.check("git push", r"D:\shschool_mvp\.claude\worktrees\x"))

    def test_case_insensitive_drive_letter(self):
        self.assertIsNone(g.check("git push", "c:/Users/Mesue/Delivery_Manager_Work"))

    def test_known_limit_inline_cd_not_tracked(self):
        # حدٌّ معلَن: cd داخل الأمر نفسِه لا يُتتبَّع — هذا الاختبارُ يوثّق الفجوة لا يخفيها
        cmd = "cd C:/Users/mesue/delivery_manager_work && git push"
        self.assertIsNotNone(g.check(cmd, PLATFORM_TREE))  # يُحجب رغم أنّ الوجهة الفعليّة آمنة

    def test_env_wrapper_stripped(self):
        self.assertIsNotNone(g.check("env FOO=bar git push", PLATFORM_TREE))
        self.assertIsNone(g.check("env FOO=bar git push", MAESTRO))

    def test_main_hook_contract_end_to_end(self):
        import io
        import json
        from contextlib import redirect_stderr, redirect_stdout

        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push"}, "cwd": PLATFORM_TREE})
        stdin = io.BytesIO(payload.encode("utf-8"))
        old_stdin = sys.stdin
        sys.stdin = type("S", (), {"buffer": stdin})()
        try:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = g.main()
            self.assertEqual(rc, 2)
            self.assertIn("محجوبٌ", err.getvalue())
        finally:
            sys.stdin = old_stdin

    def test_main_allows_non_bash_tools(self):
        import io
        import json

        payload = json.dumps({"tool_name": "Read", "tool_input": {"command": "git push"}, "cwd": PLATFORM_TREE})
        old_stdin = sys.stdin
        sys.stdin = type("S", (), {"buffer": io.BytesIO(payload.encode("utf-8"))})()
        try:
            self.assertEqual(g.main(), 0)
        finally:
            sys.stdin = old_stdin

    def test_malformed_payload_never_blocks(self):
        import io

        old_stdin = sys.stdin
        sys.stdin = type("S", (), {"buffer": io.BytesIO(b"not json at all")})()
        try:
            self.assertEqual(g.main(), 0)
        finally:
            sys.stdin = old_stdin


if __name__ == "__main__":
    unittest.main()
