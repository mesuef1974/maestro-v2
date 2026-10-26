"""استخراجُ بطاقة الطلب تلقائياً في `approval_check pr` (W-20261017-018، قرار المالك 2026-10-17).

الترتيب: اسمُ الفرع ثمّ العنوان ثمّ الوصف؛ أوّلُ معرّفٍ يُعتمد، وتعارضُ معرّفين في المصدر الواحد يُرفض ولا يُخمَّن،
وغيابُه يبقى «لا بطاقة». لا gh حقيقيّ: `run` يُستبدل بردٍّ مصنوع.
"""

from __future__ import annotations

import json

import approval_check as ac

CARD = "W-20261017-018"
OTHER = "W-20261017-016"


def _pr(branch="", title="", body="", head="abcdef1234567890"):
    return {
        "headRefName": branch,
        "title": title,
        "body": body,
        "state": "OPEN",
        "headRefOid": head,
    }


def _patch(monkeypatch, d):
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (0, json.dumps(d)))


def test_id_in_the_branch_alone_is_enough(monkeypatch):
    _patch(monkeypatch, _pr(branch=f"claude/{CARD}-pr-card"))
    ev, card, head = ac.pr_evidence("7")
    assert card == CARD and head == "abcdef12"


def test_id_in_the_title_alone(monkeypatch):
    _patch(monkeypatch, _pr(branch="claude/x", title=f"fix: شيء ({CARD})"))
    assert ac.pr_evidence("7")[1] == CARD


def test_id_in_the_description_alone(monkeypatch):
    _patch(monkeypatch, _pr(branch="claude/x", title="fix", body=f"البطاقة {CARD}"))
    assert ac.pr_evidence("7")[1] == CARD


def test_two_different_ids_in_one_source_are_rejected_with_a_message(monkeypatch):
    _patch(monkeypatch, _pr(title=f"{CARD} و{OTHER}"))
    ev, card, _ = ac.pr_evidence("7")
    assert card is None
    assert (
        len(ev) == 1
        and ev[0][1] == "conflict"
        and CARD in ev[0][0]
        and OTHER in ev[0][0]
        and "العنوان" in ev[0][0]
    )


def test_no_id_anywhere_stays_no_card(monkeypatch):
    _patch(monkeypatch, _pr(branch="claude/x", title="fix", body="لا شيء"))
    ev, card, _ = ac.pr_evidence("7")
    assert card is None and ev == []


def test_branch_wins_over_title_and_the_same_id_repeated_is_not_a_conflict(monkeypatch):
    _patch(monkeypatch, _pr(branch=f"claude/{CARD}", title=f"{OTHER} {OTHER}"))
    assert ac.pr_evidence("7")[1] == CARD
    _patch(monkeypatch, _pr(title=f"{CARD} ثمّ {CARD}"))
    assert ac.pr_evidence("7")[1] == CARD


def test_a_conflict_makes_the_command_fail_and_names_the_ids(monkeypatch, capsys):
    _patch(monkeypatch, _pr(branch=f"claude/{CARD}-{OTHER}"))
    monkeypatch.setattr("sys.argv", ["approval_check.py", "pr", "7"])
    assert ac.main() == 3
    out = capsys.readouterr().out
    assert "تعارضُ بطاقات" in out and CARD in out and OTHER in out


def test_owner_lines_recorded_under_the_card_name_are_found_for_a_pr(
    monkeypatch, capsys
):
    """الغايةُ: طلبٌ بلا معرّف البطاقة في عنوانه/وصفه لكنّ فرعه يحملها => أسطرُ الاعتماد باسم البطاقة تُرى."""
    _patch(monkeypatch, _pr(branch=f"claude/{CARD}"))
    seen: list[str] = []

    def fake_conf(key, pr_head=None, **kw):
        seen.append(key)
        return [(f"owner_confirmations.md: {key}", "ok")] if key == CARD else []

    monkeypatch.setattr(ac, "confirmations_evidence", fake_conf)
    monkeypatch.setattr(ac, "card_evidence", lambda *a, **k: [])
    monkeypatch.setattr(ac, "waiver_carry", lambda *a, **k: [])
    monkeypatch.setattr(ac, "visual_problem", lambda *a, **k: None)
    monkeypatch.setattr("sys.argv", ["approval_check.py", "pr", "7"])
    assert ac.main() == 0 and CARD in seen and "7" in seen
    assert "✔" in capsys.readouterr().out


def test_gh_failure_still_returns_nothing(monkeypatch):
    monkeypatch.setattr(ac, "run", lambda cmd, cwd=None: (1, ""))
    assert ac.pr_evidence("7") == ([], None, None)


def test_repo_option_is_passed_to_gh(monkeypatch):
    seen = []

    def fake(cmd, cwd=None):
        seen.append(cmd)
        return 0, json.dumps(_pr(branch=f"claude/{CARD}-x"))

    monkeypatch.setattr(ac, "run", fake)
    ac.pr_evidence("7", "mesuef1974/maestro-v2")
    assert seen[-1][-2:] == ["--repo", "mesuef1974/maestro-v2"]
    ac.pr_evidence("7")
    assert "--repo" not in seen[-1]
