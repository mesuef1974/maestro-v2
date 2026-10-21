"""release_follow يحكم على الفحصين المطلوبين وحدَهما (W-20261020-017): أحمرٌ استشاريٌّ أو معلَّقٌ لا يوقف المتابعة ولا يُنتظر."""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parent / "release_follow.sh"
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="لا bash")

QUALITY = "ملخص بوابة الجودة"
SECURITY = "Security Summary"


def _verdict(tmp_path: pathlib.Path, *rows: tuple[str, str]) -> str:
    """يمرّر مخرجاً بصيغة `gh pr checks` (اسم⇥حالة⇥مدّة⇥رابط) إلى required_verdict كما هي في السكربت."""
    body = "\n".join(
        line
        for line in SCRIPT.read_text(encoding="utf-8").splitlines()
        if line.startswith("required_verdict()")
    )
    assert body, "الدالة غائبة من السكربت"
    text = "".join(f"{name}\t{state}\t1s\thttps://x\n" for name, state in rows)
    # ملفٌّ لا وسيطُ سطر أوامر: العربيّةُ في الوسيط تتشوّه على ويندوز فيفشل awk
    script = tmp_path / "verdict.sh"
    script.write_text(body + "\nrequired_verdict\n", encoding="utf-8", newline="\n")
    proc = subprocess.run(  # noqa: S603
        [shutil.which("bash"), script.as_posix()],  # noqa: S607
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return proc.stdout.strip()


def test_required_green_passes_despite_advisory_red(tmp_path):
    assert (
        _verdict(
            tmp_path,
            (QUALITY, "pass"),
            (SECURITY, "pass"),
            ("سطرُ الاعتماد مطابقٌ للرأس", "fail"),
        )
        == "PASS"
    )


def test_required_green_passes_despite_advisory_pending(tmp_path):
    assert (
        _verdict(
            tmp_path,
            (QUALITY, "pass"),
            (SECURITY, "pass"),
            ("Playwright — e2e", "pending"),
        )
        == "PASS"
    )


def test_required_red_fails_even_if_the_rest_is_green(tmp_path):
    assert (
        _verdict(tmp_path, (QUALITY, "fail"), (SECURITY, "pass"), ("Ruff", "pass"))
        == "FAIL"
    )
    assert _verdict(tmp_path, (QUALITY, "pass"), (SECURITY, "fail")) == "FAIL"


def test_required_pending_waits(tmp_path):
    assert _verdict(tmp_path, (QUALITY, "pending"), (SECURITY, "pass")) == "PENDING"


def test_required_not_reported_yet_waits(tmp_path):
    """فحصٌ مطلوبٌ لم يظهر بعدُ ليس أخضر: لا دمج على غيابه."""
    assert _verdict(tmp_path, (QUALITY, "pass"), ("Ruff", "pass")) == "PENDING"
    assert _verdict(tmp_path) == "PENDING"


def test_fail_beats_pending(tmp_path):
    assert _verdict(tmp_path, (QUALITY, "fail"), (SECURITY, "pending")) == "FAIL"


def test_the_script_no_longer_waits_on_every_check():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "grep -Eq 'pending|queued|in_progress'" not in text
    assert "required_verdict" in text
