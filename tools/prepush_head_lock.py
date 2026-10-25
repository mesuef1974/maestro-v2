#!/usr/bin/env python3
"""قفلُ الرأس عند الدفع (W-20261025-002، البند 2): يُستدعى من خطاف git pre-push فيرفض دفعَ رأسٍ يخالف الرأسَ المعتمَد لبطاقةٍ مربوطةٍ بالفرع.

يقرأ من stdin أسطرَ git: `<local ref> <local sha> <remote ref> <remote sha>`. البطاقةُ تُعرَف بحقل branch في الدفتر؛ وإلا برمز W-… في سطر
عنوان الإيداع المدفوع. المنفذُ الوحيد: `ledger.py waive-head` الموقّع من 0501 (ينقل approved_head إلى الرأس الجديد فيتطابقان).
الخروج: 0 سماح، 1 رفض مع سبب. لا شبكة ولا كتابة.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ledger  # noqa: E402

CARD_RE = re.compile(r"W-\d{8}-\d{3}")
LOCKED_STATES = ("approved", "pushed")
ZERO = "0" * 40


def _subject(sha: str) -> str:
    r = subprocess.run(["git", "log", "-1", "--format=%s", sha], capture_output=True, text=True, encoding="utf-8", check=False)
    return r.stdout if r.returncode == 0 else ""


def check_lines(lines: list[str], items: dict[str, dict], subject_of=_subject) -> list[str]:
    """يعيد قائمةَ أسباب الرفض (فارغةٌ = سماح)."""
    problems: list[str] = []
    for ln in lines:
        parts = ln.split()
        if len(parts) < 4 or parts[1] == ZERO:  # حذفُ فرعٍ لا يخصّ القفل
            continue
        sha, branch = parts[1], parts[2].removeprefix("refs/heads/")
        cards = {k for k, v in items.items() if v.get("branch") == branch and v.get("state") in LOCKED_STATES}
        if not cards:
            cards = {c for c in CARD_RE.findall(subject_of(sha)) if items.get(c, {}).get("state") in LOCKED_STATES}
        for cid in sorted(cards):
            want = (items[cid].get("approved_head") or "").strip()
            if want and not sha.startswith(want[:8]) and not want.startswith(sha[:8]):
                problems.append(f"{cid}: الرأسُ المدفوع {sha[:8]} يخالف المعتمَد {want[:8]} على {branch} — waive-head من 0501 أو اعتمادٌ جديد")
    return problems


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    items = ledger.reduce_state(ledger.load_events())
    problems = check_lines(sys.stdin.read().splitlines(), items)
    for p in problems:
        print("قفلُ الرأس: " + p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
