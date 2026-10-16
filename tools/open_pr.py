#!/usr/bin/env python3
"""فتحُ طلب الدمج آلياً بسطر اعتماد مولَّد من الدفتر (W-20261016-024، المكوّن E من خطة الفلو بلا لمس).

    python open_pr.py W-20261016-024 --repo <شجرة> [--branch claude/x] [--title "..."]

الافتراضيّ ظلٌّ (--dry-run): يطبع أوامر gh التي كان سينفّذها دون تنفيذ. التنفيذُ الفعليّ يحتاج `--execute`
ومعه `OPEN_PR_ENFORCE=1` معاً (قرارٌ بعد أسبوع الظلّ ومقارنته بما فعلته 0601).

لا يعتمد ولا يتجاوز approval_check: يمرّ على `pr_open_prep.py` كاملاً (الرأسُ مدفوعٌ ومطابق، والاعتمادُ ثابتٌ لهذا الرأس بعينه،
ولا تعارضَ مع الأساس) وأيُّ فشلٍ يوقفه برمزه. ولا يدمج: يضع الطلبَ في طابور الدمج (`gh pr merge --auto`) وتبقى البوّاباتُ هي الحَكَم.
رموز الخروج: 0 سليم، رموز pr_open_prep (3 اعتمادٌ غيرُ ثابت، 4 غيرُ مدفوع، 5 تعارض)، 7 طلبٌ مفتوحٌ لهذا الفرع أصلاً، 8 فشل gh.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pr_open_prep  # noqa: E402

TITLE_MAX = 70


def run(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    return pr_open_prep.run(cmd, cwd)


def current_branch(repo: str) -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)[1].strip()


def make_title(card: dict, card_id: str, override: str | None) -> str:
    if override:
        return override[:TITLE_MAX]
    problem = (
        str(card.get("problem", "")).strip().splitlines()[0]
        if card.get("problem")
        else ""
    )
    return (f"{problem} ({card_id})" if problem else card_id)[:TITLE_MAX]


def make_body(line: str, card_id: str) -> str:
    return f"{line}\n\nالبطاقة: {card_id}\n\nفُتح آلياً بـopen_pr.py بعد approval_check ✔ للرأس نفسه."


def open_pr_for_branch(branch: str, repo: str, runner=run) -> str:
    """رابطُ طلبٍ مفتوحٍ لهذا الفرع إن وُجد، وإلا فارغ."""
    code, out = runner(
        ["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "url"], repo
    )
    if code != 0:
        return ""
    try:
        rows = json.loads(out or "[]")
    except ValueError:
        return ""
    return rows[0]["url"] if rows else ""


def plan(
    card_id: str,
    repo: str,
    branch: str,
    base: str,
    title: str | None,
    no_fetch: bool,
    runner=run,
) -> tuple[int, list[list[str]], str]:
    """(رمز، أوامر gh المطلوبة، رسالة). لا ينفّذ gh pr create بل يجهّزه بعد فحوص pr_open_prep كاملةً."""
    prep = [
        sys.executable,
        str(HERE / "pr_open_prep.py"),
        card_id,
        "--repo",
        repo,
        "--branch",
        branch,
        "--base",
        base,
    ]
    if no_fetch:
        prep.append("--no-fetch")
    code, out = runner(prep + ["--line-only"])
    if code != 0:
        return code, [], out.strip()
    line = out.strip().splitlines()[-1]
    existing = open_pr_for_branch(branch, repo, runner)
    if existing:
        return 7, [], f"طلبٌ مفتوحٌ لهذا الفرع أصلاً: {existing}"
    card = pr_open_prep.ledger_card(card_id)
    create = [
        "gh", "pr", "create", "--base", base.split("/")[-1], "--head", branch,
        "--title", make_title(card, card_id, title), "--body", make_body(line, card_id),
    ]  # fmt: skip
    queue = ["gh", "pr", "merge", branch, "--auto", "--squash"]
    return 0, [create, queue], line


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("card")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--branch")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--title")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument(
        "--execute", action="store_true", help="نفّذ فعلاً (مع OPEN_PR_ENFORCE=1)"
    )
    a = ap.parse_args(argv)
    branch = a.branch or current_branch(a.repo)
    code, cmds, msg = plan(a.card, a.repo, branch, a.base, a.title, a.no_fetch)
    if code != 0:
        print(f"✘ لا يُفتح طلب: {msg}")
        return code
    live = a.execute and os.environ.get("OPEN_PR_ENFORCE") == "1"
    print(f"✔ فحوصُ pr_open_prep سليمة — سطر الاعتماد: {msg}")
    if not live:
        print("وضع الظلّ (لا تنفيذ) — الأوامر التي كان سينفّذها:")
        for c in cmds:
            print("  " + subprocess.list2cmdline(c))
        return 0
    for c in cmds:
        rc, out = run(c, a.repo)
        print(out.strip())
        if rc != 0:
            print(f"✘ فشل: {c[:3]}")
            return 8
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
