#!/usr/bin/env python3
"""قائمةُ ما بعد الدمج: تقرأ حالةَ الطلب من المصدر وتُخرج نصَّ إشعاراتِ 0701 و0104 جاهزةً + سطرَ ledger.

    python post_merge_checklist.py 757 [--card W-20261001-035]

قراءةٌ فقط ولا تُرسل شيئاً (الشيفرةُ لا تراسل الجلسات): تنقل 0601 النصَّ إلى SendMessage. تحلّ محلَّ الاعتماد على
الذاكرة في خطواتٍ نُسيت من قبل (إخطار 0701 فورَ كلّ اندماج) وتضيف 0104 خطوةً خامسة (D-101م).
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


def session_for_branch(branch: str) -> str | None:
    """الجلسةُ التي تملك شجرةَ هذا الفرع (من session_names.json) أو None إن لم تُسجَّل."""
    try:
        import branch_status as bs
        import session_load_v2 as sl

        names = sl.load_json("session_names.json", "schoolos")
        for wt in sl.worktrees(Path(REPO_DIR), []):
            if bs.branch_of(wt) == branch:
                return names.get(Path(wt["worktree"]).name)
    except Exception:  # noqa: BLE001 — الأداةُ لا تسقط بسبب تعذّر الإسناد
        return None
    return None


def build(pr: dict, card: str | None, hits: list[str], session: str | None = None) -> dict[str, str]:
    n, title, sha = pr["number"], pr["title"], (pr.get("mergeCommit") or {}).get("oid", "")[:8]
    head = f"#{n} «{title[:80]}» اندمج {pr.get('mergedAt', '')} (commit {sha})" + (f" — البطاقة {card}" if card else "")
    sec = ("\nمسّ مساراً حسّاساً أمنيّاً: " + "، ".join(hits[:6]) + " ← الفحصُ بعد النشر إلزاميّ.") if hits else "\nلم يمسّ مساراً من قائمة المسارات الحسّاسة."
    who = session or "الجلسة المنفِّذة (لم يُحدَّد صاحبُ الفرع — اسألي 0101)"
    return {
        f"{who}": f"{head}.\nعملُك **نُشر** (تحقّقت 0601 من الإنتاج). المطلوب: اكتبي مذكّرةَ تسليمٍ في handover_notes/ (ما أُنجز، ما بقي، أدواتُك وملفّاتُك) ثمّ أخبري 0101 أنّك جاهزةٌ للأرشفة؛ ولا تبدئي عملاً جديداً قبل قرارها.",
        "0101": f"{head}.\nنُشر عملُ {who}: **قرّري أرشفتَها** (archive_check ثمّ الأرشفة بتفويضك الدائم D-62م، أو إبقاؤها إن بقي لها عمل).",
        "0701": f"{head}.\nالمطلوب: (١) الخارطة: إغلاقُ البند أو تحديثُ تقدّمه برقم الطلب" + (f" ({card})" if card else "") + "؛ وأضيفي ما لم يكن له بند. (٢) القياس: ما مسّه النشرُ ومقارنتُه بالأساس بعد تحقّق النشر.",
        "0104": f"{head}.{sec}\nالمطلوب: فحصٌ بعد النشر يُثبَّت فيه رقمُ الإيداع المنشور ({sha}).",
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pr")
    ap.add_argument("--card")
    a = ap.parse_args()
    p = subprocess.run(["gh", "pr", "view", a.pr, "--json", "number,title,state,mergedAt,mergeCommit,files,headRefName"],
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
    print("الخطواتُ الستّ بعد كلّ اندماج منشور (تُنفَّذ معاً): تحقّقٌ، دفتر، 0701 (الخارطة والقياس)، 0104، **الجلسةُ المنفِّذة**، **0101 لقرار الأرشفة**")
    print("  ١) تحقّقُ النشر الفعليّ (verify_deploy / health)")
    print(f"  ٢) python C:/Users/mesue/delivery_manager_work/tools/ledger.py move {a.card or '<رمز البطاقة>'} published --note \"اندمج #{pr['number']}\"")
    session = session_for_branch(pr.get("headRefName", ""))
    for who, text in build(pr, a.card, hits, session).items():
        print(f"\n  إلى {who}:\n    " + text.replace("\n", "\n    "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
