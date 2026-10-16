#!/usr/bin/env python3
"""تحديثُ الطلبات المفتوحة آلياً بعد كل دمج في main (W-20261016-025، المكوّن F من خطة الفلو بلا لمس).

    python refresh_open.py [--repo owner/name] [--execute]

يقرأ الطلبات المفتوحة ويصنّفها بـ`mergeStateStatus`:
  BEHIND (خلف main)  → `gh pr update-branch <N>` (دمجُ main فقط) — ويُنبَّه بأنّ رأسه الجديد يلزمه `ledger.py waive-head` بتوقيع 0501 (D-154م)؛
  DIRTY  (تعارض)     → لا يلمسه: يُبلَّغ صاحبُ الطلب باسم الفرع والرقم؛
  غير ذلك             → لا إجراء.
الافتراضيّ ظلٌّ: يطبع ما كان سيفعله. التنفيذُ يحتاج `--execute` مع `REFRESH_OPEN_ENFORCE=1` معاً. لا يوقّع waive-head ولا يدمج ولا يتجاوز بوّابة.
رمز الخروج: 0 دائماً عند نجاح القراءة؛ 8 فشل gh.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

FIELDS = "number,headRefName,mergeStateStatus,title,isDraft"


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return p.returncode, p.stdout or ""


def list_open(repo: str | None, runner=run) -> list[dict] | None:
    cmd = ["gh", "pr", "list", "--state", "open", "--json", FIELDS, "--limit", "100"]
    if repo:
        cmd += ["--repo", repo]
    code, out = runner(cmd)
    if code != 0:
        return None
    try:
        return json.loads(out or "[]")
    except ValueError:
        return None


def classify(prs: list[dict]) -> dict[str, list[dict]]:
    """BEHIND يُحدَّث، DIRTY يُبلَّغ، والباقي يُترك (المسوّداتُ لا تُحدَّث)."""
    out: dict[str, list[dict]] = {"update": [], "conflict": [], "leave": []}
    for pr in prs:
        state = pr.get("mergeStateStatus", "")
        if pr.get("isDraft"):
            out["leave"].append(pr)
        elif state == "BEHIND":
            out["update"].append(pr)
        elif state == "DIRTY":
            out["conflict"].append(pr)
        else:
            out["leave"].append(pr)
    return out


def actions(groups: dict[str, list[dict]], repo: str | None) -> list[list[str]]:
    cmds = []
    for pr in groups["update"]:
        cmd = ["gh", "pr", "update-branch", str(pr["number"])]
        if repo:
            cmd += ["--repo", repo]
        cmds.append(cmd)
    return cmds


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args(argv)
    prs = list_open(a.repo)
    if prs is None:
        print("✘ تعذّرت قراءةُ الطلبات المفتوحة (gh).")
        return 8
    groups = classify(prs)
    live = a.execute and os.environ.get("REFRESH_OPEN_ENFORCE") == "1"
    print(
        f"{len(prs)} طلباً مفتوحاً: {len(groups['update'])} خلف main، {len(groups['conflict'])} متعارض، {len(groups['leave'])} بلا إجراء."
    )
    for pr in groups["conflict"]:
        print(
            f"⚠ تعارضٌ يُبلَّغ لصاحبه: #{pr['number']} ({pr['headRefName']}) — أعِد الأساسَ يدوياً."
        )
    for pr in groups["update"]:
        print(
            f"↻ #{pr['number']} ({pr['headRefName']}): بعد التحديث يلزمه ledger.py waive-head --kind main-merge بتوقيع 0501 (D-154م)."
        )
    cmds = actions(groups, a.repo)
    if not live:
        print("وضع الظلّ (لا تنفيذ) — الأوامر التي كان سينفّذها:")
        for c in cmds:
            print("  " + subprocess.list2cmdline(c))
        return 0
    for c in cmds:
        code, out = run(c)
        print(out.strip() or f"{c[3]}: رمز {code}")
        if code != 0:
            return 8
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
