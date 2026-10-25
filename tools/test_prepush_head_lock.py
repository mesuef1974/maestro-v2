"""قفلُ الرأس في خطاف pre-push — بلا شبكة ولا git."""

from __future__ import annotations

import prepush_head_lock as hl

ITEMS = {"W-20261025-901": {"state": "approved", "approved_head": "abcdef12", "branch": "claude/x"},
         "W-20261025-902": {"state": "closed", "approved_head": "11111111", "branch": "claude/y"}}


def _line(sha, ref="refs/heads/claude/x"):
    return f"{ref} {sha} {ref} {'0' * 40}"


def test_other_head_on_locked_branch_is_rejected():
    out = hl.check_lines([_line("99999999" + "0" * 32)], ITEMS, subject_of=lambda s: "")
    assert out and "W-20261025-901" in out[0] and "abcdef12" in out[0]


def test_same_head_passes():
    assert hl.check_lines([_line("abcdef12" + "0" * 32)], ITEMS, subject_of=lambda s: "") == []


def test_closed_card_and_unbound_branch_pass():
    assert hl.check_lines([_line("9" * 40, "refs/heads/claude/y")], ITEMS, subject_of=lambda s: "") == []
    assert hl.check_lines([_line("9" * 40, "refs/heads/other")], ITEMS, subject_of=lambda s: "") == []


def test_card_id_in_subject_binds_when_branch_missing():
    out = hl.check_lines([_line("9" * 40, "refs/heads/other")], ITEMS, subject_of=lambda s: "W-20261025-901: عمل")
    assert out and "W-20261025-901" in out[0]


def test_branch_deletion_ignored():
    assert hl.check_lines([f"(delete) {'0' * 40} refs/heads/claude/x {'a' * 40}"], ITEMS) == []
