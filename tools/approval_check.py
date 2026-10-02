#!/usr/bin/env python3
"""هل اعتمد المالكُ هذا؟ — تحقّقٌ آليٌّ من المصدر بدل سؤال المالك أو الجلسات (أمر المالك 2026-10-02).

    python approval_check.py card W-20260930-005
    python approval_check.py pr 772

المصادر بالترتيب: (١) حالةُ البطاقة في الدفتر — لا تبلغ approved وما بعدها إلا بـ`ledger.py move … --note` (قاعدةُ D-73م)،
(٢) أحداثُ الاعتماد approvals في الدفتر، (٣) سطرُ الاعتماد في وصف طلب الدمج، (٤) `owner_confirmations.md`.
يخرج برمز 0 إن ثبت الاعتماد من مصدرٍ واحد على الأقلّ، و2 إن لم يثبت — وحينها تسأل الجلسةُ **0501 أو 0101** (من تلقّى الاعتماد) لا المالك.
قراءةٌ فقط.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_DIR = "D:/shschool_mvp"
APPROVED_STATES = {"approved", "pushed", "merged", "published", "closed"}
APPROVAL_LINE = re.compile(r"اعتُمد من المالك[^\n]*|اعتمد المالك[^\n]*")


def run(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "")


# اعتماداتٌ قديمةٌ بلا رأسٍ تُقبل بتحذيرٍ حتى هذا التاريخ ثمّ تُرفض (قرار 0101، v2.23)
LEGACY_DEADLINE = date(2026, 10, 9)
HEAD_IN_LINE = re.compile(r"(?:الرأس|@)\s*([0-9a-f]{7,40})")


def head_status(approved: str | None, pr_head: str | None, today: date | None = None) -> str:
    """ok: متطابقان أو لا رأسَ للمقارنة؛ stale: اختلفا؛ legacy: اعتمادٌ بلا رأس؛ expired: بلا رأسٍ وبعد المهلة."""
    today = today or date.today()
    if not approved:
        return "legacy" if today <= LEGACY_DEADLINE else "expired"
    if pr_head and approved[:8] != pr_head[:8]:
        return "stale"
    return "ok"


def card_evidence(card: str, pr_head: str | None = None) -> list[tuple[str, str]]:
    code, out = run([sys.executable, str(ROOT / "tools" / "ledger.py"), "show", card])
    try:
        d = json.loads(out)
    except ValueError:
        return []
    ev: list[tuple[str, str]] = []
    st = head_status(d.get("approved_head"), pr_head)
    if d.get("state") in APPROVED_STATES:
        ev.append((f"الدفتر: حالةُ {card} = {d['state']} (رأسُ الاعتماد {d.get('approved_head') or 'غيرُ مسجَّل'})", st))
    for a in d.get("approvals", []):
        ev.append((f"الدفتر: اعتمادٌ by={a.get('by')} via={a.get('via', '')} {a.get('ts', '')[:16]}", st))
    for n in d.get("notes", []):
        txt = str(n.get("note", n.get("text", "")))
        if txt.startswith("استثناءُ رأس"):
            ev.append((f"الدفتر: تنازلٌ مسجَّل {n.get('ts', '')[:16]}: {txt[:110]}", st))
        if "اعتمد" in str(n.get("note", n.get("text", ""))):
            ev.append((f"الدفتر: ملاحظةٌ {n.get('ts', '')[:16]}: {str(n.get('note', n.get('text', '')))[:100]}", st))
    return ev


def pr_evidence(num: str) -> tuple[list[tuple[str, str]], str | None, str | None]:
    code, out = run(["gh", "pr", "view", num, "--json", "title,body,state,headRefOid"], cwd=REPO_DIR)
    if code != 0:
        return [], None, None
    d = json.loads(out)
    pr_head = (d.get("headRefOid") or "")[:8] or None
    ev = []
    for m in APPROVAL_LINE.findall(d.get("body") or "")[:1]:
        h = HEAD_IN_LINE.search(m)
        ev.append((f"الطلب #{num} ({d['state']}): {m.strip()[:110]}", head_status(h.group(1) if h else None, pr_head)))
    card = re.search(r"W-\d{8}-\d{3}", d.get("title", "") + (d.get("body") or ""))
    return ev, card.group(0) if card else None, pr_head


def confirmations_evidence(key: str, pr_head: str | None = None) -> list[tuple[str, str]]:
    f = ROOT / "owner_confirmations.md"
    if not f.exists():
        return []
    out = []
    for ln in f.read_text(encoding="utf-8").splitlines():
        if key in ln:
            h = HEAD_IN_LINE.search(ln)
            tail = " ← إفادةُ جلسةٍ تُدقَّق بالعيّنة" if "إفادةُ جلسة" in ln else ""
            out.append((f"owner_confirmations.md: {ln.strip()[:120]}{tail}", head_status(h.group(1) if h else None, pr_head)))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("kind", choices=["card", "pr"])
    ap.add_argument("target")
    ap.add_argument("--head", help="للبطاقة: رأسُ الإيداع الحاليّ للمقارنة (sha8)")
    a = ap.parse_args()
    ev: list[tuple[str, str]] = []
    pr_head = a.head
    if a.kind == "card":
        ev += card_evidence(a.target, pr_head)
    else:
        pev, card, pr_head = pr_evidence(a.target)
        ev += pev
        if card:
            ev += card_evidence(card, pr_head)
    ev += confirmations_evidence(a.target, pr_head)
    good = [e for e in ev if e[1] in ("ok", "legacy")]
    stale = [e for e in ev if e[1] == "stale"]
    if good:
        print("✔ الاعتمادُ ثابتٌ من المصدر — لا تسألي المالكَ:")
        for t, st in good:
            print(f"  - {t}" + ("  ⚠ بلا رأسٍ (مقبولٌ حتى 2026-10-09 ثمّ يُرفض)" if st == "legacy" else ""))
        if stale:
            print("  (تجاهلتُ اعتماداتٍ على رأسٍ مختلف:)")
            for t, _ in stale:
                print(f"  - {t}")
        return 0
    if stale:
        print(f"✘ الاعتمادُ على رأسٍ غيرِ رأس الإيداع الحاليّ ({pr_head}): لا يسري على إيداعاتٍ لاحقةٍ لم يرها المالك.")
        for t, _ in stale:
            print(f"  - {t}")
        print("  أعيدي المعاينةَ على الرأس الجديد ثمّ سجّلي اعتماداً بـ--head، أو استثناءَ تافهٍ بتوقيع 0501 (`ledger.py waive-head`، وثائقُ فقط).")
        return 3
    if ev:
        print("✘ اعتماداتٌ بلا رأسٍ انتهت مهلتُها (2026-10-09): سجّلي اعتماداً جديداً بـ--head.")
        return 3
    print("✘ لا اعتمادَ مسجَّلاً في المصدر. لا تسألي المالكَ مباشرةً: اسألي 0501 (إن كان معاينةً) أو 0101 أن تسجّل الاعتمادَ بـ`ledger.py move … approved --head <sha8> --note` ثمّ أعيدي الفحص.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
