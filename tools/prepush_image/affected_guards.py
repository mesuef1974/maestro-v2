"""حرّاسُ الملفّات المعدَّلة بجدول `scripts/affected_tests.py` من main، داخل حاوية prepush.

الأداةُ تُستورد ولا تُشغَّل بسطر أوامرها: هي تقارن المودَعَ وحده (`base...HEAD`)، وتعديلُ النموذج غيرُ مودَعٍ
وقت الفحص، ومستودعُ الحاوية للقراءة فقط فلا يُودَع فيها. فالمشغّلُ يمرّر قائمةَ الملفّات، والاختيارُ والتشغيلُ منها.
نسخةُ main لا الفرع: فرعٌ يعدّل جدولَها لا يُعفي نفسَه. وعلّةُ البيئة (الخروج 3 في الأداة) تخطٍّ لا فشل.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time

SKIP_TOOLS = ("mypy_ratchet",)  # سقّاطةُ الأنواع يشغّلها prepush نفسُه قبل هذه الخطوة


def load(path: str):
    spec = importlib.util.spec_from_file_location("affected_tests_main", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _judge(aff, name: str, status: str, detail: str) -> int:
    if status == aff.FAIL:
        print(f"✘ {name}: فشل\n{detail}", flush=True)
        return 1
    if status != aff.OK:
        print(f"[affected] {name}: تخطٍّ لعلّة بيئة", flush=True)
    return 0


def run(skip=(), env=None) -> int:
    """0 نجح أو تُخطّي، 1 حارسٌ فشل فيعود سجلُّه إلى النموذج."""
    env = os.environ if env is None else env
    path = env.get("PREPUSH_AFFECTED")
    changed = sorted(f for f in env.get("PREPUSH_AFFECTED_FILES", "").split("\n") if f)
    if not path or not changed:
        return 0
    try:
        aff = load(path)
        plan = aff.select(changed)
    except Exception as exc:  # noqa: BLE001 — أداةٌ لا تُقرأ لا تُسقط بطاقةً سليمة
        print(f"[affected] تخطٍّ: {type(exc).__name__}", flush=True)
        return 0
    tests = [t for t in plan["tests"] if t not in skip]
    tools = [t for t in plan["tools"] if t not in SKIP_TOOLS]
    started, rc = time.monotonic(), 0
    print(f"… حرّاسُ المعدَّل من main ({len(tests)})", flush=True)
    if tests:
        if env.get("PREPUSH_REUSE_DB"):
            os.environ["PYTEST_ADDOPTS"] = "--reuse-db"  # الأداةُ تبني أمرَ pytest بنفسها، وقاعدةُ الفحص جاهزة
        rc |= _judge(aff, "pytest", *aff.run_pytest(tests))
    for tool in tools:
        rc |= _judge(aff, tool, *aff.TOOL_RUNNERS[tool]())
    print(f"[timing] affected {time.monotonic() - started:.0f}s", flush=True)
    return rc
