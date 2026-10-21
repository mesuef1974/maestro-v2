"""اتجاهُ القول (الموجة 0.2، D-453م): سطرٌ نصُّه رفضٌ لا يُحسب اعتماداً ولو حمل البطاقةَ والرأس."""

from __future__ import annotations

from pathlib import Path

import approval_check as ac
import record_owner_confirmation as rc

CARD = "W-20261021-901"
HEAD = "abcdef12"


def _file(tmp_path: Path, quote: str) -> Path:
    f = tmp_path / "owner_confirmations.md"
    f.write_text(rc.row("0501", CARD, quote, "", head=HEAD, source="مباشر"), encoding="utf-8")
    return f


def test_refusal_line_is_not_approval(tmp_path):
    f = _file(tmp_path, "لا، ارفضه ولا تدمج")
    ev = ac.confirmations_evidence(CARD, HEAD, enforce=True, path=f)
    assert [st for _, st in ev] == ["rejected"]


def test_approving_rows_exclude_refusal(tmp_path, monkeypatch):
    f = _file(tmp_path, "لا، ارفضه ولا تدمج")
    monkeypatch.setattr(ac, "ROOT", f.parent)
    assert ac._approving_rows(CARD, HEAD) == []


def test_approval_line_still_ok(tmp_path):
    for q in ("اعتمد", "ادفع", "نعم أوقف الشرط", "لا مانع", "لا تعديل في الانتاج نجح التوليد ادفع اعتمد"):
        ev = ac.confirmations_evidence(CARD, HEAD, enforce=True, path=_file(tmp_path, q))
        assert [st for _, st in ev] == ["ok"], q


def test_refusal_variants():
    for q in ("لا", "لا تدمج قبل المعاينة", "لا تعتمد", "ارفضه", "مرفوض", "غير موافق", "لا، لا تعتمد"):
        assert ac.quote_refusal(q), q


def test_question_context_in_parentheses_is_ignored():
    assert not ac.quote_refusal("اعتمد (ردّاً على: هل ترفض هذا الرأس؟)")


def test_stale_head_stays_stale_even_if_refusal(tmp_path):
    ev = ac.confirmations_evidence(CARD, "99999999", enforce=True, path=_file(tmp_path, "لا، ارفضه"))
    assert [st for _, st in ev] == ["stale"]


REFUSALS = (
    "لا، ارفضه ولا تدمج", "لن أعتمد", "لا، لن أدمج", "أوقف ولا تدمج", "ليس الآن", "ليس بعد",
    "نعم (لكن لا تدمج حتى الصباح)", "لا ادفع", "لن أوافق", "لا، لا تدمج", "ولا تعتمد",
)
APPROVALS = (
    "اعتمد", "ادفع", "نعم أوقف الشرط", "لا مانع", "ولا مانع لدي", "لا تعديل في الانتاج نجح التوليد ادفع اعتمد",
    "اعتمد (رداً على: هل ترفض أو لا تدمج؟)", "نعم اعتمد (ردّاً على سؤال (هل لا تدمج؟))", "لا، اعتمد",
)


def test_refusal_forms_are_all_caught():
    assert [q for q in REFUSALS if not ac.quote_refusal(q)] == []


def test_sound_approvals_are_not_refused():
    assert [q for q in APPROVALS if ac.quote_refusal(q)] == []


def test_leading_no_is_overridden_only_by_an_explicit_separator():
    assert not ac.quote_refusal("لا، اعتمد")
    assert ac.quote_refusal("لا اعتمد")


def test_parenthesis_with_a_negation_is_not_ignored():
    assert ac.quote_refusal("نعم (لكن لا تدمج حتى الصباح)")
    assert not ac.quote_refusal("نعم (ردّاً على: هل لا تدمج؟)")


#: أقوالٌ حقيقيةٌ من owner_confirmations.md (لا يُقرأ الملفُّ الحيُّ: يتغيّر بقول المالك ويختلف بين الأشجار)
REAL_APPROVALS = (
    "لا تؤجل بلغ خفيفة (ردّاً على: W-047 على الرأس 04fafe7d هل تعتمد أم تؤجّل؟)",
    "لا تعديل الاسنادات في الانتاج نجح التوليد هيا ادفع اعتمد",
    "نعم أوقف الشرط وبلغ 0601 و0101",
    "اعتماد للكل من المالك هيا",
)


def test_real_owner_approvals_are_not_refused():
    assert [q for q in REAL_APPROVALS if ac.quote_refusal(q)] == []


def test_conditional_approval_with_no_merge_is_refused_on_purpose():
    assert ac.quote_refusal("اعتمده بالرأس bf4f8c7e ولا دمج قبل W-020 N1-N3")
