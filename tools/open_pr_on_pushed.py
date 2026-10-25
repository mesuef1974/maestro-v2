#!/usr/bin/env python3
"""غلافٌ رقيقٌ يُستدعى عند «pushed» فيفتح الطلب بسطر الاعتماد القياسيّ (W-20261020-016).

    python open_pr_on_pushed.py W-20261020-016 --repo <شجرة> [--branch claude/x] [--execute]

لا يكرّر منطقاً: يعيد استعمال `open_pr.main` (وفحوص `pr_open_prep` داخلها) كما هي. الافتراضيّ ظلٌّ
(يطبع الأوامر دون تنفيذ)، والتنفيذُ يحتاج `--execute` ومعه `OPEN_PR_ENFORCE=1` معاً، كما في `open_pr.py`.
رموزُ الخروج هي رموزُ `open_pr.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import open_pr  # noqa: E402


def open_after_push(card_id: str, repo: str, branch: str | None = None, execute: bool = False) -> int:
    argv = [card_id, "--repo", repo]
    if branch:
        argv += ["--branch", branch]
    if execute:
        argv.append("--execute")
    return open_pr.main(argv)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("card")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--branch")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args(argv)
    return open_after_push(a.card, a.repo, a.branch, a.execute)


if __name__ == "__main__":
    raise SystemExit(main())
