#!/usr/bin/env python3
"""حكمُ «هل في هذه الشجرة عملٌ معلَّق؟» بحالة طلب فرعها في GitHub — لا بعدّ الإيداعات.

لماذا: الدمجُ بالسحق (squash) يصنع إيداعاً واحداً جديداً في main، فيبقى كلُّ إيداعٍ في الفرع «غيرَ مدموج»
في `git rev-list origin/main..HEAD` وفي `git cherry` (بصمةُ الإيداع المجمَّع تختلف عن بصمات أجزائه).
فكانت الأشجارُ التي اندمج عملُها تُعلَن يتيمةً (قياس 2026-09-28: vision-footer ← #714، qcc-collectors ← #707).

القاعدة: رأسُ الشجرة هو رأسُ طلبٍ مدموجٍ أو سلفُه ⇒ لا عملَ معلَّقاً (إلّا ملفّاتٍ غيرَ مودَعة).
"""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Callable

# الحالات (بالأولويّة)؛ PENDING = ما يستحقّ تنبيهاً أو يمنع الأرشفة
OPEN_PR = "open_pr"                 # طلبٌ مفتوح — العملُ له صاحبٌ وطريق
MERGED = "merged"                   # اندمج ولا شيءَ بعده
MERGED_DIRTY = "merged_dirty"       # اندمج لكن في الشجرة ملفّاتٌ غيرُ مودَعة
MERGED_ELSEWHERE = "merged_elsewhere"  # بلا طلبٍ على فرعه، لكنّ رأسَه داخل طلبٍ مدموجٍ من فرعٍ آخر
WORK_AFTER_MERGE = "work_after_merge"  # إيداعاتٌ فوق رأس طلبٍ مدموج
CLOSED_UNMERGED = "closed_unmerged"  # طلبٌ أُغلق بلا دمج وفي الفرع إيداعات
NO_PR = "no_pr"                     # إيداعاتٌ أو تعديلاتٌ بلا أيّ طلب
CLEAN = "clean"                     # لا إيداعَ خارج main ولا تعديل
PENDING = {MERGED_DIRTY, WORK_AFTER_MERGE, CLOSED_UNMERGED, NO_PR}

LABEL_AR = {
    OPEN_PR: "طلبٌ مفتوح",
    MERGED: "اندمج بطلبه",
    MERGED_DIRTY: "اندمج وفيه ملفّاتٌ غيرُ مودَعة",
    MERGED_ELSEWHERE: "اندمج عبر طلب فرعٍ آخر",
    WORK_AFTER_MERGE: "إيداعاتٌ بعد دمج طلبه",
    CLOSED_UNMERGED: "طلبٌ مغلقٌ بلا دمج",
    NO_PR: "عملٌ بلا طلب",
    CLEAN: "نظيفة",
}


def classify_tree(head: str, branch: str, ahead: int, dirty: int, prs: list[dict],
                  contains: Callable[[str, str], bool], elsewhere: list[int] | None = None) -> dict:
    """حكمٌ نقيّ. prs: طلباتُ هذا الفرع [{number, state, headRefOid}]؛ contains(a, b) = a سلفٌ لـb (أو يساويه)؛
    elsewhere: طلباتٌ مدموجةٌ من فروعٍ أخرى رأسُها يحوي رأسَ الشجرة (تُحسب خارجاً لأنّها مكلفة)."""
    opened = sorted(p["number"] for p in prs if p["state"] == "OPEN")
    if opened:
        return {"status": OPEN_PR, "prs": opened}
    merged = [p for p in prs if p["state"] == "MERGED"]
    covering = [p for p in merged if head == p["headRefOid"] or contains(head, p["headRefOid"])]
    if covering:
        nums = sorted(p["number"] for p in covering)
        return {"status": MERGED_DIRTY if dirty else MERGED, "prs": nums}
    beyond = [p for p in merged if contains(p["headRefOid"], head)]
    if beyond:
        return {"status": WORK_AFTER_MERGE, "prs": sorted(p["number"] for p in beyond)}
    if elsewhere and ahead:
        return {"status": MERGED_DIRTY if dirty else MERGED_ELSEWHERE, "prs": sorted(elsewhere)}
    closed = sorted(p["number"] for p in prs if p["state"] == "CLOSED")
    if ahead or dirty:
        return {"status": CLOSED_UNMERGED if closed else NO_PR, "prs": closed}
    return {"status": CLEAN, "prs": []}


