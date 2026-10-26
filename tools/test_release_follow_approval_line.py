"""release_follow يجد ✔ في أيّ سطرٍ من مخرج approval_check لا في سطره الأوّل (بعد #56 صار الأوّل «المصدر المقروء: …»؛ وقع مع #1151)."""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parent / "release_follow.sh"
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="لا bash")


def _passed(output: str) -> bool:
    body = "\n".join(
        line for line in SCRIPT.read_text(encoding="utf-8").splitlines() if line.startswith("approval_passed()")
    )
    assert body, "الدالة غائبة من السكربت"
    # السكربتُ يُمرَّر بملفٍّ لا بوسيط سطر أوامر: ترميزُ الوسائط على Windows يفسد «✔»
    with tempfile.TemporaryDirectory() as d:
        sh = pathlib.Path(d) / "t.sh"
        sh.write_bytes((body + "\napproval_passed\n").encode("utf-8"))
        proc = subprocess.run(  # noqa: S603
            [shutil.which("bash"), sh.name],  # noqa: S607
            input=output.encode("utf-8"),
            capture_output=True,
            check=False,
            cwd=d,
        )
    return proc.returncode == 0


def test_check_mark_after_a_context_line_is_found():
    assert _passed("المصدر المقروء: C:/x/owner_confirmations.md (عُدّل 2026-10-19)\n✔ الاعتمادُ ثابتٌ")


def test_check_mark_on_the_first_line_still_passes():
    assert _passed("✔ الاعتمادُ ثابتٌ من المصدر")


def test_failure_after_a_context_line_is_not_a_pass():
    assert not _passed("المصدر المقروء: C:/x\n✘ الاعتمادُ على رأسٍ غيرِ رأس الإيداع")


def test_a_check_mark_quoted_inside_a_line_is_not_a_pass():
    """أسطرُ الأدلّة المقتبسة تذكر ✔ داخل نصٍّ؛ الحكمُ سطرٌ يبدأ به."""
    assert not _passed("✘ فشل\n  - owner_confirmations.md: | ... «✔ ...»")


def test_both_call_sites_use_the_helper_not_head_1():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "head -1 | grep" not in text
    assert text.count("| approval_passed") == 2
