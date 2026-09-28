#!/usr/bin/env python3
"""فحصُ ما قبل الاستحداث — قراءةٌ فقط، لا يكتب شيئاً ولا يفتح جلسة.

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
import sys
from pathlib import Path

MAESTRO = Path(os.environ.get("MAESTRO_HOME", "C:/Users/mesue/delivery_manager_work"))
sys.path.insert(0, str(MAESTRO / "tools"))
import validate_registry as vr  # noqa: E402 — قواعدُ التسمية من مصدرها لا منسوخة
import watch_once as wo  # noqa: E402 — قياسُ الذاكرة وعتباتُها


def build_title(serial: int, tag: str, task: str, code: str, slice_: str = "") -> str:
    body = f"{task} {slice_}".strip()
    return f"04{serial:02d} · {tag}: {body} ({code})"


def preflight(title: str | None, tag: str | None, task: str | None, code: str | None,
              slice_: str, tabs: dict, th: dict, free_gb: float | None) -> dict:
    policy = tabs["session_policy"]
    serial = policy["serial"]
    nxt = serial["per_tab_next"]["04"]
    tab04 = next(t for t in tabs["tabs"] if t.get("number") == "04")
    tags = [s["name_tag"] for s in tabs["specialties"]]
    blockers, warnings = [], []
    if title is None:
        if tag not in tags:
            blockers.append(f"وسمٌ غيرُ معروف «{tag}» — المسموح: {'، '.join(tags)} (specialties[].name_tag)")
        title = build_title(nxt, tag or "?", task or "", code or "", slice_)
    else:
        head = title.partition(" · ")[0]
        if head.isdigit() and len(head) == 4 and head[:2] == "04" and int(head[2:]) < nxt:
            blockers.append(f"الرقمُ {head} أُعطي من قبل ولا يُعاد (serial.note) — التالي 04{nxt:02d}")
        elif not title.startswith(f"04{nxt:02d} · "):
            warnings.append(f"الرقمُ في العنوان ليس التاليَ في per_tab_next['04'] ({nxt:02d})")
        if code is None and title.endswith(")") and "(" in title:  # الرمزُ بين القوسين الأخيرين
            code = title.rsplit("(", 1)[1].rstrip(")").split("/")[0]
    blockers += vr.name_problems(title, "04", serial)
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


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--title")
    ap.add_argument("--tag"); ap.add_argument("--task"); ap.add_argument("--code")
    ap.add_argument("--slice", default="", help="للمهمّة الضخمة: «1 من 3»")
    args = ap.parse_args()
    if not args.title and not (args.tag and args.task and args.code):
        sys.exit("أعطِ --title أو (--tag و--task و--code)")
    base = MAESTRO / "projects" / "schoolos"
    tabs = json.loads((base / "tabs.json").read_text(encoding="utf-8"))
    th = json.loads((base / "thresholds.json").read_text(encoding="utf-8"))
    result = preflight(args.title, args.tag, args.task, args.code, args.slice, tabs, th, wo.free_memory_gb())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