def describe(result: dict, ahead: int, dirty: int) -> str:
    refs = (" " + ", ".join("#" + str(n) for n in result["prs"])) if result["prs"] else ""
    return f"{LABEL_AR[result['status']]}{refs} — {ahead} إيداعاً خارج main، {dirty} ملفّاً غيرَ مودَع"


def prs_by_branch(repo: Path, warn: list[str] | None = None) -> dict[str, list[dict]] | None:
    """استدعاءٌ واحدٌ لكلّ الطلبات (مفتوحة ومدموجة ومغلقة) مفهرسةً باسم الفرع. None إن تعذّر gh."""
    proc = subprocess.run(
        ["gh", "pr", "list", "--state", "all", "--limit", "2000", "--json", "number,state,headRefName,headRefOid,mergedAt"],
        cwd=repo, capture_output=True, encoding="utf-8", errors="replace", check=False,
    )
    if proc.returncode != 0:
        if warn is not None:
            warn.append(f"gh pr list --state all رجع {proc.returncode}: {proc.stderr.strip()[:160]}")
        return None
    try:
        rows = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        if warn is not None:
            warn.append("gh pr list --state all لم يُرجع JSON صالحاً")
        return None
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["headRefName"]].append(r)
    return dict(out)


def git_contains(repo: Path) -> Callable[[str, str], bool]:
    """a سلفٌ لـb؟ (git merge-base --is-ancestor). إيداعٌ غيرُ موجودٍ محلّياً ⇒ False."""
    def contains(a: str, b: str) -> bool:
        return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=repo,
                              capture_output=True, check=False).returncode == 0
    return contains


def branch_of(wt: dict) -> str:
    """git worktree list --porcelain يعطي 'branch refs/heads/<اسم>'؛ الرأسُ المنفصل بلا فرع."""
    return wt.get("branch", "").removeprefix("refs/heads/")


def merged_elsewhere(repo: Path, head: str, merged: list[dict], contains: Callable[[str, str], bool]) -> list[int]:
    """طلباتٌ مدموجةٌ (أيُّ فرع) رأسُها يحوي رأسَ الشجرة. لا يُفحص إلّا ما اندمج بعد تاريخ إيداع الرأس — فالسلفُ لا
    يكون داخل طلبٍ اندمج قبل وجوده؛ هذا يقصر الفحصَ على عشراتٍ بدل مئاتٍ من استدعاءات merge-base."""
    stamp = subprocess.run(["git", "show", "-s", "--format=%cI", head], cwd=repo, capture_output=True,
                           encoding="utf-8", check=False).stdout.strip()
    if not stamp:
        return []
    from datetime import datetime
    t0 = datetime.fromisoformat(stamp)
    later = [p for p in merged if p.get("mergedAt") and datetime.fromisoformat(p["mergedAt"].replace("Z", "+00:00")) >= t0]
    return sorted(p["number"] for p in later if contains(head, p["headRefOid"]))


def overlap(repo: Path, head: str) -> tuple[int, int]:
    """(ملفّاتٌ فرقُها مطابقٌ لـmain بالمحتوى، مجموعُ ملفّات الفرق) — كم بقي فعلاً من عمل الشجرة."""
    def git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=repo, capture_output=True, encoding="utf-8", errors="replace", check=False).stdout.strip()
    base = git("merge-base", head, "origin/main")
    files = git("diff", "--name-only", base, head).split() if base else []
    same = sum(1 for f in files if git("rev-parse", f"{head}:{f}") == git("rev-parse", f"origin/main:{f}"))
    return same, len(files)
