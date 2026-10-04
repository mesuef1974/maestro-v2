#!/usr/bin/env python3
"""فحصُ ما قبل الاستحداث — قراءةٌ فقط، لا يفتح جلسة؛ ولا يكتب إلّا بـ--reserve (حجزُ رقم البطاقة).

يبني اسمَ الجلسة المرنة «04SS · <الوسم>: <المهمّة> (<الرمز>)» ويدقّقه بقواعد validate_registry نفسِها،
ويقرأ السعة: أعضاءُ 04 مقابل live_cap، والذاكرةُ المتاحة بعتبات thresholds.json، وجلسةٌ حيّةٌ أو مؤرشفةٌ بالرمز نفسه.

    python spawn_preflight.py --tag واجهة --task "فراغ بطاقة الغياب" --code W-007
    python spawn_preflight.py --tag جدول --task "المولّد" --slice "1 من 3" --code G4
    python spawn_preflight.py --title "0405 · إدارة: تنبيه إعادة التوجيه (W-008)"

المخرج JSON؛ رمزُ الخروج 1 إن وُجد مانع (اسمٌ مخالف، وسمٌ غيرُ معروف، 04 ممتلئة).
الذاكرةُ تنبيهٌ لا مانع (D-51م) فلا تغيّر رمزَ الخروج.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

MAESTRO = Path(os.environ.get("MAESTRO_HOME", "C:/Users/mesue/delivery_manager_work"))
sys.path.insert(0, str(MAESTRO / "tools"))
import validate_registry as vr  # noqa: E402 — قواعدُ التسمية من مصدرها لا منسوخة
import watch_once as wo  # noqa: E402 — قياسُ الذاكرة وعتباتُها


RESERVATIONS = MAESTRO / "ledger" / "spawn_reservations.json"
RESERVATION_HOURS = 12


def active_reservations(next_serial: int, path: Path = RESERVATIONS, now: datetime | None = None) -> list[dict]:
    """أرقامٌ حُجزت لبطاقات spawn_task ولم تُفتح بعد؛ تسقط حين يبلغها per_tab_next أو بعد 12 ساعة.

    لماذا: per_tab_next لا يزيد إلّا عند الفتح الفعليّ، فبطاقتان تصدران قبل أن تُفتح أيٌّ منهما تأخذان الرقمَ نفسَه
    (تصادم «0405» مرّتين يوم 09-29 — ولا يمنعه تشغيلُ الفحص قبل كلّ بطاقةٍ وحدَه).
    """
    now = now or datetime.now()
    if not path.is_file():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [r for r in rows
            if r["number"] >= next_serial and (now - datetime.fromisoformat(r["ts"])).total_seconds() < RESERVATION_HOURS * 3600]


def reserve(number: int, title: str, path: Path = RESERVATIONS, now: datetime | None = None) -> None:
    now = now or datetime.now()
    rows = active_reservations(0, path, now)
    rows.append({"number": number, "title": title, "ts": now.isoformat(timespec="seconds")})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def short_code(code: str) -> str:
    """اختصارٌ من رمز البطاقة الكامل: W-20261001-007 ← W-007؛ ما لا يطابق الصيغةَ يعود كما هو."""
    m = re.fullmatch(r"([A-Z]+)-(\d{8})-(\d+)", code or "")
    return f"{m.group(1)}-{m.group(3)}" if m else (code or "")


def resolve_code(code: str, known_codes: list[str] | None = None) -> tuple[str, list[str]]:
    """الرمزُ الذي يدخل العنوان + تحذيرات: الاختصارُ الفريد، فإن صادم رمزاً آخر بالرقم نفسه فصيغةٌ أطول (W-1001-007) ثمّ الكاملة."""
    short = short_code(code)
    if short == code:
        return code, []
    clash = sorted({k for k in (known_codes or []) if k != code and short_code(k) == short})
    if not clash:
        return short, []
    mid_of = lambda c: re.sub(r"^([A-Z]+)-\d{4}(\d{4})-(\d+)$", r"\1-\2-\3", c)  # noqa: E731
    mid = mid_of(code)
    if mid != code and all(mid_of(k) != mid for k in clash):
        return mid, [f"الاختصار {short} يصادم {clash} — استُعملت الصيغةُ الأطول {mid}"]
    return code, [f"الاختصار {short} والصيغةُ المتوسطة تصادمان {clash} — استُعمل الرمزُ الكامل"]


def build_title(serial: int, tag: str, task: str, code: str, slice_: str = "") -> str:
    body = f"{task} {slice_}".strip()
    return f"04{serial:02d} · {tag}: {body} ({code})"


def preflight(title: str | None, tag: str | None, task: str | None, code: str | None,
              slice_: str, tabs: dict, th: dict, free_gb: float | None,
              reserved: dict[int, str] | None = None, known_codes: list[str] | None = None) -> dict:
    policy = tabs["session_policy"]
    serial = policy["serial"]
    reserved = reserved or {}
    nxt = max([serial["per_tab_next"]["04"]] + [n + 1 for n in reserved])
    tab04 = next(t for t in tabs["tabs"] if t.get("number") == "04")
    tags = [s["name_tag"] for s in tabs["specialties"]]
    blockers, warnings = [], []
    if code and title is None:
        code, clash_notes = resolve_code(code, known_codes)
        warnings += clash_notes
    if title is None:
        if tag not in tags:
            blockers.append(f"وسمٌ غيرُ معروف «{tag}» — المسموح: {'، '.join(tags)} (specialties[].name_tag)")
        title = build_title(nxt, tag or "?", task or "", code or "", slice_)
    else:
        head = title.partition(" · ")[0]
        mine = head.isdigit() and len(head) == 4 and reserved.get(int(head[2:])) == title  # حجزُ هذه البطاقة نفسِها
        if head.isdigit() and len(head) == 4 and head[:2] == "04" and int(head[2:]) < nxt and not mine:
            blockers.append(f"الرقمُ {head} أُعطي من قبل أو محجوزٌ لبطاقةٍ أخرى ولا يُعاد (serial.note) — التالي 04{nxt:02d}")
        elif not mine and not title.startswith(f"04{nxt:02d} · "):
            warnings.append(f"الرقمُ في العنوان ليس التاليَ في per_tab_next['04'] ({nxt:02d})")
        if code is None and title.endswith(")") and "(" in title:  # الرمزُ بين القوسين الأخيرين
            code = title.rsplit("(", 1)[1].rstrip(")").split("/")[0]
    # طولُ الاسم تنبيهٌ لا مانع: المالكُ يقرّر الاختصار، والأسماءُ بأرقام البطاقات الطويلة تتجاوز الحدّ
    limit = serial.get("max_title_len", 40)
    problems = vr.name_problems(title, "04", {**serial, "max_title_len": 10**6})
    blockers += problems
    if len(title) > limit:
        warnings.append(f"الاسمُ {len(title)} حرفاً (> {limit}) — تنبيهٌ لا مانع؛ اختصر المهمّةَ إن أمكن")
    if len(tab04["members"]) >= tab04["live_cap"]:
        blockers.append(f"04 ممتلئة: {len(tab04['members'])}/{tab04['live_cap']} (D-51م) — أرشِف منتهيةً أو انتظر")
    if code:
        live_same = [m for m in tab04["members"] if f"({code}" in m or f"/{code}" in m]
        if live_same:
            warnings.append(f"جلسةٌ حيّةٌ بالرمز نفسه: {live_same} — وجِّه إليها بدل الاستحداث")
        archived = [t for e in tabs.get("archived_log", []) for t in ([e["title"]] if "title" in e else e.get("titles", [])) if code in t]
        if archived:
            warnings.append(f"جلسةٌ مؤرشفةٌ بالرمز نفسه: {archived} — أعِد فتحَها (unarchive_session) قبل الإنشاء")
    memory = None
    if free_gb is not None:
        band = wo.memory_band(free_gb, th["memory_free_gb"])
        memory = {"free_gb": free_gb, "band": band}
        if band in ("red", "critical"):
            warnings.append(f"الذاكرة {free_gb} غيغا ({band}): تنبيهٌ لا مانع (D-51م) — أبلغ المالكَ بالرقم وافتح جلسةً واحدةً ثمّ انتظر")
    return {"title": title, "length": len(title), "max_len": serial.get("max_title_len", 40),
            "next_serial_04": f"04{nxt:02d}", "live_04": len(tab04["members"]), "live_cap_04": tab04["live_cap"],
            "memory": memory, "blockers": blockers, "warnings": warnings, "ok": not blockers}


def ledger_codes() -> list[str]:
    """رموزُ بطاقات الدفتر كلُّها — لفحص تصادم الاختصار؛ يفشل بصمتٍ إلى قائمةٍ فارغة."""
    try:
        import ledger
        return sorted(ledger.reduce_state(ledger.load_events()))
    except Exception:  # noqa: BLE001 — الفحصُ مساعدٌ لا مانع
        return []


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--title")
    ap.add_argument("--tag"); ap.add_argument("--task"); ap.add_argument("--code")
    ap.add_argument("--slice", default="", help="للمهمّة الضخمة: «1 من 3»")
    ap.add_argument("--reserve", action="store_true",
                    help="احجز رقمَ العنوان المبنيّ لهذه البطاقة (عند إصدار spawn_task فقط) فلا تأخذه بطاقةٌ أخرى قبل الفتح")
    args = ap.parse_args()
    if not args.title and not (args.tag and args.task and args.code):
        sys.exit("أعطِ --title أو (--tag و--task و--code)")
    base = MAESTRO / "projects" / "schoolos"
    tabs = json.loads((base / "tabs.json").read_text(encoding="utf-8"))
    th = json.loads((base / "thresholds.json").read_text(encoding="utf-8"))
    per_tab = tabs["session_policy"]["serial"]["per_tab_next"]["04"]
    reserved = {r["number"]: r["title"] for r in active_reservations(per_tab)}
    result = preflight(args.title, args.tag, args.task, args.code, args.slice, tabs, th, wo.free_memory_gb(), reserved,
                       ledger_codes())
    if args.reserve and result["ok"] and not args.title:
        reserve(int(result["next_serial_04"][2:]), result["title"])
        result["reserved"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
