#!/usr/bin/env python3
"""«جاهزٌ للمعاينة» يُسجَّل في الدفتر بالرأس لا بالرسالة وحدها — فيعكس جدولُ batch_preview الجاهزاتِ الحقيقيّة (W-20261014-015).

تنقل بطاقةً إلى ready_for_review بالانتقال الرسميّ `ledger.move` (فتسري بوّاباتُه كلُّها) وتكتب في ملاحظتها الرأسَ المعلَن والرابطَ والدور؛ لا تعتمد
ولا تمسّ فلوَ الاعتماد: الرأسُ يُكتب في **ملاحظةٍ** وفي الحقل المهيكل `ready_head` (D-452م) لا في حقل `head` (الذي يُقرأ اعتماداً
— v2.23)، فلا ينتحل أحدٌ اعتمادَ المالك؛ ومضخّةُ التدفّق تقرأ `ready_head`.
تُشغَّلها الجلسةُ المنفِّذةُ بعد الإيداع وقبل/مع رسالتها لـ0501؛ وإعادتُها بالرأس نفسه لا تفعل شيئاً.

    python ready_mark.py <بطاقة> --head <sha8> --by <رقمك> [--link http://localhost:8500/…] [--role الدور] [--repo D:/shschool_mvp] [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402

DEFAULT_REPO = "D:/shschool_mvp"
NO_PREFLIGHT = "تعليمُ رأسٍ فقط بلا فحصٍ مسبق (ready_mark)"
PREFLIGHT_OK = "الفحصُ المسبق نجح آلياً (ready_mark)"
FROM_STATES = {"in_progress", "routed", "verified", "notes", "ready_for_review"}
MARK = "جاهزٌ للمعاينة بالرأس "
HEAD_NOTE = re.compile(re.escape(MARK) + r"([0-9a-f]{7,40})")


def git_ok(repo: str, *args: str) -> str | None:
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, encoding="utf-8", errors="replace", check=False)
    return p.stdout.strip() if p.returncode == 0 else None


def candidate_repos(explicit: str | None) -> list[str]:
    """أين يُبحث عن الرأس: ما مرَّرتَه، ثمّ SCHOOLOS_REPO، ثمّ المنصّة، ثمّ مستودعُ الأداة نفسِه (بطاقاتُ maestro). بلا تكرار."""
    seen: list[str] = []
    for r in (explicit, os.environ.get("SCHOOLOS_REPO"), DEFAULT_REPO, str(Path(__file__).resolve().parent.parent)):
        if r and r not in seen:
            seen.append(r)
    return seen


def find_head(explicit: str | None, head8: str) -> tuple[str, str | None]:
    """(المستودعُ الذي وُجد فيه الرأس، الرأسُ الكامل) أو (أوّلُ مرشَّح، None)."""
    cands = candidate_repos(explicit)
    for r in cands:
        full = git_ok(r, "rev-parse", "--verify", f"{head8}^{{commit}}")
        if full:
            return r, full
    return cands[0], None


def declared_head(item: dict) -> str | None:
    """الرأسُ المعلَن «جاهزاً» (sha8) أو None: الحقلُ المهيكل ready_head أوّلاً (D-452م)، وإلا آخرُ ملاحظةٍ قديمةٍ به."""
    if "ready_head" in item:  # الحقلُ حاضرٌ = مصدرُ الحقيقة؛ الفارغُ يعني أنّ العملَ عاد فسُحب الإعلان
        return item["ready_head"] or None
    for n in reversed(item.get("notes", [])):
        m = HEAD_NOTE.search(n.get("text", ""))
        if m:
            return m.group(1)[:8]
    return None


def auto_preflight_repo(repo: str, full: str) -> str | None:
    """شجرةُ الفحص المسبق تلقائياً: المستودعُ الذي وُجد فيه الرأس إن كان HEAD فيه هو الرأسَ نفسَه (فيفحص الفحصُ فرعَ البطاقة فعلاً).
    وإلا (رأسٌ في فرعٍ غير مُسحوب) لا شجرةَ تُفحص فيرجع None ويبقى الإعفاءُ المدوَّن القصير."""
    return repo if git_ok(repo, "rev-parse", "HEAD") == full else None


def mark(card: str, head: str, by: str, repo: str, link: str = "", role: str = "", base: str = "origin/main",
         dry: bool = False, path=None, preflight_repo: str | None = None, waive_preflight: str | None = None,
         premerge_sha: str | None = None) -> str:
    items = ledger.reduce_state(ledger.load_events(path))
    if card not in items:
        raise ledger.LedgerError(f"بطاقةٌ غيرُ موجودة: {card}")
    item = items[card]
    if not ledger.HEAD_RE.match(head or ""):
        raise ledger.LedgerError("--head <sha8> مطلوب (git rev-parse --short=8 <الفرع>)")
    head8 = head[:8]
    if item["state"] not in FROM_STATES:
        raise ledger.LedgerError(f"«{item['state']}» لا تنتقل إلى ready_for_review بهذه الأداة (الحالات المقبولة: {sorted(FROM_STATES)})")
    repo, full = find_head(repo, head8)
    if not full:
        raise ledger.LedgerError(f"الرأس {head8} غيرُ موجودٍ في أيٍّ من: {'، '.join(candidate_repos(repo))} — أودِع أولاً أو مرِّر --repo <المستودع>")
    if not git_ok(repo, "log", "-1", "--format=%H", f"--grep={card}", full, f"^{base}"):
        raise ledger.LedgerError(f"لا إيداعَ يحمل رمزَ {card} بين {base} والرأس {head8} — رأسٌ لبطاقةٍ أخرى؟")
    if item["state"] == "ready_for_review" and declared_head(item) == head8:
        return f"لا تغيير: {card} جاهزةٌ أصلاً بالرأس {head8}"
    if preflight_repo is None and not waive_preflight and not dry:
        tree = auto_preflight_repo(repo, full)  # W-20261014-007: الفحصُ المسبق (R2) يعمل دائماً متى كانت الشجرةُ على الرأس نفسِه
        if tree:
            # يُشغَّل هنا قبل أيّ كتابةٍ فيُرفض الانتقالُ كاملاً عند الفشل؛ وإنذاراتُه الطويلة تُطبع ولا تُلصق في الملاحظة (حدّ 240، كسرُ #46)
            warn = ledger.check_preflight_ready(item, "ready_for_review", tree, None)
            if warn:
                print(warn, file=sys.stderr)
            waive_preflight = PREFLIGHT_OK
    extra = "؛ ".join(([f"الرابط {link}"] if link else []) + ([f"الدور {role}"] if role else []))
    note = f"{MARK}{head8}"
    if dry:
        return f"[dry] {card} ← ready_for_review: {'؛ '.join(filter(None, [note, extra]))}"
    # `ledger.move` يلصق في الملاحظة إنذارَ الفحص المسبق (~110 حرفاً) وإنذارَ البصمة؛ فبلا تمريرٍ صريحٍ تجاوزت الملاحظةُ حدَّ 240 حرفاً
    # (كسرُ #46). هذه الأداةُ تعلّم الرأسَ فحسب ولا تُشغّل الفحص: فتُعلن ذلك بنصٍّ قصيرٍ صريحٍ بدل إنذارٍ طويل، ومن يملك الفحصَ يمرّره.
    ledger.move(card, "ready_for_review", path=path, note=note, by=by, head_now=head8, preflight_repo=preflight_repo,
                waive_preflight=waive_preflight or (None if preflight_repo else NO_PREFLIGHT), premerge_sha=premerge_sha)
    if extra:  # الرابطُ والدور في ملاحظةٍ لاحقةٍ: إنذاراتُ move تملأ حدَّ 240 حرفاً في ملاحظة الانتقال
        ledger.append_event("note", card, {"text": ledger.check_text("note", extra)}, path)
    return f"ok: {card} ← ready_for_review ({'؛ '.join(filter(None, [note, extra]))})"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("card")
    ap.add_argument("--head", required=True)
    ap.add_argument("--by", required=True)
    ap.add_argument("--link", default="")
    ap.add_argument("--role", default="")
    ap.add_argument("--repo", default=None, help="المستودعُ الذي فيه الرأس؛ بغيابه يُبحث في SCHOOLOS_REPO ثمّ المنصّة ثمّ مستودع الأداة")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--preflight-repo", default=None, help="شجرةُ الفحص المسبق؛ الافتراضيُّ مستودعُ الرأس")
    ap.add_argument("--waive-preflight", default=None, help="سببُ إعفاء الفحص المسبق")
    ap.add_argument("--premerge-sha", default=None, help="بصمةُ make premerge: <head8>:<sha16>")
    a = ap.parse_args(argv)
    path = ledger.ledger_path()
    if not path.is_file():
        # دفترٌ غائبٌ (شجرةٌ نظيفةٌ بلا ledger/events.jsonl غير المتتبَّع) لا يُقال عنه «بطاقةٌ غيرُ موجودة»
        print(f"✗ لا دفترَ في {path} — شغّل الأداةَ من مجلّد المايسترو أو اضبط LEDGER_PATH", file=sys.stderr)
        return 2
    try:
        print(mark(a.card, a.head, a.by, a.repo, a.link, a.role, a.base, a.dry_run, preflight_repo=a.preflight_repo,
                   waive_preflight=a.waive_preflight, premerge_sha=a.premerge_sha))
    except ledger.LedgerError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
