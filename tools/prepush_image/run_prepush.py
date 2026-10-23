"""يعمل داخل حاوية maestro-prepush (W-20261023-016): يشغّل scripts/prepush_check.py للمنصّة كما هو بلا إضعاف أيّ حارس.

الفرقُ الوحيد عن التشغيل على المضيف:
  - لا pre-commit في الحاوية: حارسا ruff يُشغَّلان مباشرةً (`ruff check` و`ruff format --check` بإصدار CI نفسه 0.4.4) —
    شرطُ النجاح واحد (صفر مخالفة)، بلا --fix فالنسخةُ للقراءة فقط.
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
pc.check_pre_commit_hook = _direct_ruff
pc.write_receipt = lambda: None
sys.exit(pc.main(sys.argv[1:]))
