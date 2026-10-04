#!/usr/bin/env python3
"""فحصُ الأرقام الميّتة والمُعاد استعمالُها في الذاكرة وبطاقات الأدوار والمهارات (أسبوعيّاً، قراءةٌ فقط).

    python dead_refs.py [--memory <MEMORY.md>] [--limit 60]

- «ميّت»: رقمٌ لا يعود لجلسة (0203 و0801 و0105 و0204 و0702) — أيُّ ذكرٍ له خارج سياق الإحالة خطأ.
- «مُعاد»: رقمٌ قديمٌ صار لجلسةٍ أخرى (0104 و0201 و0701 و04xx) — يُراجَع المعنى: القديم أم الجديد؟
الخرجُ مرتّبٌ: ميّتٌ نشطٌ ← مُعادٌ ← ما في سياق إحالة (كانت/دُمجت/→). لا يعدّل شيئاً.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from validate_registry import DEAD_NUMBERS

ROOT = Path(__file__).resolve().parent.parent
MEMORY = Path("C:/Users/mesue/.claude/projects/D--shschool-mvp/memory/MEMORY.md")
REUSED_NUMBERS = ("0104", "0201", "0701", "0402", "0403", "0404", "0405", "0406", "0407", "0408")
REFERRAL_CUES = ("كانت", "كان ", "دُمجت", "دمجت", "القديم", "ميّت", "ميتة", "→", "سابقاً", "لا تُعاد", "لا يُعاد")
_NUM = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def scan_text(text: str, source: str) -> list[dict]:
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        for n in dict.fromkeys(m.group(1) for m in _NUM.finditer(line)):  # رقمٌ واحد لكلّ سطر
            kind = "ميّت" if n in DEAD_NUMBERS else "مُعاد" if n in REUSED_NUMBERS else None
            if kind:
                hits.append({"source": source, "line": i, "number": n, "kind": kind,
                             "referral": any(c in line for c in REFERRAL_CUES), "text": line.strip()[:90]})
    return hits


def sort_hits(hits: list[dict]) -> list[dict]:
    rank = lambda h: (h["referral"], h["kind"] != "ميّت", h["number"], h["source"], h["line"])  # noqa: E731
    return sorted(hits, key=rank)


def collect(memory: Path = MEMORY, root: Path = ROOT) -> list[dict]:
    files = [memory] + sorted(p for p in (root / "role_cards").glob("*.md") if p.name != "INDEX.md")
    files += sorted((root / "skills").rglob("*.md"))
    hits: list[dict] = []
    for f in files:
        if f.exists():
            hits += scan_text(f.read_text(encoding="utf-8", errors="replace"), str(f))
    return sort_hits(hits)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--memory", default=str(MEMORY))
    ap.add_argument("--limit", type=int, default=60)
    a = ap.parse_args(argv)
    hits = collect(Path(a.memory))
    live = [h for h in hits if not h["referral"]]
    print(f"أرقامٌ ميّتةٌ/مُعادة: {len(hits)} ذكراً ({len([h for h in live if h['kind'] == 'ميّت'])} ميّتٌ نشط، {len(live)} خارج سياق الإحالة)")
    for h in hits[: a.limit]:
        print(f"  [{h['kind']}{'/إحالة' if h['referral'] else ''}] {h['number']}  {Path(h['source']).name}:{h['line']}  {h['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
