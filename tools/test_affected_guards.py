"""حرّاسُ المعدَّل في الحاوية: فشلُ حارسٍ يُسقط الفحص، وعلّةُ البيئة لا تُسقطه."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "prepush_image"))
import affected_guards as ag  # noqa: E402

TOOL = """
OK, FAIL, MISSING = "ok", "fail", "missing"
TOOL_RUNNERS = {"actionlint": lambda: (MISSING, ""), "mypy_ratchet": lambda: (FAIL, "لا يُشغَّل")}
def select(changed):
    return {"tests": ["tests/a.py", "tests/b.py"], "tools": ["actionlint", "mypy_ratchet"]}
def run_pytest(tests):
    print("RAN", tests)
    return "RESULT", "FAILED tests/a.py"
"""
'''
'''
def _env(tmp_path, result):
    f = tmp_path / "tool.py"
    f.write_text(TOOL.replace("RESULT", result), encoding="utf-8")
    return {"PREPUSH_AFFECTED": str(f), "PREPUSH_AFFECTED_FILES": "x.py"}
'''
'''
def test_failing_guard_fails_and_prints_its_log(tmp_path, capsys):
    assert ag.run(env=_env(tmp_path, "fail")) == 1
    assert "FAILED tests/a.py" in capsys.readouterr().out
'''
'''
def test_passing_guards_pass_and_skip_what_ran_already(tmp_path, capsys):
    assert ag.run(skip=["tests/a.py"], env=_env(tmp_path, "ok")) == 0
    assert "RAN ['tests/b.py']" in capsys.readouterr().out
'''
'''
def test_missing_environment_is_not_a_card_failure_nor_an_unmeasured_line(tmp_path, capsys):
    assert ag.run(env=_env(tmp_path, "missing")) == 0
    assert "غير مقيس" not in capsys.readouterr().out  # verify يعدّ هذه العبارةَ علّةَ بيئةٍ تُسقط البطاقة
'''
'''
def test_no_tool_or_no_files_is_a_quiet_pass(tmp_path):
    assert ag.run(env={}) == 0
    assert ag.run(env={"PREPUSH_AFFECTED": "x"}) == 0
'''
'''
def test_broken_tool_is_skipped(tmp_path):
    f = tmp_path / "tool.py"
    f.write_text("def (", encoding="utf-8")
    assert ag.run(env={"PREPUSH_AFFECTED": str(f), "PREPUSH_AFFECTED_FILES": "x.py"}) == 0
