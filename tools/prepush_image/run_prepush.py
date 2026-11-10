"""يعمل داخل حاوية maestro-prepush (W-20261023-016): يشغّل scripts/prepush_check.py للمنصّة كما هو بلا إضعاف أيّ حارس.

الفرقُ الوحيد عن التشغيل على المضيف:
  - لا pre-commit في الحاوية: حارسا ruff يُشغَّلان مباشرةً (`ruff check` و`ruff format --check` بإصدار CI نفسه 0.4.4) —
    شرطُ النجاح واحد (صفر مخالفة)، بلا --fix فالنسخةُ للقراءة فقط.
  - GIT_DIR (مجلّد .git الرئيس المركَّب للقراءة) يُمرَّر عبر PREPUSH_GIT_DIR لكلّ أمرٍ سوى pytest؛ فاختباراتٌ تنشئ مستودعاتٍ مؤقّتة
    (git init) لا ترث مستودعاً للقراءة فقط.
  - كتابةُ الإيصال مُعطَّلة هنا (الشجرةُ مركَّبة للقراءة)؛ المضخّةُ تكتبه من المضيف بعد رمز خروج 0 وحده.
رمز الخروج هو رمز prepush_check نفسه: 0 نجاح كاملٌ بلا «غير مقيس»، 1 فشل، 3 غير مقيس.
"""

from __future__ import annotations

import os
import subprocess
import time
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
sys.path.insert(0, os.getcwd())
import prepush_check as pc  # noqa: E402

RUFF = {
    "ruff": ["ruff", "check", "--no-cache", "."],
    "ruff-format": ["ruff", "format", "--check", "--no-cache", "."],
}


def _direct_ruff(hook_id: str):
    def run():
        proc = subprocess.run(RUFF[hook_id], capture_output=True, text=True, encoding="utf-8", errors="replace")
        return (pc.OK, "") if proc.returncode == 0 else (pc.FAIL, pc._tail(proc))

    return run


os.environ.update(pc.MYPY_ENV)  # قيمُ اختبارٍ عامّةٌ منسوخةٌ من quality-gate.yml: بيئةُ الحرّاس كبيئة CI
_orig_run = pc._run


def _scoped_git_run(cmd, env=None, timeout=None):
    """GIT_DIR لكلّ أمرٍ سوى pytest (git وdetect-secrets وسكربتات scripts/ تقرأ git)؛ وpytest بلا GIT_DIR فلا تبني اختباراتُه المستودعاتِ المؤقّتة فوقه."""
    git_dir = os.environ.get("PREPUSH_GIT_DIR")
    env = dict(env or {})
    if git_dir and "pytest" not in cmd:
        env["GIT_DIR"] = git_dir
        env["GIT_WORK_TREE"] = os.getcwd()
    return _orig_run(cmd, env, timeout)


pc._run = _scoped_git_run
import check_migration_collisions as cmc  # noqa: E402 — من scripts/ المنصّة (في sys.path أعلاه)
import git_open_prs  # noqa: E402 — بجوار هذا الملف (/runner)

pc.check_migration_collisions = lambda: git_open_prs.check(pc, cmc)  # صورةٌ بلا gh: فروعُ git بدل gh pr list (W-20261026-014)


def _timed(name, fn):
    """يطبع زمنَ كلّ فحصٍ بسطرٍ [timing] يجمعه المشغّل في ledger/prepush_timing.log."""
    def run(*a, **k):
        start = time.monotonic()
        out = fn(*a, **k)
        print(f"[timing] {name} {time.monotonic() - start:.0f}s", flush=True)
        return out
    return run


pc.check_pre_commit_hook = lambda hook_id: _timed(hook_id, _direct_ruff(hook_id))
for _name in ("check_personal_data", "check_secrets", "check_complexity", "check_identity", "check_structure", "check_migration_collisions", "check_types"):
    if hasattr(pc, _name):
        setattr(pc, _name, _timed(_name, getattr(pc, _name)))
pc.write_receipt = lambda: None
if os.environ.get("PREPUSH_BUILD_DB"):
    # قاعدةٌ نظيفةٌ تُحفظ قبل أيّ اختبارٍ حقيقيّ: اختباراتُ المعاملات تفرّغ الجداولَ فلا يصلح ما بعدها للحفظ
    probe = "tests/test_zz_build_db.py"
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write("import pytest" + chr(10) + chr(10) + chr(10) + "@pytest.mark.django_db" + chr(10) + "def test_build():" + chr(10) + "    pass" + chr(10))
    sys.exit(subprocess.run([sys.executable, "-m", "pytest", probe, "-q", "-p", "no:cacheprovider", "--no-header", "--reuse-db", "--create-db"]).returncode)
rc = pc.main(sys.argv[1:])
# اختباراتٌ تذكر ما عدّله النموذج (PREPUSH_EXTRA_TESTS من runner.referenced_tests): بعد نجاح prepush وفي الحاوية نفسها؛
# فشلُها فشلُ الفحص (رمز 1) لا «غير مقيس». prepush وحده ثابتٌ فلا يرى كسرَ مستعمِلٍ لم يُفتح (#1338).
extra = os.environ.get("PREPUSH_EXTRA_TESTS", "").split()
if rc == 0 and extra:
    print(f"… اختباراتٌ تذكر المعدَّل ({len(extra)})", flush=True)
    extra_start = time.monotonic()
    reuse = ["--reuse-db"] if os.environ.get("PREPUSH_REUSE_DB") else []
    proc = subprocess.run([sys.executable, "-m", "pytest", *extra, "-q", "-p", "no:cacheprovider", "--no-header", *reuse],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    from fail_digest import failure_digest  # noqa: E402, PLC0415 — بجوار هذا الملف (/runner)

    sys.stdout.write(failure_digest(proc.stdout + proc.stderr))
    print(f"[timing] extra_tests {time.monotonic() - extra_start:.0f}s", flush=True)
    if proc.returncode != 0:
        rc = 1
if rc == 0:
    import affected_guards  # noqa: E402 — بجوار هذا الملف (/runner)

    rc = affected_guards.run(skip=extra)
sys.exit(rc)
