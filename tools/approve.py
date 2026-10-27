#!/usr/bin/env python3
"""اعتمادُ 0101 بتفويض D-443م في أمرٍ واحد: كلُّ الخطوات أو لا شيء، وسببُ رفضٍ واحدٌ واضح (W-20261026-013).

الخطواتُ التي كانت تُنفَّذ يدويّاً بترتيبٍ صارمٍ لا يظهر إلا بالرفض:
  1) الفحصُ قبل أيّ كتابة: المعتمِد 0101، والبطاقةُ في ready_for_review بالرأس المعلَن، والرأسُ يطابق الشجرة، والفرقُ لا يمسّ
     واجهةً ولا هجرةً ولا صلاحيّاتٍ ولا ملفّاً حاكماً، و--reviewed يصف ما رُوجع؛
  2) سطرُ التفويض في owner_confirmations.md (ما يقرؤه approval_check)؛
  3) حدثُ التفويض وحالةُ approved بالرأس في الدفتر (يُسترجع سطرُ الخطوة 2 إن فشلت هذه);
  4) التحقّقُ بـapproval_check على الرأس نفسه.

    python approve.py <بطاقة> --head <sha8> --by 0101 --reviewed "ما رُوجع في الفرق (20 حرفاً فأكثر)" [--tree <شجرة الفرع>] [--base origin/main]

بلا --tree يُحسب الفرقُ في مستودع الأدوات نفسِه على الرأس المعطى (فرعٌ مدفوعٌ أو محلّيّ).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402
import record_owner_confirmation as oc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HEAD_RE = re.compile(r"^[0-9a-f]{7,40}$")


class RefusedError(Exception):
    """رفضٌ بسببٍ واحد؛ لم يُكتب شيء."""


def _git(tree: str, *args: str) -> str:
    return oc.git_out(tree, *args)


def check_approval(card: str, head: str) -> tuple[bool, str]:
    """يشغّل approval_check على الرأس؛ (نجح؟، أوّلُ سطرٍ مفيد)."""
    p = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "approval_check.py"), "card", card, "--head", head],  # noqa: S603
                       capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    lines = [ln for ln in (p.stdout or "").splitlines() if ln.startswith(("✔", "✘"))]
    return p.returncode == 0 and any(ln.startswith("✔") for ln in lines), (lines[0] if lines else (p.stdout or p.stderr).strip()[:200])


def precheck(card: str, head: str, by: str, reviewed: str, tree: str | None, base: str, items: dict | None = None,
             git=_git) -> tuple[str, list[str]]:
    """كلُّ الفحوص بلا كتابة. يعيد (الرأس الكامل، ملفّات الفرق) أو يرفع RefusedError بسببٍ واحد."""
    if by != "0101":
        raise RefusedError("الاعتماد بالتفويض لـ0101 وحدَها (D-443م)")
    if not HEAD_RE.match(head or ""):
        raise RefusedError("--head يلزمه sha من 7 إلى 40 خانة (git rev-parse --short=8 <الفرع>)")
    if len(reviewed.strip()) < 20:
        raise RefusedError("--reviewed إلزاميّ: ما رُوجع في الفرق الفعليّ (20 حرفاً فأكثر)")
    items = items if items is not None else ledger.reduce_state(ledger.load_events())
    item = items.get(card)
    if item is None:
        raise RefusedError(f"لا بطاقةَ {card} في الدفتر")
    state = item.get("state")
    if state != "ready_for_review":
        raise RefusedError(f"حالةُ {card} «{state}» — الاعتمادُ لبطاقةٍ في ready_for_review فقط" + (" (اعتُمدت أصلاً)" if state in ledger.ALREADY_APPROVED else ""))
    ready = (item.get("ready_head") or "").strip()
    n = min(len(ready), len(head))
    if not ready or ready[:n].lower() != head[:n].lower():
        raise RefusedError(f"الرأسُ المعلَن جاهزاً {ready[:8] or '—'} ≠ الرأس المطلوب {head[:8]}: تعلنه الجلسةُ بـledger.py move … ready_for_review --head-now")
    where = tree or str(ROOT)
    try:
        full = git(where, "rev-parse", "HEAD" if tree else head)
        diff = [f for f in git(where, "diff", "--no-renames", "--name-only", f"{base}...{full}").splitlines() if f.strip()]
    except ValueError as exc:
        raise RefusedError(str(exc)) from exc
    problem = oc.delegation_problem(item, card, head, diff, full, reviewed, by)
    if problem:
        raise RefusedError(problem)
    bad = ledger.delegation_blockers(diff)
    if bad:
        raise RefusedError("يُعرض على المالك لا بالتفويض: " + "؛ ".join(bad[:6]))
    return full, diff


def approve(card: str, head: str, by: str, reviewed: str, tree: str | None = None, base: str = "origin/main",
            confirmations: Path | None = None, check=check_approval, git=_git, ledger_path=None) -> str:
    """ينفّذ الخطوات الأربع. يعيد سطرَ النجاح أو يرفع RefusedError (قبل الكتابة) أو RuntimeError (فشلٌ بعد الكتابة، مع التراجع الممكن)."""
    full, diff = precheck(card, head, by, reviewed, tree, base, items=ledger.reduce_state(ledger.load_events(ledger_path)), git=git)
    path = confirmations or oc.FILE
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        quote, _ = oc.standing_quote(before)
    except ValueError as exc:
        raise RefusedError(str(exc)) from exc
    question = f"اعتماد رأس {head} بتفويض D-443م بعد مراجعة الفرق: {reviewed.strip()} (ملفّات الفرق: {len(diff)})"
    path.write_text(before + oc.row(by, card, quote, question, head=head, source="مباشر"), encoding="utf-8")
    try:
        ledger.record_delegation(card, head, by, path=ledger_path, repo=tree or str(ROOT), changed=diff)
    except ledger.LedgerError as exc:
        path.write_text(before, encoding="utf-8")  # لا يبقى سطرُ تفويضٍ بلا حدثٍ في الدفتر
        raise RefusedError(f"رفضه الدفتر فتُراجع السطر: {exc}") from exc
    ok, line = check(card, head)
    if not ok:
        raise RuntimeError(f"سُجّل التفويض لكنّ approval_check لم يؤكّده: {line}")
    return f"اعتُمدت {card} على الرأس {head[:8]} بتفويض D-443م ({len(diff)} ملفّاً) — {line}"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("card")
    ap.add_argument("--head", required=True)
    ap.add_argument("--by", required=True)
    ap.add_argument("--reviewed", required=True, help="ما رُوجع في الفرق (20 حرفاً فأكثر)")
    ap.add_argument("--tree", help="شجرةُ الفرع؛ بلا قيمةٍ يُحسب الفرقُ في مستودع الأدوات على الرأس")
    ap.add_argument("--base", default="origin/main")
    a = ap.parse_args(argv)
    try:
        print(approve(a.card, a.head, a.by, a.reviewed, a.tree, a.base))
    except RefusedError as exc:
        print(f"✘ لا اعتماد: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
