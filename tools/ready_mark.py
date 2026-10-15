#!/usr/bin/env python3
"""«جاهزٌ للمعاينة» يُسجَّل في الدفتر بالرأس لا بالرسالة وحدها — فيعكس جدولُ batch_preview الجاهزاتِ الحقيقيّة (W-20261014-015).

تنقل بطاقةً إلى ready_for_review بالانتقال الرسميّ `ledger.move` (فتسري بوّاباتُه كلُّها) وتكتب في ملاحظتها الرأسَ المعلَن والرابطَ والدور؛ لا تعتمد
ولا تمسّ فلوَ الاعتماد: الرأسُ يُكتب في **ملاحظةٍ** لا في حقل `head` (الذي يُقرأ اعتماداً — v2.23)، فلا ينتحل أحدٌ اعتمادَ المالك.
تُشغَّلها الجلسةُ المنفِّذةُ بعد الإيداع وقبل/مع رسالتها لـ0501؛ وإعادتُها بالرأس نفسه لا تفعل شيئاً.

    python ready_mark.py <بطاقة> --head <sha8> --by <رقمك> [--link http://localhost:8500/…] [--role الدور] [--repo D:/shschool_mvp] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402

DEFAULT_REPO = "D:/shschool_mvp"
FROM_STATES = {"in_progress", "routed", "verified", "notes", "ready_for_review"}
MARK = "جاهزٌ للمعاينة بالرأس "
HEAD_NOTE = re.compile(re.escape(MARK) + r"([0-9a-f]{7,40})")


def git_ok(repo: str, *args: str) -> str | None:
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, encoding="utf-8", errors="replace", check=False)
    return p.stdout.strip() if p.returncode == 0 else None


def declared_head(item: dict) -> str | None:
    """آخرُ رأسٍ أعلنته الجلسةُ في ملاحظات البطاقة (sha8) أو None."""
    for n in reversed(item.get("notes", [])):
        m = HEAD_NOTE.search(n.get("text", ""))
        if m:
            return m.group(1)[:8]
    return None


def mark(card: str, head: str, by: str, repo: str, link: str = "", role: str = "", base: str = "origin/main",
         dry: bool = False, path=None) -> str:
    items = ledger.reduce_state(ledger.load_events(path))
    if card not in items:
        raise ledger.LedgerError(f"بطاقةٌ غيرُ موجودة: {card}")
    item = items[card]
    if not ledger.HEAD_RE.match(head or ""):
        raise ledger.LedgerError("--head <sha8> مطلوب (git rev-parse --short=8 <الفرع>)")
    head8 = head[:8]
    if item["state"] not in FROM_STATES:
        raise ledger.LedgerError(f"«{item['state']}» لا تنتقل إلى ready_for_review بهذه الأداة (الحالات المقبولة: {sorted(FROM_STATES)})")
    full = git_ok(repo, "rev-parse", "--verify", f"{head8}^{{commit}}")
    if not full:
        raise ledger.LedgerError(f"الرأس {head8} غيرُ موجودٍ في {repo} — أودِع أولاً")
    if not git_ok(repo, "log", "-1", "--format=%H", f"--grep={card}", full, f"^{base}"):
        raise ledger.LedgerError(f"لا إيداعَ يحمل رمزَ {card} بين {base} والرأس {head8} — رأسٌ لبطاقةٍ أخرى؟")
    if item["state"] == "ready_for_review" and declared_head(item) == head8:
        return f"لا تغيير: {card} جاهزةٌ أصلاً بالرأس {head8}"
    parts = [f"{MARK}{head8}"] + ([f"الرابط {link}"] if link else []) + ([f"الدور {role}"] if role else [])
    note = "؛ ".join(parts)
    if dry:
        return f"[dry] {card} ← ready_for_review: {note}"
    ledger.move(card, "ready_for_review", path=path, note=note, by=by)
    return f"ok: {card} ← ready_for_review ({note})"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("card")
    ap.add_argument("--head", required=True)
    ap.add_argument("--by", required=True)
    ap.add_argument("--link", default="")
    ap.add_argument("--role", default="")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    path = ledger.ledger_path()
    if not path.is_file():
        # دفترٌ غائبٌ (شجرةٌ نظيفةٌ بلا ledger/events.jsonl غير المتتبَّع) لا يُقال عنه «بطاقةٌ غيرُ موجودة»
        print(f"✗ لا دفترَ في {path} — شغّل الأداةَ من مجلّد المايسترو أو اضبط LEDGER_PATH", file=sys.stderr)
        return 2
    try:
        print(mark(a.card, a.head, a.by, a.repo, a.link, a.role, a.base, a.dry_run))
    except ledger.LedgerError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
