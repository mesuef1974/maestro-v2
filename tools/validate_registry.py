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


def name_problems(title: str, is_core: bool, prefix: str, serial: dict) -> list[str]:
    """الاسمُ «NNN · <بادئة التبويب> · <المهمّة>»: الرقمُ يرتّب الجلسةَ داخل تبويبها (D-44م) — النواةُ في المحجوز، والباقي بأقدميّته."""
    head, sep, rest = title.partition(" · ")
    if not (sep and len(head) == 3 and head.isdigit()):
        return [f"«{title}»: الاسمُ يبدأ برقمٍ من ثلاث خانات ثمّ « · »"]
    lo, hi = serial.get("core_range", [1, 99])
    if is_core and not lo <= int(head) <= hi:
        return [f"«{title}»: رقمُ جلسةِ النواة خارج المحجوز {lo:03d}..{hi:03d}"]
    if not is_core:
        if int(head) < serial.get("task_start", 101):
            return [f"«{title}»: رقمُ جلسة المهمّة يبدأ من {serial.get('task_start', 101)}"]
        if not rest.startswith(f"{prefix} · "):
            return [f"«{title}»: بعد الرقم بادئةُ التبويب «{prefix} · » ثمّ المهمّة"]
    return []


def validate(tabs: dict, routing: dict, live_titles: list[str] | None = None) -> list[str]:
    problems: list[str] = []
    seen: dict[str, str] = {}
    orders, ids = set(), set()
    core = set(tabs.get("session_policy", {}).get("core_sessions", []))
    for tab in tabs["tabs"]:
        for key in REQUIRED_TAB_KEYS:
            # الأعضاءُ قد تكون فارغةً: الجلسةُ تُفتح عند الطلب (D-43م)
            if key not in tab or (key != "members" and tab[key] in ("", [], None)):
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
            problems += name_problems(member, member in core, tab.get("title_prefix", ""), tabs.get("session_policy", {}).get("serial", {}))
    for title in core:
        if title not in seen:
            problems.append(f"جلسةُ النواة «{title}» غيرُ مسجَّلةٍ في أيّ تبويب")
    for ptype, spec in routing["problem_types"].items():
        # التوجيهُ بالتبويب؛ أسماءُ المنفّذين والملّاك مرجعٌ لا شرط (الجلساتُ تُفتح عند الطلب — D-43م)
        if spec["tab"] not in ids and spec["tab"] != "exec_*":
            problems.append(f"التوجيه {ptype}: تبويبٌ غيرُ موجود {spec['tab']}")
    if live_titles is not None:
        # جلساتُ المهامّ المجدولة الآليّة ليست مقاعد — تُستثنى بالبادئة
        prefixes = tuple(tabs.get("scheduled_task_title_prefixes", []))
        live_titles = [t for t in live_titles if not (prefixes and t.startswith(prefixes))]
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
