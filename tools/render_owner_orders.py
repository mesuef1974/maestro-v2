#!/usr/bin/env python3
"""يولّد owner_orders_auto.md من decisions.md: كلُّ قرارٍ مصدرُه المالك (حقلُ المرجع يذكره) — لتصالحَ عليه «0202 · طلبات المالك».

    python render_owner_orders.py

لا يمسّ owner_requests.md (دفترُ 0202 اليدويّ)؛ هذا ملفٌّ آليٌّ منفصلٌ يكشف الأوامرَ المباشرةَ التي لم تمرّ بها (D-107م).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = re.compile(r"^- D-(\d+)م \| ([^|]*)\| (.*)$")


def owner_rows(text: str) -> list[tuple[str, str, str]]:
    rows = []
    for line in text.splitlines():
        m = ENTRY.match(line)
        if not m:
            continue
        parts = [p.strip() for p in m.group(3).split(" | ")]
        source = parts[-1] if len(parts) >= 3 else ""
        if "المالك" in source:
            summary = re.sub(r"\*+", "", parts[0])[:170]
            rows.append((f"D-{m.group(1)}م", m.group(2).strip(), summary))
    return rows


def render(rows: list[tuple[str, str, str]]) -> str:
    out = ["# أوامرُ المالك المستخرَجةُ آليّاً من decisions.md (لا يُحرَّر يدويّاً)", "",
           "> للمصالحة مع `owner_requests.md` (دفترُ 0202): كلُّ صفٍّ أمرٌ أو قرارٌ مصدرُه المالك. الأوامرُ التي بلا بطاقةٍ أو متابعةٍ هنا تُرفَع إلى 0201.", "",
           f"عددُ الصفوف: {len(rows)}", "", "| القرار | متى | الملخّص |", "|---|---|---|"]
    out += [f"| {a} | {b} | {c.replace('|', '/')} |" for a, b, c in rows]
    return "\n".join(out) + "\n"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    arch = ROOT / "decisions_archive.md"  # أوامرُ المالك المؤرشفة تبقى في الناتج (W-20261025-016)
    rows = owner_rows((arch.read_text(encoding="utf-8") + chr(10) if arch.is_file() else "") + (ROOT / "decisions.md").read_text(encoding="utf-8"))
    (ROOT / "owner_orders_auto.md").write_text(render(rows), encoding="utf-8")
    print(f"owner_orders_auto.md ✔ ({len(rows)} صفّاً)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
