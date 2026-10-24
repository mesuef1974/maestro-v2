#!/usr/bin/env python3
"""مدقّقُ سجلّ التبويبات والتوجيه: اتّساقُ الأعضاء والمنفّذين والملّاك والحدود. يُشغَّل قبل أيّ نقلٍ للجلسات وبعده.

    python validate_registry.py [--sessions sessions.json]

sessions.json (اختياريّ): قائمةُ عناوين الجلسات الحيّة كما تُرجعها list_sessions ← تُقارَن بالسجلّ (غيرُ مسجَّلة / مسجَّلة بلا جلسة).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_TAB_KEYS = ("id", "name", "order", "layer", "purpose", "goals", "kpis", "inputs", "outputs", "skills", "permissions", "lifecycle", "live_cap", "members")

# أرقامٌ ميّتةٌ لا تُعاد ولم تُستعمل لجلسةٍ أخرى (D-197م/D-198م، docs/session_renumbering_2026-10-04.md).
# أمّا 0104/0201/0701/0702 فأُعيد (0702 أُعيد فتحُها معاوناً لـ0701 بقرار المالك D-315م، 10-10) استعمالُها لجلساتٍ حيّةٍ فليست ميّتة.
# والمدمَجةُ في المرحلة 2 (0102، أمر المالك 2026-10-21) أسماءٌ مستعارةٌ في aliases لا أرقامٌ ميّتة بعدُ:
# جلساتُها القديمةُ ما زالت في session_names.json وsessions_snapshot.json حتى تُؤرشف (alias_problems يحرس اتّساقَها).
# و0201/0301 أُعيدا لجلستين حيّتين بترقيم المجموعة 01 بالترتيب (أمر المالك 2026-10-21 14:02) فهما في «_reused».
DEAD_NUMBERS = ("0203", "0801", "0105", "0204")
FLOW_CHANGELOG_SINCE = "2026-10-04"
_SELF_REF = re.compile(r"(\d{4})\s*(?:دُمجت|دمجت|دُمجَت|مدموجة)\s+في\s+\1(?!\d)")
# الشريطُ قد يكتب «الحوكمة» والسجلُّ «الحوكمةُ»: الفرقُ تشكيلٌ تجميليٌّ لا يُسقط التعرّف، فالسجلُّ هو المصدر
# وتُقارَن العناوينُ الحيّةُ به بلا تشكيلٍ ولا تطويل (ملاحظة 0301 على الجولة 2، 2026-10-21).
_TASHKEEL = re.compile(r"[ً-ْٰـ]")


def bare_title(title: str) -> str:
    """العنوانُ بلا تشكيلٍ ولا تطويل، للمقارنة بين الشريط والسجلّ."""
    return _TASHKEEL.sub("", title)


def self_reference_problems(text: str, where: str = "tabs.json") -> list[str]:
    """عباراتٌ ذاتيّةُ الإحالة مثل «0201 دُمجت في 0201»: رقمٌ مدموجٌ في نفسه لا يُفهم."""
    return [f"{where}: عبارةٌ ذاتيّةُ الإحالة «{m.group(0)}»" for m in _SELF_REF.finditer(text)]


def dead_number_problems(tabs: dict, names: dict | None = None, snapshot: list | None = None,
                         cards: dict[str, str] | None = None) -> list[str]:
    """رقمٌ ميّتٌ يظهر بصفته جلسةً قائمة: عضوٌ أو نواةٌ أو اسمُ جلسةٍ أو لقطةٌ أو عنوانُ بطاقة (غيرِ المدموجة)."""
    found: list[tuple[str, str]] = []
    policy = tabs.get("session_policy", {})
    for t in policy.get("core_sessions", []):
        found.append(("core_sessions", t))
    for tab in tabs.get("tabs", []):
        for m in tab.get("members", []):
            found.append((f"tabs.members[{tab.get('id')}]", m))
    for v in (names or {}).values():
        found.append(("session_names.json", v))
    for t in snapshot or []:
        found.append(("sessions_snapshot.json", t if isinstance(t, str) else str(t.get("title", ""))))
    for fname, text in (cards or {}).items():
        first = next((ln for ln in text.splitlines() if ln.startswith("# ")), "")
        if "دُمجت" in first or "مدموجة" in first:
            continue  # بطاقةُ إحالةٍ مدموجة
        found.append((f"role_cards/{fname}", first.split("—", 1)[-1].strip()))
    out = []
    for where, title in found:
        m = re.search(r"\d{4}", title)
        if m and m.group(0) in DEAD_NUMBERS and title.index(m.group(0)) < 12:
            out.append(f"{where}: الرقمُ الميّت {m.group(0)} يظهر جلسةً قائمة «{title}»")
    return out


def alias_problems(tabs: dict) -> list[str]:
    """اتّساقُ session_policy.aliases مع السجلّ: الرقمُ المستعار لا يبقى جلسةً قائمة، وهدفُه جلسةُ نواةٍ حاليّة،
    وكلُّ ميثاقٍ في charters[*].merged يُحال رقمُه إلى مستقبِلته (المرحلة 2 من الدمج، 2026-10-21)."""
    policy = tabs.get("session_policy", {})
    aliases = {k: v for k, v in policy.get("aliases", {}).items() if not k.startswith("_")}
    reused = policy.get("aliases", {}).get("_reused") or {}
    charters = policy.get("charters", {})
    core = {t[:4] for t in policy.get("core_sessions", [])}
    # هدفُ الإحالة: جلسةُ نواةٍ قائمةٌ أو نواةٌ تنتظر الفتح (core_to_open)
    targets = core | {str(t.get("title", "") if isinstance(t, dict) else t)[:4] for t in policy.get("core_to_open", [])}
    standing = core | {m[:4] for tab in tabs.get("tabs", []) for m in tab.get("members", [])} | {t[:4] for t in charters}
    out = []
    for old, new in aliases.items():
        if old in standing:
            out.append(f"aliases: {old} ← {new} مستعارٌ وما زال جلسةً قائمة (نواةٌ أو عضوٌ أو ميثاق)")
        if new not in targets:
            out.append(f"aliases: هدفُ الإحالة {old} ← {new} ليس جلسةَ نواةٍ حاليّة (أحِل إلى المستقبِلة الأخيرة مباشرةً)")
    for title, ch in charters.items():
        for merged in ch.get("merged") or {}:
            num = merged[:4]
            # رقمٌ مدمَجٌ أُعيد لجلسةٍ حيّةٍ أخرى يُحال في «_reused» (يُحلّ بطلبٍ صريح) لا في الإحالة العاديّة
            ok = aliases.get(num) == title[:4] or (num in standing and reused.get(num) == title[:4])
            if not ok:
                out.append(f"«{merged}» مدمَجٌ في «{title}» بلا إحالة {num} ← {title[:4]} في aliases")
    return out


def changelog_problems(text: str, since: str = FLOW_CHANGELOG_SINCE) -> list[str]:
    """أسطرُ flow_changelog المؤرَّخةُ بعد `since` يلزمها رقمُ إصدار (vN.NN) ورقمُ قرار (D-NNNم). ما قبلها مستثنى."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        full = re.search(r"\b(20\d\d-\d\d-\d\d)\b", line)
        if full:
            date = full.group(1)
        else:
            row = re.match(r"\|\s*v[\d.]+\s*\|\s*(\d\d-\d\d)", line)
            date = f"{since[:4]}-{row.group(1)}" if row else None
        if date and date > since:
            if not re.search(r"\bv\d+\.\d+\b", line):
                out.append(f"flow_changelog.md:{i}: سطرٌ بعد {since} بلا رقم إصدار (vN.NN)")
            if not re.search(r"D-\d+م", line):
                out.append(f"flow_changelog.md:{i}: سطرٌ بعد {since} بلا رقم قرار (D-NNNم)")
    return out


