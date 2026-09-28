#!/usr/bin/env python3
"""مدقّقُ سجلّ التبويبات والتوجيه: اتّساقُ الأعضاء والمنفّذين والملّاك والحدود. يُشغَّل قبل أيّ نقلٍ للجلسات وبعده.

    python validate_registry.py [--sessions sessions.json]

sessions.json (اختياريّ): قائمةُ عناوين الجلسات الحيّة كما تُرجعها list_sessions ← تُقارَن بالسجلّ (غيرُ مسجَّلة / مسجَّلة بلا جلسة).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_TAB_KEYS = ("id", "name", "order", "layer", "purpose", "goals", "kpis", "inputs", "outputs", "skills", "permissions", "lifecycle", "live_cap", "members")


def validate(tabs: dict, routing: dict, live_titles: list[str] | None = None) -> list[str]:
    problems: list[str] = []
    seen: dict[str, str] = {}
    orders, ids = set(), set()
    for tab in tabs["tabs"]:
        for key in REQUIRED_TAB_KEYS:
            if key not in tab or tab[key] in ("", [], None):
                problems.append(f"التبويب {tab.get('id', '؟')}: الحقل {key} ناقص")
        if tab.get("id") in ids:
            problems.append(f"معرّفٌ مكرَّر: {tab.get('id')}")
        ids.add(tab.get("id"))
        if tab.get("order") in orders:
            problems.append(f"ترتيبٌ مكرَّر: {tab.get('order')}")
        orders.add(tab.get("order"))
        if len(tab.get("members", [])) > tab.get("live_cap", 0):
            problems.append(f"التبويب {tab['id']}: الأعضاءُ ({len(tab['members'])}) فوق الحدّ ({tab.get('live_cap')})")
        for member in tab.get("members", []):
            if member in seen:
                problems.append(f"«{member}» في تبويبَين: {seen[member]} و{tab['id']}")
            seen[member] = tab["id"]
    for ptype, spec in routing["problem_types"].items():
        for who in spec["executors"] + spec["owners"]:
            if who != "file_owner" and who not in seen:
                problems.append(f"التوجيه {ptype}: «{who}» غيرُ مسجَّلة في أيّ تبويب")
        if spec["tab"] not in ids and spec["tab"] != "exec_*":
            problems.append(f"التوجيه {ptype}: تبويبٌ غيرُ موجود {spec['tab']}")
    if live_titles is not None:
        known = set(seen) | {p["title"] for p in tabs.get("pending_archive", [])}
        for title in live_titles:
            if title not in known:
                problems.append(f"جلسةٌ حيّةٌ غيرُ مسجَّلة: «{title}»")
        for title in seen:
            if title not in live_titles:
                problems.append(f"مسجَّلةٌ بلا جلسةٍ حيّة: «{title}»")
    return problems


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sessions"); ap.add_argument("--project", default="schoolos")
    args = ap.parse_args()
    base = ROOT / "projects" / args.project
    tabs = json.loads((base / "tabs.json").read_text(encoding="utf-8"))
    routing = json.loads((base / "routing.json").read_text(encoding="utf-8"))
    live = json.loads(Path(args.sessions).read_text(encoding="utf-8")) if args.sessions else None
    problems = validate(tabs, routing, live)
    print("\n".join(problems) if problems else "السجلُّ متّسق")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
