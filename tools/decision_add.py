#!/usr/bin/env python3
"""أداةُ إلحاق قرارات المالك في decisions.md — الشريحةُ أ من سجلّ القرارات (قرارُ المالك 2026-09-28، نقله المايسترو).

ثلاثةُ أنواع:
  add                إلحاقُ قرارٍ بنيويٍّ عاديّ: D-NNم | الوقتُ من الجهاز | النصّ | الأثر | المرجع.
  approval            اعتمادُ المالك — نوعٌ مستقلٌّ بنصّه الحرفيّ ووقته ومكانه (لا يُصاغ ولا يُلخَّص).
  non-automatable     قرارٌ بحالة «غير قابل للأتمتة» — يُرفض بلا سببٍ مكتوبٍ وتاريخِ مراجعةٍ وبديل.
  coverage            ملخّصٌ رقميٌّ فقط (نسبة، عدد، عمرُ الأقدم) للوحة «تغطية القرارات» في 0702 — بلا نصّ قرارٍ واحد.

الوقتُ يُقرأ من ساعة الجهاز لحظةَ الكتابة، لا يُقدَّر ولا يُمرَّر يدويّاً (المصدر: تصحيحُ أوقات D-50م..D-56م في decisions.md).
كلُّ إلحاقٍ في decisions.md يوازيه سطرٌ في decisions_meta.jsonl (JSON واحد بالسطر) ليُحسَب منه التغطية آليّاً
بلا تحليل نصّ Markdown، ولا يحمل نصَّ القرار — معرّفه ونوعه وتصنيفه وتاريخُ مراجعته وحالتُه فقط.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECISIONS = ROOT / "decisions.md"
META = ROOT / "ledger" / "decisions_meta.jsonl"
REVIEW_DAYS = {"تشغيلي": 90, "بصري": 60}


def now_doha() -> datetime:
    """وقتُ الجهاز لحظةَ الاستدعاء — لا يُقدَّر ولا يُمرَّر يدويّاً."""
    return datetime.now()


def next_id() -> str:
    text = DECISIONS.read_text(encoding="utf-8") if DECISIONS.is_file() else ""
    nums = [int(m) for m in re.findall(r"D-(\d+)م", text)]
    return f"D-{(max(nums) + 1) if nums else 1}م"


DATE_TWICE = re.compile(r"^- D-\d+م? \| (\d\d-\d\d) \1(?![\d/])")


def format_problems(text: str) -> list[str]:
    """أسطرٌ يتكرّر فيها التاريخُ («09-29 09-29 16:10») — عيبٌ يقع حين يُكتب السطرُ يدويّاً لا بالأداة."""
    return [f"السطر {n}: التاريخُ مكرَّر" for n, line in enumerate(text.splitlines(), 1) if DATE_TWICE.match(line)]


def append_row(did: str, ts: datetime, text: str, effect: str, reference: str) -> str:
    row = f"- {did} | {ts:%m-%d %H:%M} | {text} | {effect} | {reference}\n"
    with DECISIONS.open("a", encoding="utf-8", newline="\n") as f:
        f.write(row)
    return row


def append_meta(entry: dict) -> None:
    META.parent.mkdir(parents=True, exist_ok=True)
    with META.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def cmd_add(args: argparse.Namespace) -> int:
    did, ts = next_id(), now_doha()
    row = append_row(did, ts, args.text, args.effect, args.reference)
    append_meta({"id": did, "type": "structural", "ts": ts.isoformat()})
    print(row, end="")
    return 0


def cmd_approval(args: argparse.Namespace) -> int:
    """اعتمادُ المالك: نصٌّ حرفيٌّ بلا صياغةٍ أو تلخيص، ووقتٌ ومكانٌ (محادثةٌ أو جلسة)."""
    did, ts = next_id(), now_doha()
    text = f"اعتمادُ المالك في {args.location}: «{args.text}»"
    row = append_row(did, ts, text, args.effect or "—", args.reference or args.location)
    append_meta({"id": did, "type": "approval", "location": args.location, "ts": ts.isoformat()})
    print(row, end="")
    return 0


def cmd_non_automatable(args: argparse.Namespace) -> int:
    if args.category not in REVIEW_DAYS:
        print("خطأ: category يجب أن يكون تشغيلي أو بصري", file=sys.stderr)
        return 1
    if not args.reason.strip() or not args.alternative.strip():
        print("خطأ: السببُ والبديلُ إلزاميّان ولا يُقبلان فارغَين", file=sys.stderr)
        return 1
    did, ts = next_id(), now_doha()
    review = ts + timedelta(days=REVIEW_DAYS[args.category])
    text = f"غيرُ قابلٍ للأتمتة ({args.category}): {args.text} — السبب: {args.reason} — البديل: {args.alternative}"
    row = append_row(did, ts, text, f"مراجعةٌ في {review:%Y-%m-%d}", args.reference or "—")
    append_meta({
        "id": did, "type": "non_automatable", "category": args.category,
        "reason": args.reason, "alternative": args.alternative,
        "ts": ts.isoformat(), "review_due": review.isoformat(), "reviewed": False,
    })
    print(row, end="")
    return 0


def cmd_coverage(_: argparse.Namespace) -> int:
    """ملخّصٌ رقميٌّ فقط — بلا نصّ قرارٍ واحد، ليصلح لعرضٍ في مركز قيادة الجودة (0702)."""
    if not META.is_file():
        print(json.dumps({"non_automatable_count": 0, "overdue_review_count": 0,
                           "missing_reason_count": 0, "oldest_open_days": 0}, ensure_ascii=False))
        return 0
    now = now_doha()
    rows = [json.loads(line) for line in META.read_text(encoding="utf-8").splitlines() if line.strip()]
    na = [r for r in rows if r["type"] == "non_automatable"]
    overdue = [r for r in na if not r.get("reviewed") and datetime.fromisoformat(r["review_due"]) < now]
    missing_reason = [r for r in na if not r.get("reason", "").strip()]
    oldest = min((datetime.fromisoformat(r["ts"]) for r in na), default=now)
    print(json.dumps({
        "non_automatable_count": len(na),
        "overdue_review_count": len(overdue),
        "missing_reason_count": len(missing_reason),
        "oldest_open_days": (now - oldest).days,
    }, ensure_ascii=False))
    return 0


def cmd_check(_: argparse.Namespace) -> int:
    """فحصُ تنسيق decisions.md (قراءةٌ فقط): رمزُ الخروج 1 إن وُجد سطرٌ معيب."""
    problems = format_problems(DECISIONS.read_text(encoding="utf-8")) if DECISIONS.is_file() else []
    print("\n".join(problems) if problems else "تنسيقُ decisions.md سليم")
    return 1 if problems else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="قرارٌ بنيويٌّ عاديّ")
    a.add_argument("--text", required=True)
    a.add_argument("--effect", required=True)
    a.add_argument("--reference", required=True)
    a.set_defaults(func=cmd_add)

    ap = sub.add_parser("approval", help="اعتمادُ المالك — نصٌّ حرفيّ")
    ap.add_argument("--text", required=True, help="النصُّ الحرفيّ وحدَه، بلا صياغة")
    ap.add_argument("--location", required=True, help="محادثةُ «...» أو جلسةُ «...»")
    ap.add_argument("--effect", default="")
    ap.add_argument("--reference", default="")
    ap.set_defaults(func=cmd_approval)

    na = sub.add_parser("non-automatable", help="قرارٌ بحالة «غير قابل للأتمتة»")
    na.add_argument("--text", required=True)
    na.add_argument("--category", required=True, choices=["تشغيلي", "بصري"])
    na.add_argument("--reason", required=True)
    na.add_argument("--alternative", required=True, help="بندٌ في قائمة تحقّق طلب الدمج")
    na.add_argument("--reference", default="")
    na.set_defaults(func=cmd_non_automatable)

    cov = sub.add_parser("coverage", help="ملخّصٌ رقميّ فقط للوحة 0702")
    cov.set_defaults(func=cmd_coverage)

    chk = sub.add_parser("check", help="فحصُ تنسيق decisions.md (تاريخٌ مكرَّر)")
    chk.set_defaults(func=cmd_check)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
