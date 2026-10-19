"""اختبارات حارس العربيّة tools/lang_guard.py (D-388م) — لا تغيّر وضع الحارس؛ الوضع يُحقن بمتغير البيئة."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lang_guard as lg  # noqa: E402


def test_arabic_sentence_passes():
    assert lg.is_english("أوقفتُ العمل على البطاقة بعد التحقق من القرار في السجل") is False


def test_english_sentence_is_flagged():
    assert lg.is_english("Waiting for the review to finish before pushing the change") is True


def test_arabic_with_command_mention_passes():
    # أمر لاتيني داخل جملة عربية طويلة لا يُسقطها (أربع كلمات لاتينية مقابل عربيّ غالب)
    assert lg.is_english("شغّل الأمر git push origin main من مجلد المايسترو ثم تحقق من الرأس البعيد") is False


def test_code_paths_urls_identifiers_excluded():
    text = "```\nwaiting for the review to finish now\n```\n`git status now please`\nhttps://example.com/a/b msg_counter.py D:/x/y/z"
    assert lg.is_english(text) is False


def test_below_min_words_not_flagged():
    # حدّ الأربع كلمات: ثلاث لاتينيّة بلا عربيّ لا تُعدّ إنجليزيّة (حدٌّ معروف يُقاس في أسبوع warn)
    assert lg.is_english("Run the tests") is False
    assert lg.is_english("Run all the tests") is True


def test_threshold_boundary_arabic_chars_vs_latin_words():
    # العتبة: أحرف عربيّة <= ضعف عدد الكلمات اللاتينيّة
    latin = "alpha beta gamma delta"  # 4 كلمات ← حدّ الأحرف العربيّة 8
    assert lg.is_english("ابحث " + latin) is True  # 4 أحرف عربيّة
    assert lg.is_english("ابحثوا عنها بسرعة " + latin) is False  # 14 حرفاً عربيّاً


def test_mode_env_overrides_and_defaults_to_warn(monkeypatch, tmp_path):
    monkeypatch.setattr(lg, "MODE_FILE", tmp_path / "absent.mode")
    monkeypatch.delenv("LANG_GUARD_MODE", raising=False)
    assert lg.mode() == "warn"
    monkeypatch.setenv("LANG_GUARD_MODE", "block")
    assert lg.mode() == "block"
    monkeypatch.setenv("LANG_GUARD_MODE", "bogus")
    assert lg.mode() == "warn"


def test_mode_file_invalid_value_falls_back_to_warn(monkeypatch, tmp_path):
    f = tmp_path / "lang_guard.mode"
    f.write_text("anything", encoding="utf-8")
    monkeypatch.setattr(lg, "MODE_FILE", f)
    monkeypatch.delenv("LANG_GUARD_MODE", raising=False)
    assert lg.mode() == "warn"
    f.write_text("block", encoding="utf-8")
    assert lg.mode() == "block"


def _transcript(tmp_path, entries):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries), encoding="utf-8")
    return str(p)


def _assistant(text):
    return {"message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def test_last_assistant_text_reads_latest_text(tmp_path):
    p = _transcript(tmp_path, [_assistant("نص قديم"), _assistant("Waiting for the review to finish now")])
    assert "Waiting" in lg.last_assistant_text(p)


def test_last_assistant_text_stops_at_user_turn(tmp_path):
    p = _transcript(tmp_path, [_assistant("Waiting for the review to finish now"),
                               {"message": {"role": "user", "content": "تابع"}}])
    assert lg.last_assistant_text(p) == ""


def test_last_assistant_text_missing_file_is_empty():
    assert lg.last_assistant_text("Z:/no/such/file.jsonl") == ""


def _run_main(monkeypatch, capsys, payload, mode):
    monkeypatch.setenv("LANG_GUARD_MODE", mode)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload, ensure_ascii=False)))
    rc = lg.main()
    return rc, capsys.readouterr().out


def test_main_warn_injects_context_without_denying(monkeypatch, capsys):
    rc, out = _run_main(monkeypatch, capsys, {"tool_input": {"description": "Waiting for the review to finish now"}}, "warn")
    assert rc == 0
    data = json.loads(out)["hookSpecificOutput"]
    assert "additionalContext" in data and "permissionDecision" not in data


def test_main_block_denies(monkeypatch, capsys):
    rc, out = _run_main(monkeypatch, capsys, {"tool_input": {"description": "Waiting for the review to finish now"}}, "block")
    assert rc == 0
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_main_arabic_is_silent(monkeypatch, capsys):
    rc, out = _run_main(monkeypatch, capsys, {"tool_input": {"description": "عرض حالة المستودع"}}, "block")
    assert rc == 0 and out == ""


@pytest.mark.parametrize("raw", ["", "not json", "{"])
def test_main_bad_input_never_fails_the_session(monkeypatch, capsys, raw):
    monkeypatch.setenv("LANG_GUARD_MODE", "block")
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    assert lg.main() == 0
    assert capsys.readouterr().out == ""


def _tr_one(tmp_path, text):
    p = tmp_path / "t.jsonl"
    p.write_text(json.dumps({"message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(p)


def test_block_three_word_description_denied(monkeypatch, capsys):
    """D-411م: وصف الأداة الإنجليزي ثلاث كلماتٍ فأكثر يُمنع."""
    _, out = _run_main(monkeypatch, capsys, {"tool_input": {"description": "Update message counter"}}, "block")
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_block_text_five_words_only_warns(monkeypatch, capsys, tmp_path):
    """نصٌّ بخمس كلماتٍ لاتينيّة تحذيرٌ لا منع."""
    t = _tr_one(tmp_path, "Now the new decision module.")
    _, out = _run_main(monkeypatch, capsys, {"tool_input": {"description": "عرض"}, "transcript_path": t}, "block")
    data = json.loads(out)["hookSpecificOutput"]
    assert "additionalContext" in data and "permissionDecision" not in data


def test_block_text_six_words_denied(monkeypatch, capsys, tmp_path):
    t = _tr_one(tmp_path, "Run the real generation again with early stop.")
    _, out = _run_main(monkeypatch, capsys, {"tool_input": {"description": "عرض"}, "transcript_path": t}, "block")
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
