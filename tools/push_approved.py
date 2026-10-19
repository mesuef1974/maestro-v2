#!/usr/bin/env python3
"""دفعٌ آليّ لفرع بطاقةٍ معتمَدة (W-20261015-004، أمر المالك 2026-10-15) — عرضٌ افتراضيّاً و`--apply` للدفع.

    python push_approved.py W-20261015-004 --repo D:/shschool_mvp/.claude/worktrees/x --branch claude/task-name
    python push_approved.py W-… --repo … --branch claude/… --apply

يجمع في أمرٍ واحد: التحقّق من الاعتماد (approval_check ✔ بالرأس) ← حارس الرأس ← الدفع ← التحقّق من البعيد ← التدوين في الدفتر.

الحارس (يرفض بلا دفع): الفرعُ غير claude/* (لا main ولا غيره)؛ رأسُ الاعتماد في الدفتر غائب؛ HEAD الشجرة ≠ الرأس المعتمَد حرفيّاً؛
في الشجرة تعديلٌ غيرُ مودَع في ملفٍّ متتبَّع (الملفّاتُ تغيّرت بعد الاعتماد)؛ البطاقةُ ليست approved.
الدفعُ دائماً `HEAD:refs/heads/<الفرع>` بلا `--force`؛ ولا دمج ولا طلب دمج (0601 وحدَها). التدوين: مذكّرةٌ ثمّ انتقالٌ إلى pushed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ledger  # noqa: E402

BRANCH_RE = re.compile(r"^claude/[A-Za-z0-9._/-]+$")


class PushRefused(RuntimeError):
    pass


def _git(repo: str, *args: str) -> tuple[int, str]:
    p = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    return p.returncode, (p.stdout or "") + (p.stderr if p.returncode else "")


MIN_HEAD = 7


def same_head(a: str, b: str) -> bool:
    """تطابقُ رأسين ببادئةٍ مشتركةٍ بطول الأقصر منهما (٧ أحرف فأكثر): الدفترُ قد يحمل رأساً بسبعة أو ثمانية أحرف (W-20261019-021)."""
    a, b = a.strip().lower(), b.strip().lower()
    n = min(len(a), len(b))
    return n >= MIN_HEAD and a[:n] == b[:n]


def approval_ok(card: str, head: str) -> bool:
    p = subprocess.run(
        [sys.executable, "-X", "utf8", str(HERE / "approval_check.py"), "card", card, "--head", head],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    return p.returncode == 0


def guard(card: str, branch: str, repo: str, items: dict, git=_git, approved=approval_ok) -> str:
    """يعيد رأسَ الشجرة الكامل إن اجتاز كلُّ الحرّاس، وإلا يرفع PushRefused بالسبب."""
    if not BRANCH_RE.match(branch) or ".." in branch:
        raise PushRefused(f"الفرعُ «{branch}» ليس claude/<اسم>: تدفع هذه الأداةُ فروعَ البطاقات فقط (لا main)")
    item = items.get(card)
    if not item:
        raise PushRefused(f"بطاقةٌ غيرُ موجودة: {card}")
    if item.get("state") != "approved":
        raise PushRefused(f"البطاقةُ في «{item.get('state')}» لا approved: لا دفعَ")
    want = (item.get("approved_head") or "").strip()
    if not want:
        raise PushRefused("لا رأسَ اعتمادٍ في الدفتر: لا دفعَ بلا رأس")
    rc, head = git(repo, "rev-parse", "HEAD")
    head = head.strip()
    if rc or not head:
        raise PushRefused("تعذّرت قراءةُ HEAD في الشجرة")
    if not same_head(head, want):
        raise PushRefused(f"HEAD الشجرة {head[:8]} ≠ الرأس المعتمَد {want[:8]}: إيداعٌ بعد الاعتماد يُبطله")
    rc, dirty = git(repo, "status", "--porcelain", "--untracked-files=no")
    if rc or dirty.strip():
        raise PushRefused("في الشجرة تعديلٌ غيرُ مودَع لملفٍّ متتبَّع: الملفّاتُ تغيّرت بعد الاعتماد")
    if not approved(card, want):
        raise PushRefused("approval_check لم يخرج بـ✔ على هذا الرأس")
    return head


def push(card: str, branch: str, repo: str, apply: bool = False, path=None, git=_git, approved=approval_ok, by: str | None = None) -> str:
    items = ledger.reduce_state(ledger.load_events(path))
    head = guard(card, branch, repo, items, git, approved)
    if not apply:
        return f"عرض: يُدفع {head[:8]} إلى origin/{branch} (HEAD:refs/heads/{branch}) ثمّ يُدوَّن pushed — أضف --apply"
    rc, out = git(repo, "push", "origin", f"HEAD:refs/heads/{branch}")
    if rc:
        raise PushRefused("فشل الدفع: " + out.strip()[-200:])
    rc, remote = git(repo, "ls-remote", "origin", f"refs/heads/{branch}")
    if rc or not remote.split() or remote.split()[0] != head:
        raise PushRefused(f"البعيدُ لا يطابق بعد الدفع: {remote.strip()[:80]}")
    ledger.add_note(card, f"دُفع الفرع {branch} بالرأس {head[:8]} آلياً (push_approved) بعد approval_check ✔ وحارس الرأس", by or "0701", path)
    # فحصُ البعيد جرى أعلاه في شجرة البطاقة (قد تكون مستودعاً غير مستودع المنصّة) فنمرّر نتيجتَه لا فحصَ ledger الافتراضيّ
    ledger.move(card, "pushed", path=path, by=by, head=head[:8], branch=branch, remote_lookup=lambda _b: head)
    return f"دُفع {head[:8]} إلى origin/{branch}؛ دُوّن pushed. سلّم البطاقة والفرع لـ0501 ثمّ 0601."


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("card")
    ap.add_argument("--repo", required=True, help="شجرةُ العمل التي فيها الفرع")
    ap.add_argument("--branch", required=True, help="claude/<اسم-المهمّة>")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--by", help="رقمُ جلسة الدافع (للدفتر)")
    a = ap.parse_args(argv)
    try:
        print(push(a.card, a.branch, a.repo, a.apply, by=a.by))
    except (PushRefused, ledger.LedgerError) as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
