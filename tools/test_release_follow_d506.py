"""W-20261101-003 (D-506م وD-507م): release_follow لا يشترط كلمة المالك لاعتماد الرأس ولا للهجرة، وينشر عاجلاً بسببٍ مدوَّن."""

import pathlib

TEXT = (pathlib.Path(__file__).resolve().parent / "release_follow.sh").read_text(encoding="utf-8")


def test_approval_line_of_0101_is_accepted_beside_the_owner_form():
    assert 'اعتُمد من المالك على 8500"*"الرأس $S"*)' in TEXT
    assert 'اعتمد 0101"*"الرأس $S"*)' in TEXT


def test_migration_no_longer_needs_a_direct_owner_word():
    assert "لا يكمل بلا كلمة مالكٍ جديدة" not in TEXT
    assert "مباشر" + chr(92) + "|مباشر" not in TEXT


def test_urgent_label_with_recorded_reason_replaces_the_owner_window_order():
    assert 'startswith("نشر-عاجل:")' in TEXT and "D-507م" in TEXT
    assert "window_order_present" in TEXT  # سطرُ المالك يبقى بديلاً مقبولاً
