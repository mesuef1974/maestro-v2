"""خلاصةُ فشل pytest: الأسبابُ الفريدة تصل النموذجَ ولو ملأت الأسماءُ ذيلَ السجلّ."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "prepush_image"))

from fail_digest import failure_digest  # noqa: E402

NL = chr(10)


def test_unique_causes_survive_a_tail_full_of_test_names():
    body = NL.join(["tests/test_a.py:12: in setup", "E   django.db.utils.ProgrammingError: relation x does not exist"] * 40)
    names = NL.join("ERROR tests/test_a.py::T::test_%03d" % i + " " * 60 for i in range(60))
    out = failure_digest(body + NL + names + NL + "5 failed, 33 errors in 95s")
    assert out.count("ProgrammingError: relation x does not exist") >= 1 and out.index("ProgrammingError") < 200
    assert out.endswith("5 failed, 33 errors in 95s") and len(out) <= 3700


def test_a_log_without_causes_is_just_its_tail():
    assert failure_digest("x" * 5000) == "x" * 3600
