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


def name_problems(title: str, tab_number: str, serial: dict) -> list[str]:
    """الاسمُ «TTSS · <اسمٌ معبّرٌ قصير>»: TT رقمُ التبويب بترتيب الفلو، وSS أقدميّةُ الإنشاء فيه من 01 (D-45م)."""
    head, sep, rest = title.partition(" · ")
    if not (sep and len(head) == 4 and head.isdigit()):
        return [f"«{title}»: الاسمُ يبدأ برقمٍ من أربع خانات (رقمُ التبويب ثمّ التسلسل) ثمّ « · »"]
    problems = []
    # الجلسةُ المرنةُ تُفتح في 04 وتحمل رقمَها وهي تنتقل إلى 05 و06 و07 (D-46م)
    allowed = {tab_number, *serial.get("carried_from", {}).get(tab_number, [])}
    if head[:2] not in allowed:
        problems.append(f"«{title}»: أوّلُ خانتين {head[:2]} لا تطابقان رقمَ مرحلته {tab_number} ولا مرحلةَ فتحٍ مسموحةً فيها")
    if int(head[2:]) < 1:
        problems.append(f"«{title}»: التسلسلُ داخل التبويب يبدأ من 01")
    limit = serial.get("max_title_len", 40)
    if len(title) > limit:
        problems.append(f"«{title}»: الاسمُ أطولُ من {limit} حرفاً — اجعله معبّراً قصيراً")
    if not rest.strip():
        problems.append(f"«{title}»: بعد الرقم اسمٌ معبّر")
    return problems


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
            problems += name_problems(member, tab.get("number", ""), tabs.get("session_policy", {}).get("serial", {}))
    # تبويبٌ فيه أكثرُ من جلسةٍ ثابتة: لا ترث جلسةٌ صلاحيّاتِه ومهاراتِه — يلزم تصريحٌ في ميثاقها نفسِه
    # (خللُ ليلة 10-01/02: وَرِثت 0101..0105 «لا دفع» ومهاراتِ المايسترو من التبويب 01).
    charters = tabs.get("session_policy", {}).get("charters", {})
    for tab in tabs["tabs"]:
        fixed = [m for m in tab.get("members", []) if m in core]
        if len(fixed) < 2:
            continue
        for member in fixed:
            ch = charters.get(member)
            if ch is None:
                problems.append(f"«{member}» في تبويبٍ مشترَك ({tab['id']}) بلا ميثاقٍ يصرّح بصلاحيّاتها ومهاراتها")
                continue
            # القالبُ (render_role_cards) لا يورّث الصلاحيّاتِ من تبويبٍ مشترَك بعد إصلاح 0102؛ فيكفي أن يحوي
            # الميثاقُ حدودَه صراحةً كي لا تُنسب إليها حدودُ غيرها.
            if not ch.get("boundaries"):
                problems.append(f"«{member}»: التبويبُ {tab['id']} مشترَك ولا «حدودَ» صريحةً في ميثاقها")
    for title in core:
        if title not in seen:
            problems.append(f"جلسةُ النواة «{title}» غيرُ مسجَّلةٍ في أيّ تبويب")
    for ptype, spec in routing["problem_types"].items():
        # التوجيهُ بالتبويب؛ أسماءُ المنفّذين والملّاك مرجعٌ لا شرط (الجلساتُ تُفتح عند الطلب — D-43م)
        # التوجيهُ إلى اختصاص (specialties) أو إلى مرحلة (D-46م)
        if spec["tab"] not in ids | {s["id"] for s in tabs.get("specialties", [])} and spec["tab"] != "exec_*":
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
