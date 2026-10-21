"""ترميزُ UTF-8 في كلّ أداة تُشغَّل من سطر الأوامر (الموجة 0.5، D-453م): لا طبعَ عربيّ يسقط على cp1252/cp1256 في ويندوز."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
#: أدواتٌ لا تطبع على الطرفيّة (خطّافاتٌ تعيد رمزاً فقط) فلا تحتاج إعادةَ الضبط
NO_PRINT = {"flow_pump_hook.py", "ready_mark_hook.py"}


def _entrypoints() -> list[Path]:
    out = []
    for f in sorted(TOOLS.glob("*.py")):
        if f.name.startswith("test_"):
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        has_main = any(
            isinstance(n, ast.If) and isinstance(n.test, ast.Compare) and getattr(n.test.left, "id", "") == "__name__"
            for n in tree.body
        )
        prints = any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "print" for n in ast.walk(tree))
        if has_main and prints and f.name not in NO_PRINT:
            out.append(f)
    return out


def test_every_printing_entrypoint_forces_utf8():
    missing = [f.name for f in _entrypoints() if 'reconfigure(encoding="utf-8")' not in f.read_text(encoding="utf-8")]
    assert missing == []


def test_msg_counter_is_tracked_in_the_tools_dir():
    assert (TOOLS / "msg_counter.py").is_file()


def test_msg_counter_prints_arabic_even_when_the_console_cannot(tmp_path):
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
    r = subprocess.run([sys.executable, str(TOOLS / "msg_counter.py"), "--help"], capture_output=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert "عدّادُ رسائل الجلسات" in r.stdout.decode("utf-8")
