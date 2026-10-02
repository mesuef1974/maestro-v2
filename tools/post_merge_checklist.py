#!/usr/bin/env python3
"""قائمةُ ما بعد الدمج: تقرأ حالةَ الطلب من المصدر وتُخرج نصَّ إشعاراتِ 0701 و0702 و0105 جاهزةً + سطرَ ledger.

    python post_merge_checklist.py 757 [--card W-20261001-035]

قراءةٌ فقط ولا تُرسل شيئاً (الشيفرةُ لا تراسل الجلسات): تنقل 0601 النصَّ إلى SendMessage. تحلّ محلَّ الاعتماد على
الذاكرة في خطواتٍ نُسيت من قبل (إخطار 0701/0702 فورَ كلّ اندماج) وتضيف 0105 خطوةً خامسة (D-101م).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_DIR = "D:/shschool_mvp"


def sensitive_hits(files: list[str], globs: list[str]) -> list[str]:
    return sorted({f for f in files for g in globs if fnmatch.fnmatch(f, g.split(":")[0])})


def build(pr: dict, card: str | None, hits: list[str]) -> dict[str, str]:
    n, title, sha = pr["number"], pr["title"], (pr.get("mergeCommit") or {}).get("oid", "")[:8]
    head = f"#{n} «{title[:80]}» اندمج {pr.get('mergedAt', '')} (commit {sha})" + (f" — البطاقة {card}" if card else "")
    sec = ("\nمسّ مساراً حسّاساً أمنيّاً: " + "، ".join(hits[:6]) + " ← الفحصُ بعد النشر إلزاميّ.") if hits else "\nلم يمسّ مساراً من قائمة المسارات الحسّاسة."
    return {
        "0701": f"{head}.\nالمطلوب: إغلاقُ البند أو تحديثُ تقدّمه برقم الطلب" + (f" ({card})" if card else "") + "؛ وأضيفي ما لم يكن له بند.",
        "0702": f"{head}.\nالمطلوب: قياسُ ما مسّه النشرُ ومقارنتُه بالأساس بعد تحقّق النشر.",
        "0105": f"{head}.{sec}\nالمطلوب: فحصٌ بعد النشر يُثبَّت فيه رقمُ الإيداع المنشور ({sha}).",
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pr")
    ap.add_argument("--card")
    a = ap.parse_args()
    p = subprocess.run(["gh", "pr", "view", a.pr, "--json", "number,title,state,mergedAt,mergeCommit,files"],
                       cwd=REPO_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print("تعذّر الاستعلام:", p.stderr.strip()[:200])
        return 1
    pr = json.loads(p.stdout)
    if pr["state"] != "MERGED":
        print(f"الطلبُ #{pr['number']} حالتُه {pr['state']} لا MERGED — لا إشعارَ قبل الاندماج الفعليّ.")
        return 1
    paths = json.loads((ROOT / "security" / "sensitive_paths.json").read_text(encoding="utf-8"))
    globs = [g for grp in paths.get("mandatory_review_when_diff_touches", {}).values() for g in grp]
    hits = sensitive_hits([f["path"] for f in pr.get("files", [])], globs)
    print("الخطواتُ الخمس بعد كلّ اندماج (تُنفَّذ معاً):")
    print("  ١) تحقّقُ النشر الفعليّ (verify_deploy / health)")
    print(f"  ٢) python C:/Users/mesue/delivery_manager_work/tools/ledger.py move {a.card or '<رمز البطاقة>'} published --note \"اندمج #{pr['number']}\"")
    for who, text in build(pr, a.card, hits).items():
        print(f"\n  إلى {who}:\n    " + text.replace("\n", "\n    "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
