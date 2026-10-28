"""الشرط السابع لحسابات المعاينة (W-20261003-022): حارسُ الربط والقاعدة، و`down` لا يحذف الحسابات."""

import importlib.util
import os
import pathlib
import sys
from unittest import mock

import pytest

SRC = pathlib.Path(__file__).with_name("w020_preview_seed.py")
STUBS = ("django", "django.db", "django.utils", "django.conf", "core", "core.models", "operations", "operations.attendance_entries", "operations.models")


def _load(monkeypatch):
    """يحمّل الأداةَ بلا Django (تُشغَّل داخل الحاوية)؛ W020_ACTION فارغ فلا يُنفَّذ شيء عند الاستيراد."""
    for name in STUBS:
        monkeypatch.setitem(sys.modules, name, mock.MagicMock())
    # `@transaction.atomic` يجب أن يعيد الدالةَ نفسَها وإلّا صارت down() مجسّاً فارغاً واختبارُها بلا معنى
    sys.modules["django.db"].transaction.atomic = lambda func: func
    monkeypatch.setenv("W020_ACTION", "")
    spec = importlib.util.spec_from_file_location("w020_under_test", SRC)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_guard_accepts_loopback_and_matching_preview_db(monkeypatch):
    m = _load(monkeypatch)
    assert m.guard_problems("127.0.0.1", "schoolos_preview_1", "schoolos_preview_1") == []


@pytest.mark.parametrize(
    "bind,expected,actual",
    [
        ("0.0.0.0", "schoolos_preview_1", "schoolos_preview_1"),
        ("", "schoolos_preview_1", "schoolos_preview_1"),
        ("127.0.0.1", "", "schoolos_preview_1"),
        ("127.0.0.1", "schoolos_preview_1", "schoolos_prod"),
        ("127.0.0.1", "schoolos_prod", "schoolos_prod"),
    ],
)
def test_guard_rejects_any_unsafe_combination(monkeypatch, bind, expected, actual):
    m = _load(monkeypatch)
    assert m.guard_problems(bind, expected, actual)


def test_accounts_refuses_and_disables_when_guard_fails(monkeypatch):
    m = _load(monkeypatch)
    monkeypatch.setenv("PREVIEW_BIND", "0.0.0.0")
    monkeypatch.setenv("PREVIEW_DB_NAME", "schoolos_preview_1")
    settings = sys.modules["django.conf"].settings
    settings.DATABASES = {"default": {"NAME": "schoolos_preview_1"}}
    users = mock.MagicMock()
    monkeypatch.setattr(m, "_fake_users", lambda: users)
    monkeypatch.setattr(m, "_marked", mock.MagicMock(side_effect=AssertionError("لا بذرَ بعد الرفض")))
    with pytest.raises(SystemExit) as exit_info:
        m.accounts()
    assert exit_info.value.code == 3
    users.filter.assert_called_once_with(is_active=True)
    users.filter.return_value.update.assert_called_once_with(is_active=False)


def test_down_keeps_fake_accounts(monkeypatch):
    m = _load(monkeypatch)
    assert not hasattr(m, "_remove_fake_accounts")
    monkeypatch.setattr(m, "_marked", lambda: [])
    monkeypatch.setattr(m, "_restore_wing_supervisors", lambda sessions: None)
    users = mock.MagicMock()
    monkeypatch.setattr(m, "_fake_users", lambda: users)
    m.AttendanceEntry.objects.filter.return_value.select_related.return_value = []
    m.StudentAttendance.objects.filter.return_value.delete.return_value = (0, {})
    m.down()
    users.delete.assert_not_called()
    users.filter.assert_not_called()
