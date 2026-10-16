#!/usr/bin/env python3
"""تصنيفُ إعادات الاعتماد بالسبب (W-20261016-016): بطاقةٌ اعتُمدت على رأسٍ ثمّ اعتُمدت على رأسٍ مختلف.

السببُ يُستنتج من فرق الملفّات بين الرأسين في مستودع المنصّة (قراءةٌ فقط)؛ وما تعذّر (رأسٌ غائب أو لا رأسَ في
الاعتماد) يُعدّ «غير معروف» ويُعلن عددُه. لا يغيّر شيئاً في الدفتر ولا في المستودع.

    python reapproval_causes.py [--repo D:/shschool_mvp] [--json]
"""

from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ledger  # noqa: E402

UI_PREFIXES = ("templates/", "static/")
CAUSES = ("واجهة", "هجرة", "كود", "اختبارات فقط", "وثائق فقط", "غير معروف")


def classify_paths(paths: list[str]) -> str:
    """سببٌ واحد من فرق المسارات؛ الأعلى خطورةً يغلب (واجهة ثمّ هجرة ثمّ كود)."""
    if not paths:
        return "غير معروف"
    if any(p.startswith(UI_PREFIXES) for p in paths):
        return "واجهة"
    if any("/migrations/" in p or p.startswith("migrations/") for p in paths):
        return "هجرة"
    if all(p.startswith("tests/") or "/tests/" in p or Path(p).name.startswith("test_") for p in paths):
        return "اختبارات فقط"
    if all(p.startswith(("docs/", "AAdocs/")) or p.endswith(".md") for p in paths):
        return "وثائق فقط"
    return "كود"


def pairs(events: list[dict]) -> list[tuple[str, str, str]]:
    """(البطاقة، الرأس القديم، الرأس الجديد) لكلّ اعتمادٍ ثانٍ على رأسٍ مختلفٍ معلوم."""
    heads: dict[str, list[str | None]] = collections.defaultdict(list)
    for e in events:
        if e["kind"] == "state" and e["data"].get("state") == "approved":
            heads[e["id"]].append(e["data"].get("head"))
    out = []
    for card, hs in heads.items():
        for old, new in zip(hs, hs[1:]):
            out.append((card, old or "", new or ""))
    return [p for p in out if p[1] != p[2]]


def diff_paths(repo: str, old: str, new: str) -> list[str] | None:
    p = subprocess.run(["git", "diff", "--name-only", old, new], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [ln.strip() for ln in p.stdout.splitlines() if ln.strip()] if p.returncode == 0 else None


def classify_all(events: list[dict], repo: str, differ=diff_paths) -> list[tuple[str, str]]:
    result = []
    for card, old, new in pairs(events):
        if not old or not new:
            result.append((card, "غير معروف"))
            continue
        paths = differ(repo, old, new)
        result.append((card, "غير معروف" if paths is None else classify_paths(paths)))
    return result


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default="D:/shschool_mvp")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = classify_all(ledger.load_events(), a.repo)
    counts = collections.Counter(c for _, c in res)
    total = len(res)
    if a.json:
        print(json.dumps({"total": total, "counts": counts}, ensure_ascii=False))
        return 0
    print(f"إعاداتُ الاعتماد على رأسٍ مختلف: {total}")
    for cause in CAUSES:
        n = counts.get(cause, 0)
        print(f"  {cause}: {n} ({(100 * n / total) if total else 0:.0f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
