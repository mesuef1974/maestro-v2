#!/usr/bin/env python3
"""تصنيفُ أسماء الفروع برمز البطاقة (R5، W-20261014-008): قراءةٌ فقط، تحذيرٌ لا إلزام حتى 2026-10-28.

    python branch_name_check.py --repo D:/shschool_mvp            # تقريرٌ عربيّ
    python branch_name_check.py --repo D:/shschool_mvp --json     # للأتمتة
    python branch_name_check.py --suggest W-20261014-008 --slug git-names

النمطُ المطلوب: claude/W-YYYYMMDD-NNN أو claude/W-YYYYMMDD-NNN-<وصف>.
الفئاتُ: live (رمزُ بطاقةٍ حيّة) · ended (بطاقةٌ منتهية) · unknown (رمزٌ غيرُ موجودٍ في الدفتر) · none (بلا رمز) · exempt (main وbackup وrebuild).
«حيّة» = حالتُها ليست من closed/published/deferred (فتشمل merged)؛ والمنتهية هذه الثلاث (تأكيد 0103).
لا يحذف ولا يعيد تسميةً ولا يدفع.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

CARD_IN_NAME = re.compile(r"(?:^|/)W-(\d{8}-\d{3})(?:-|$)")
WELL_FORMED = re.compile(r"^claude/W-\d{8}-\d{3}(?:-[A-Za-z0-9][A-Za-z0-9._-]*)?$")
ENDED_STATES = {"closed", "published", "deferred"}  # = RELEASING_STATES في ledger.py (تأكيد 0103)
EXEMPT = re.compile(r"^(main|master|HEAD|backup[/-].*|rebuild/.*|worktree-.*)$")
DEADLINE = "2026-10-28"


def classify(name: str, cards: dict) -> str:
    """فئةُ الفرع. `cards` = رمزٌ كامل (W-…) ← حالتُه."""
    short = re.sub(r"^(origin|remotes/origin)/", "", name)
    if EXEMPT.match(short):
        return "exempt"
    m = CARD_IN_NAME.search(short)
    if not m:
        return "none"
    state = cards.get("W-" + m.group(1))
    if state is None:
        return "unknown"
    return "ended" if state in ENDED_STATES else "live"


def conforms(name: str) -> bool:
    return bool(WELL_FORMED.match(re.sub(r"^(origin|remotes/origin)/", "", name)))


def load_cards() -> dict:
    import ledger

    items = ledger.reduce_state(ledger.load_events())
    return {k: v.get("state") for k, v in items.items()}


def list_branches(repo: str) -> list[str]:
    p = subprocess.run(["git", "branch", "--format=%(refname:short)"], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]


def report(names: list[str], cards: dict) -> dict:
    counts = {"live": 0, "ended": 0, "unknown": 0, "none": 0, "exempt": 0}
    bad: list[str] = []
    for n in names:
        c = classify(n, cards)
        counts[c] += 1
        if c in ("none", "unknown") or (c in ("live", "ended") and not conforms(n)):
            bad.append(n)
    scored = len(names) - counts["exempt"]
    pct = round(100 * counts["live"] / scored, 1) if scored else 0.0
    return {"total": len(names), "counts": counts, "live_pct": pct, "violations": sorted(bad)}


def suggest(card: str, slug: str = "") -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-")
    return f"claude/{card}" + (f"-{slug}" if slug else "")


def warning_for(branch: str, card: str | None, cards: dict | None = None) -> str | None:
    """سطرُ تحذيرٍ غيرُ حاجبٍ لفرعٍ مخالف، أو None إن سلم."""
    if conforms(branch) and (cards is None or classify(branch, cards) in ("live", "ended")):
        return None
    if EXEMPT.match(branch):
        return None
    good = suggest(card, branch.rsplit("/", 1)[-1]) if card else "claude/W-YYYYMMDD-NNN-<وصف>"
    return f"تحذيرٌ (لا يحجب حتى {DEADLINE}): اسمُ الفرع {branch} لا يحمل رمزَ بطاقةٍ سليماً؛ المقترح {good} (الدفعُ بلا تحريك الرأس: git push origin HEAD:refs/heads/{good})."


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--suggest", metavar="CARD")
    ap.add_argument("--slug", default="")
    a = ap.parse_args()
    if a.suggest:
        print(suggest(a.suggest, a.slug))
        return 0
    rep = report(list_branches(a.repo), load_cards())
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0
    c = rep["counts"]
    print(f"الفروع المحلّيّة: {rep['total']} · لبطاقةٍ حيّة {c['live']} ({rep['live_pct']}% من غير المستثنى) · لبطاقةٍ منتهية {c['ended']} · رمزٌ غيرُ موجود {c['unknown']} · بلا رمز {c['none']} · مستثناة {c['exempt']}")
    print(f"المخالفة: {len(rep['violations'])} (تحذيرٌ فقط حتى {DEADLINE}؛ الهدفُ 95% قبل الإلزام)")
    for n in rep["violations"][:20]:
        print("  -", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
