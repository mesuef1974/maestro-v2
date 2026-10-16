#!/usr/bin/env python3
"""نقلُ الدفتر إلى «منشور» آلياً (W-20261015-005، أمر المالك 2026-10-15) — عرضٌ افتراضيّاً و`--apply` للنقل.

    python publish_auto.py                 # عرض: ما سيُنقل
    python publish_auto.py --apply         # ينقل ويطبع نصّاً مجمَّعاً للإبلاغ
    python publish_auto.py --commit 25cef9a --apply

يبني على publish_sync: يقرأ commit الإنتاج من /health/ (سليم وحقل commit)، ويطابق كلَّ بطاقةٍ (approved/pushed/merged ولها رأس)
بطلبٍ مدموجٍ بالرأس نفسه ودمجُه سلفٌ لـcommit الإنتاج. ما تحقّق يُنقل بالتسلسل المسموح pushed ثمّ merged ثمّ published.

لا يدمج ولا ينشر ولا يرسل رسائل (الدمجُ والنشر لـ0601 وحدَها، والإرسال لأداة الجلسات): يطبع نصّاً واحداً مجمَّعاً بالرأس لكلّ
البطاقات. وكلُّ انتقالٍ يحمل مذكّرةً «آلياً (publish_auto) — #PR مدموج ومنشور <commit>» فيُعرف أنه ليس من يد 0601.
فشلُ /health/ أو gh = لا نقل. يعدّل D-88م (تسجيلُ published) فيدوّنه 0103.
"""

from __future__ import annotations

import argparse
import sys

import ledger
import publish_sync as ps


PR_URL = "https://github.com/sh-school/shschool_mvp/pull/{}"


def unmeasured_text(exc: Exception) -> str:
    """غياب /health/ أو عدمُ سلامته أو فشلُ gh = غير مقيس صراحةً، لا نقلَ ولا نجاحَ صامت."""
    return f"غير مقيس: {exc} — لا نقل"


def apply_rows(rows: list[dict], prod: str, move=None, note=None) -> list[str]:
    """ينقل كلَّ بطاقةٍ مستحقّةٍ؛ يعيد أسطرَ ما فُعل. بطاقةٌ فشل نقلُها تُسجَّل ولا توقف الباقي."""
    move = move or ledger.move
    done = []
    for r in rows:
        why = f"آلياً (publish_auto) — #{r['pr']} مدموج {r['merge']} ومنشور {prod[:7]} — {PR_URL.format(r['pr'])}"
        try:
            start = ps.CHAIN.index(r["state"]) + 1 if r["state"] in ps.CHAIN else 0
            for step in ps.CHAIN[start:]:
                kw = {"waive_remote_check": why} if step == "pushed" else {}
                move(r["id"], step, note=why if step == "published" else None, **kw)
            done.append(f"{r['id']} ← published (#{r['pr']})")
        except ledger.LedgerError as exc:
            done.append(f"{r['id']} ✘ {exc}")
    return done


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--commit", help="بدل قراءة /health/ (للاختبار أو الفحص)")
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    try:
        prod = a.commit or ps.fetch_health()
        states = ledger.reduce_state(ledger.load_events())
        rows = ps.due(states, ps.merged_prs(a.limit), prod)
    except ps.SyncError as exc:
        print(unmeasured_text(exc), file=sys.stderr)
        return 2
    for r in rows:
        r["prod"] = prod[:7]
    print(f"الإنتاج {prod[:7]} — {len(rows)} بطاقة مستحقّة للنقل إلى published")
    if not a.apply:
        for r in rows:
            print(f"  {r['id']} ({r['state']}) #{r['pr']} رأس {r['head']}")
        print("عرض فقط — أضف --apply للنقل")
        return 0
    for line in apply_rows(rows, prod):
        print("  " + line)
    if rows:
        print("\nإبلاغٌ واحدٌ لكلّ صاحب بطاقةٍ (أرسله مرةً واحدة؛ بلا صاحبٍ إلى 0701):")
        for owner, text in ps.messages_by_owner(rows, states, prod[:7]).items():
            print(f"  [{owner}] {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
