#!/usr/bin/env python3
"""حارسُ المخلّفات (W-20261014-001): قراءةٌ فقط؛ ينبّه (warn) أسبوعاً ثمّ يفشل (--strict) عند بقاء مخلّفات.

    python cleanup_guard.py            ينبّه ويخرج 0
    python cleanup_guard.py --strict   يخرج 1 إن تجاوزت المخلّفاتُ العتبات

العتبات: evidence القابل للتقليم >100 م، tmp_reports >0، شجرات عملٍ مدموجةٌ نظيفة >0.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prune_workspace as pw  # noqa: E402

EVIDENCE_MAX_BYTES = 100_000_000


def findings(res: dict) -> list[str]:
    out = []
    if res["evidence"]["bytes"] > EVIDENCE_MAX_BYTES:
        out.append(f"evidence قابلٌ للتقليم {res['evidence']['bytes'] // 1_000_000} م (الحدّ 100 م)")
    if res["tmp"]["files"]:
        out.append(f"tmp_reports فيه {res['tmp']['files']} ملفاً")
    if res["worktrees"]["candidates"]:
        out.append(f"شجراتُ عملٍ مدموجةٌ نظيفة: {len(res['worktrees']['candidates'])} — احذفها بـgit worktree remove")
    return out


def main() -> int:
    strict = "--strict" in sys.argv
    found = findings(pw.run(False))
    if not found:
        print("المخلّفات: نظيفة")
        return 0
    print("مخلّفات تحتاج تنظيفاً (كلُّ جلسةٍ مسؤولةٌ عن مخلّفاتها عند التسليم):")
    print(chr(10).join(f"- {f}" for f in found))
    print("الأمر: python C:/Users/mesue/delivery_manager_work/tools/prune_workspace.py (عرض) ثمّ --apply")
    return 1 if strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
