#!/usr/bin/env python3
"""فهرسُ القرارات: يولّد decisions_index.md من decisions.md (قراءةٌ من الأصل، لا حذفَ منه ولا تعديل).

    python tools/decisions_index.py            # يكتب decisions_index.md
    python tools/decisions_index.py --check    # يخرج بـ1 إن كان الفهرسُ على القرص غيرَ مطابقٍ للتوليد الطازج

الأعمدة: رقمُ القرار، التاريخ، عنوانٌ (أولُ النص مقطوعاً)، الحالة، سطرُ الأثر. الحالةُ استدلالٌ آليٌّ من النص:
«مُعدَّل» إن ذكر قرارٌ لاحق «يلغي/يحلّ محلّ/ينسخ/يستبدل/ملغى» بجوارها رقمَ هذا القرار، وإلا «ساري».
هي استدلالٌ لا حكم؛ المرجع الحاكم decisions.md. التوليدُ idempotent: الدخلُ نفسُه يعطي الخرجَ نفسَه بالبايت.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "decisions.md"
OUT = ROOT / "decisions_index.md"
ENTRY = re.compile(r"^- D-(\d+)(?:م)?(-[ء-ي])?(?: \([^)]*\))? \| ([^|]*)\| (.*)$")
HEADING = re.compile(r"^## D-(\d+)م(-[ء-ي])?\s*\(([^)]*)\)\s*[:：]?\s*(.*)$")
SUPERSEDE = re.compile(r"(?:يلغي|يُلغي|يُلغى|تُلغي|تلغي|ملغى|مُلغى|يحلّ محلّ|تحلّ محلّ|ينسخ|يستبدل)[^|D\n]{0,40}D-(\d+)")
TITLE_LEN = 60
EFFECT_LEN = 50


def clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s.replace("|", "/")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def parse(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        m = ENTRY.match(line)
        if m:
            parts = [p.strip() for p in m.group(4).split(" | ")]
            rows.append({"id": line[2:].split(" |")[0], "num": int(m.group(1)), "date": m.group(3).strip(),
                         "title": parts[0], "effect": parts[1] if len(parts) > 1 else "", "body": m.group(4)})
            continue
        h = HEADING.match(line)
        if h:
            rows.append({"id": f"D-{h.group(1)}م{h.group(2) or ''}", "num": int(h.group(1)), "date": h.group(3).strip(),
                         "title": h.group(4), "effect": "", "body": line})
    return rows


def render(text: str) -> str:
    rows = parse(text)
    changed: dict[int, set[int]] = {}
    for r in rows:
        for t in SUPERSEDE.findall(r["body"]):
            if int(t) < r["num"]:
                changed.setdefault(int(t), set()).add(r["num"])
    out = ["# فهرس القرارات (مولَّد آلياً من decisions.md؛ لا يُحرَّر يدوياً)", "",
           "> يُولَّد بـ`python tools/decisions_index.py`. المرجع الحاكم decisions.md كاملاً بلا حذف. الحالةُ استدلالٌ آليٌّ من النص (ذكرُ إلغاءٍ أو إحلالٍ في قرارٍ لاحق) لا حكم.", "",
           f"عدد القرارات: {len(rows)}", "", "| القرار | التاريخ | العنوان | الحالة | الأثر |", "|---|---|---|---|---|"]
    for r in rows:
        by = sorted(changed.get(r["num"], ()))
        status = "مُعدَّل بـ" + "،".join(f"D-{n}م" for n in by[:3]) if by else "ساري"
        out.append(f"| {r['id']} | {clip(r['date'], 20)} | {clip(r['title'], TITLE_LEN)} | {status} | {clip(r['effect'], EFFECT_LEN)} |")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    arch = SRC.with_name("decisions_archive.md")  # الفهرسُ يغطّي الأرشيفَ والحيَّ معاً (W-20261025-016)
    old = arch.read_bytes().decode("utf-8").replace("\r\n", "\n") + "\n" if arch.is_file() else ""
    fresh = render(old + SRC.read_bytes().decode("utf-8").replace("\r\n", "\n"))
    if a.check:
        cur = OUT.read_bytes().decode("utf-8").replace("\r\n", "\n") if OUT.exists() else ""
        if cur != fresh:
            print("decisions_index.md غيرُ مطابق للتوليد الطازج: شغّلي python tools/decisions_index.py")
            return 1
        print("الفهرس مطابق")
        return 0
    OUT.write_bytes(fresh.encode("utf-8"))
    print(f"decisions_index.md ✔ ({len(fresh.encode('utf-8'))} بايت من {SRC.stat().st_size})")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