def name_problems(title: str, tab_number: str, serial: dict) -> list[str]:
    """الاسمُ «TTSS · <اسمٌ معبّرٌ قصير>»: TT رقمُ التبويب بترتيب الفلو، وSS أقدميّةُ الإنشاء فيه من 01 (D-45م)."""
    head, sep, rest = title.partition(" · ")
    if not (sep and len(head) == 4 and head.isdigit()):
        return [f"«{title}»: الاسمُ يبدأ برقمٍ من أربع خانات (رقمُ التبويب ثمّ التسلسل) ثمّ « · »"]
    problems = []
    # الجلسةُ المرنةُ تُفتح في 04 وتحمل رقمَها وهي تنتقل إلى 05 و06 و07 (D-46م)
    allowed = {tab_number, *serial.get("carried_from", {}).get(tab_number, [])}
    # تبويبٌ مرقَّمٌ بالترتيب بلا رقمه (serial.ordinal_tabs، المجموعة 01 بأمر المالك 2026-10-21): SS·TT مقبولٌ بجانب TTSS
    ordinal = tab_number in serial.get("ordinal_tabs", {}) and head[2:] == tab_number
    if head[:2] not in allowed and not ordinal:
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
    problems += alias_problems(tabs)
    for ptype, spec in routing["problem_types"].items():
        # التوجيهُ بالتبويب؛ أسماءُ المنفّذين والملّاك مرجعٌ لا شرط (الجلساتُ تُفتح عند الطلب — D-43م)
        # التوجيهُ إلى اختصاص (specialties) أو إلى مرحلة (D-46م)
        if spec["tab"] not in ids | {s["id"] for s in tabs.get("specialties", [])} and spec["tab"] != "exec_*":
            problems.append(f"التوجيه {ptype}: تبويبٌ غيرُ موجود {spec['tab']}")
    if live_titles is not None:
        # جلساتُ المهامّ المجدولة الآليّة ليست مقاعد — تُستثنى بالبادئة
        prefixes = tuple(tabs.get("scheduled_task_title_prefixes", []))
        live_titles = [t for t in live_titles if not (prefixes and t.startswith(prefixes))]
        known = {bare_title(t) for t in seen} | {bare_title(p["title"]) for p in tabs.get("pending_archive", [])}
        live_bare = {bare_title(t) for t in live_titles}
        for title in live_titles:
            if bare_title(title) not in known:
                problems.append(f"جلسةٌ حيّةٌ غيرُ مسجَّلة: «{title}»")
        for title in seen:
            if bare_title(title) not in live_bare:
                problems.append(f"مسجَّلةٌ بلا جلسةٍ حيّة: «{title}»")
    return problems


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sessions")
    ap.add_argument("--project", default="schoolos")
    args = ap.parse_args()
    base = ROOT / "projects" / args.project
    tabs = json.loads((base / "tabs.json").read_text(encoding="utf-8"))
    routing = json.loads((base / "routing.json").read_text(encoding="utf-8"))
    live = json.loads(Path(args.sessions).read_text(encoding="utf-8")) if args.sessions else None
    problems = validate(tabs, routing, live)
    problems += self_reference_problems((base / "tabs.json").read_text(encoding="utf-8"))
    names = json.loads((base / "session_names.json").read_text(encoding="utf-8"))
    snap = json.loads((base / "sessions_snapshot.json").read_text(encoding="utf-8"))
    cards = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "role_cards").glob("*.md") if p.name != "INDEX.md"}
    problems += dead_number_problems(tabs, names, snap if isinstance(snap, list) else [], cards)
    log = ROOT / "flow_changelog.md"
    if log.exists():
        problems += changelog_problems(log.read_text(encoding="utf-8"))
    print("\n".join(problems) if problems else "السجلُّ متّسق")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
