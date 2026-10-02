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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_DIR = "D:/shschool_mvp"
APPROVED_STATES = {"approved", "pushed", "merged", "published", "closed"}
APPROVAL_LINE = re.compile(r"اعتُمد من المالك[^\n]*|اعتمد المالك[^\n]*")


def run(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "")


def card_evidence(card: str) -> list[str]:
    code, out = run([sys.executable, str(ROOT / "tools" / "ledger.py"), "show", card])
    try:
        d = json.loads(out)
    except ValueError:
        return []
    ev = []
    if d.get("state") in APPROVED_STATES:
        ev.append(f"الدفتر: حالةُ {card} = {d['state']} (لا تبلغها بطاقةٌ إلا بملاحظة اعتماد)")
    for a in d.get("approvals", []):
        ev.append(f"الدفتر: اعتمادٌ by={a.get('by')} via={a.get('via', '')} {a.get('ts', '')[:16]}")
    for n in d.get("notes", []):
        if "اعتمد" in str(n.get("note", n.get("text", ""))):
            ev.append(f"الدفتر: ملاحظةٌ {n.get('ts', '')[:16]}: {str(n.get('note', n.get('text', '')))[:100]}")
    return ev


def pr_evidence(num: str) -> tuple[list[str], str | None]:
    code, out = run(["gh", "pr", "view", num, "--json", "title,body,state"], cwd=REPO_DIR)
    if code != 0:
        return [], None
    d = json.loads(out)
    ev = [f"الطلب #{num} ({d['state']}): {m.strip()[:110]}" for m in APPROVAL_LINE.findall(d.get("body") or "")[:1]]
    card = re.search(r"W-\d{8}-\d{3}", d.get("title", "") + (d.get("body") or ""))
    return ev, card.group(0) if card else None


def confirmations_evidence(key: str) -> list[str]:
    f = ROOT / "owner_confirmations.md"
    if not f.exists():
        return []
    return [f"owner_confirmations.md: {ln.strip()[:120]}" for ln in f.read_text(encoding="utf-8").splitlines() if key in ln]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("kind", choices=["card", "pr"])
    ap.add_argument("target")
    a = ap.parse_args()
    ev: list[str] = []
    if a.kind == "card":
        ev += card_evidence(a.target)
    else:
        pev, card = pr_evidence(a.target)
        ev += pev
        if card:
            ev += card_evidence(card)
    ev += confirmations_evidence(a.target)
    if ev:
        print("✔ الاعتمادُ ثابتٌ من المصدر — لا تسألي المالكَ:")
        print("\n".join(f"  - {e}" for e in ev))
        return 0
    print("✘ لا اعتمادَ مسجَّلاً في المصدر. لا تسألي المالكَ مباشرةً: اسألي 0501 (إن كان معاينةً) أو 0101 أن تسجّل الاعتمادَ بـ`ledger.py move … approved --note` ثمّ أعيدي الفحص.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
