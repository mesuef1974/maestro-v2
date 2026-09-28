#!/usr/bin/env python3
"""وسمُ بطاقة السجلّ بخطورتها ومجالها قبل نافذة المراجعة — سدٌّ لفجوةٍ في ledger.py.

لماذا: review_window.py يجمع الحزمَ بحقول tier/category/area/pr في البطاقة، ويستثني من «اعتمد الكلّ»
ما خطورتُه high. لكنّ ledger.py لا أمرَ فيه يكتب هذه الحقول، فتقع كلُّ البطاقات غيرِ الموسومة في حزمةٍ
واحدة «? · ?» بخطورة low — فيعتمد «اعتمد الكلّ» هجرةً أو ملفَّ أمنٍ دون ذكر رقمها.

    # عرضٌ فقط (الافتراضيّ): يصنّف ويطبع الحدثَ الذي سيُلحَق
    python tag_card.py W-20260928-005 --branch claude/<فرع>
    python tag_card.py W-20260928-005 --pr 725
    python tag_card.py W-20260928-005 --paths core/migrations/0099_x.py templates/a.html
    # رفعُ الخطورة بحكمٍ مسبَّب (لا خفضَ أبداً)
    python tag_card.py W-... --branch claude/<فرع> --raise-to high --reason "RLS في middleware"
    # الكتابة: حدثُ update يُلحَق بالسجلّ (يُلحَق فقط، لا تعديل)
    python tag_card.py W-... --branch claude/<فرع> --apply

قراءةٌ فقط على غيت وgh. الكتابةُ الوحيدة سطرٌ في ledger/events.jsonl وبـ--apply وحده.
LEDGER_PATH يوجّه الكتابةَ إلى نسخةٍ للتجربة؛ MAESTRO_ROOT يحدّد مجلّد الحزمة.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

MAESTRO_ROOT = Path(os.environ.get("MAESTRO_ROOT", "C:/Users/mesue/delivery_manager_work"))
REPO = "D:/shschool_mvp"
sys.path.insert(0, str(MAESTRO_ROOT / "tools"))
import ledger  # noqa: E402
from risk_tier import TIER_ORDER, classify_paths  # noqa: E402


def run(cmd: list[str]) -> str:
    """يشغّل أمراً قرائيّاً ويُسقط الأداةَ برسالةٍ واضحة إن فشل (لا فشلَ صامت)."""
    proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", check=False, cwd=REPO)
    if proc.returncode != 0:
        sys.exit(f"فشل: {' '.join(cmd[:4])} … — {proc.stderr.strip()[:200]}")
    return proc.stdout


def from_branch(branch: str) -> tuple[list[str], str]:
    # الفرقُ منذ نقطة الافتراق عن main (ثلاث نقاط) = ما ستحمله الجلسةُ فعلاً، لا ما تغيّر في main بعدها
    paths = run(["git", "diff", "--name-only", f"origin/main...{branch}"]).split()
    head = run(["git", "rev-parse", "--short=8", branch]).strip()
    return paths, head


def from_pr(number: int) -> tuple[list[str], str]:
    data = json.loads(run(["gh", "pr", "view", str(number), "--json", "files,headRefOid"]))
    return [f["path"] for f in data.get("files", [])], data.get("headRefOid", "")[:8]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("card", help="معرّفُ البطاقة W-YYYYMMDD-NNN")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--branch", help="فرعُ الشجرة المنفِّذة (قبل الدفع)")
    src.add_argument("--pr", type=int, help="رقمُ طلب الدمج (بعد الدفع)")
    src.add_argument("--paths", nargs="+", help="مساراتٌ صريحة")
    ap.add_argument("--raise-to", choices=TIER_ORDER, help="رفعُ الخطورة بحكمٍ (لا خفض)")
    ap.add_argument("--reason", default="", help="سببُ الرفع — إلزاميٌّ معه")
    ap.add_argument("--apply", action="store_true", help="اكتب حدثَ update في السجلّ؛ بدونه عرضٌ فقط")
    args = ap.parse_args()

    items = ledger.reduce_state(ledger.load_events())
    if args.card not in items:
        sys.exit(f"رُفض: بطاقةٌ غيرُ موجودة: {args.card}")

    head, pr = "", None
    if args.branch:
        paths, head = from_branch(args.branch)
    elif args.pr:
        paths, head = from_pr(args.pr)
        pr = args.pr
    else:
        paths = args.paths
    if not paths:
        sys.exit("رُفض: لا مساراتٍ متغيّرة — تحقّق من اسم الفرع أو أنّ العملَ أُودِع")

    info = classify_paths(paths)
    tier = info["tier"]
    if args.raise_to:
        if not args.reason:
            sys.exit("رُفض: --raise-to يلزمه --reason")
        if TIER_ORDER.index(args.raise_to) < TIER_ORDER.index(tier):
            sys.exit(f"رُفض: لا خفضَ للخطورة ({tier} ← {args.raise_to}); الأداةُ حدٌّ أدنى لا أعلى")
        tier = args.raise_to

    data = {"tier": tier, "category": info["category"], "area": info["area"], "flags": info["flags"],
            "files_changed": len(paths)}
    if head:
        data["head"] = head  # الإيداعُ المصنَّف — يُقارن لاحقاً برأس الطلب قبل الدمج
    if pr:
        data["pr"] = pr
    if args.raise_to:
        data["tier_reason"] = ledger.check_text("note", args.reason)

    print(json.dumps({"card": args.card, "update": data, "categories": info["categories"]}, ensure_ascii=False, indent=2))
    if args.apply:
        ledger.append_event("update", args.card, data)
        print(f"أُلحق حدثُ update بـ{ledger.ledger_path()}")
    else:
        print("عرضٌ فقط — أضِف --apply للكتابة")


if __name__ == "__main__":
    main()
