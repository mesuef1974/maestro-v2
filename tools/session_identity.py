#!/usr/bin/env python3
"""هويّةُ الجلسة عند كلّ بدء أو مسح (SessionStart hook) — قرارُ المالك 2026-10-04 (الحزمة أ).

يقرأ مجلّد العمل (cwd) من مدخل الـhook (JSON على stdin) ويطابق اسمَ شجرة العمل بـ`projects/schoolos/session_names.json`
فيطبع للجلسة: اسمَها ورقمَها وبطاقةَ دورها وأوّل ما تفعله. فلا تفقد الجلسةُ هويّتَها بعد المسح (واقعةُ 2026-10-04:
0301 رفضت العملَ، و0103 و0201 عرّفتا نفسيهما 04SS). لا يطبع شيئاً خارج أشجار المنصّة.

    python session_identity.py            # يقرأ stdin (مدخل الـhook)
    python session_identity.py --cwd <مسار>   # للاختبار اليدويّ
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = ROOT / "projects" / "schoolos" / "session_names.json"
PLATFORM = "shschool_mvp"


def tree_name(cwd: str) -> str | None:
    """اسمُ شجرة العمل من المسار: .../.claude/worktrees/<الاسم>[/…]؛ وإلا None."""
    parts = Path(cwd.replace("\\", "/")).parts
    for i, p in enumerate(parts):
        if p == "worktrees" and i + 1 < len(parts) and PLATFORM in "/".join(parts):
            return parts[i + 1]
    return None


def lookup(cwd: str, names: dict[str, str]) -> str | None:
    tree = tree_name(cwd)
    return names.get(tree) if tree else None


def message(title: str | None, tree: str | None) -> str:
    if title is None:
        return ("[هويّة الجلسة] لم أجد اسمَ هذه الشجرة (" + str(tree) + ") في session_names.json — "
                "اسأل 0101 عن رقمك قبل أيّ عمل، ولا تفترض أنّك مرنة 04SS.")
    m = re.match(r"\s*(\d{4})\b", title)
    num = m.group(1) if m else "؟؟؟؟"
    flexible = num.startswith("04")
    card = "role_cards/04.md (المرنة) ثمّ ledger.py show <رمز بطاقتك>" if flexible else f"role_cards/{num}.md"
    return (f"[هويّة الجلسة] أنت «{title}» — رقمُك {num}. "
            f"اقرأ بطاقتك `C:/Users/mesue/delivery_manager_work/{card}` ثمّ شغّل "
            f"`python C:/Users/mesue/delivery_manager_work/tools/my_state.py {num}` قبل أيّ ردّ. "
            + ("" if flexible else "لا تفترض أنّك مرنة 04SS. ")
            + "إن رأيت ما يناقض هذا فاسأل 0101 ولا تُكمل.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cwd")
    args = ap.parse_args()
    cwd = args.cwd
    if not cwd:
        try:
            cwd = json.loads(sys.stdin.read() or "{}").get("cwd", "")
        except Exception:  # noqa: BLE001 — الـhook لا يسقط الجلسة أبداً
            cwd = ""
    if not cwd or PLATFORM not in cwd.replace("\\", "/"):
        return 0
    tree = tree_name(cwd)
    if tree is None:
        return 0
    try:
        names = json.loads(NAMES.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        names = {}
    sys.stdout.reconfigure(encoding="utf-8")
    print(message(lookup(cwd, names), tree))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
