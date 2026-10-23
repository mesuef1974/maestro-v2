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
pc.check_pre_commit_hook = _direct_ruff
pc.write_receipt = lambda: None
sys.exit(pc.main(sys.argv[1:]))
