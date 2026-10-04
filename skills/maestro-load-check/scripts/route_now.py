#!/usr/bin/env python3
"""التوجيهُ على النموذج الحاليّ (D-43م..D-55م) — قراءةٌ فقط.

routing.py يطابق نوعَ المشكلة بأسماء مقاعدَ قديمة (أُرشف أكثرُها في D-43م)، فيُرجع
«wake_or_spawn» لكلّ نوعٍ تنفيذيّ حتى لو كانت في 04 جلسةٌ حيّةٌ بالوسم نفسه.
هذا السكربت يعيد القراءةَ نفسها على الواقع الحاليّ:
  نوعُ المشكلة ← اختصاصٌ (specialties) ← وسمُه ← جلساتُ 04 الحيّة بهذا الوسم وأحمالُها،
  أو جلسةُ النواة المالكة للنوع، أو «اسأل» حيث لم يُحسم المالك.

    python route_now.py ui --live
    python route_now.py --paths templates/x.html --load-json load.json
    python route_now.py schedule --load-json load.json --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

MAESTRO = Path(os.environ.get("MAESTRO_HOME", "C:/Users/mesue/delivery_manager_work"))
sys.path.insert(0, str(MAESTRO / "tools"))
import routing  # noqa: E402 — نعيد استعمالَ guess_type وlive_rows ولا ننسخهما
import topic_match as tm  # noqa: E402

# نوعُ المشكلة ← جلسةُ النواة التي تملكه (من مواثيق session_policy.charters في tabs.json).
# git وinfra_preview لا مالكَ لهما بعد أرشفة مقعدَيهما في D-43م ← يُسأل المايسترو/المالك.
CORE_OWNER = {
    "release": "0601 · الإصدار: الدمجُ والنشر",
    "roadmap": "0701 · الجودة: الرصدُ والخارطةُ والأتمتة",
    "governance": "0103 · الحوكمة: حراسةُ القواعد",
    "intake": "0201 · البوابة: البلاغاتُ والطابور",
    "regulations": "0301 · المستشار: التصنيف والتسمية",
    "orchestration": "0101 · المايسترو",
}
UNRESOLVED = ("git", "infra_preview")


def load_tabs() -> dict:
    return json.loads((MAESTRO / "projects" / "schoolos" / "tabs.json").read_text(encoding="utf-8"))


def merge_rows(rows: list[dict]) -> dict[str, dict]:
    """شجرتان قد تحملان الاسمَ نفسه في session_names.json؛ نجمعهما بتحفّظ (الأسوأُ حِملاً)."""
    out: dict[str, dict] = {}
    for r in rows:
        cur = out.get(r["session"])
        if cur is None:
            out[r["session"]] = {k: r[k] for k in ("session", "open_prs", "context_mb", "overloaded", "assignable")} | {"trees": [r["tree"]]}
            continue
        cur["open_prs"] += r["open_prs"]
        cur["context_mb"] = max(cur["context_mb"], r["context_mb"])
        cur["overloaded"] = cur["overloaded"] or r["overloaded"]
        cur["assignable"] = cur["assignable"] and r["assignable"]
        cur["trees"].append(r["tree"])
    return out


def decide(ptype: str, paths: list[str], rows: list[dict], tabs: dict, rt: dict, task: str | None = None) -> dict:
    spec = rt["problem_types"].get(ptype)
    if spec is None:
        return {"decision": "unknown_type", "type": ptype, "known": sorted(rt["problem_types"]),
                "notes": ["نوعُ البطاقة ليس مفتاحاً في routing.json — صحّح --type في السجلّ أو مرِّر --paths"]}
    tab04 = next(t for t in tabs["tabs"] if t.get("number") == "04")
    serial = tabs["session_policy"]["serial"]["per_tab_next"]["04"]
    base = {"type": ptype, "live_04": len(tab04["members"]), "live_cap_04": tab04["live_cap"],
            "next_04": f"04{serial:02d}", "notes": []}
    if ptype in CORE_OWNER:
        return {**base, "decision": "core_owner", "session": CORE_OWNER[ptype],
                "notes": ["عملُ نواةٍ ثابتة: وجِّه إليها ولا تستحدث"]}
    if ptype in UNRESOLVED:
        return {**base, "decision": "ask", "notes": [f"مقعدُ «{spec['executors'][0]}» مؤرشفٌ ولا مالكَ محسوماً لهذا النوع — اعرضه على المايسترو/المالك"]}
    tab_id = spec["tab"]
    if spec["executors"] == ["file_owner"]:
        # الاختبارُ والوثيقةُ والدَّين يتبعان صاحبَ الملفّات: نخمّن اختصاصَها من المسارات
        others = {"problem_types": {k: v for k, v in rt["problem_types"].items() if v["executors"] != ["file_owner"]}}
        guessed = routing.guess_type(paths, others) if paths else None
        tab_id = rt["problem_types"][guessed]["tab"] if guessed else None
        base["notes"].append("صاحبُ الملفّات أوّلاً: جلسةُ 04 التي يلمس عملُها هذه الملفّات")
    tags = {s["id"]: s["name_tag"] for s in tabs["specialties"]}
    tag = tags.get(tab_id)
    if tag is None:
        return {**base, "decision": "ask", "notes": base["notes"] + ["تعذّر تحديدُ الاختصاص — مرِّر --paths أو حدّده من الملفّات المظنونة"]}
    merged = merge_rows(rows)
    cands = [v for k, v in merged.items() if k[:2] == "04" and k.partition(" · ")[2].startswith(tag + ":")]
    free = [c for c in cands if c["assignable"]]
    skipped = [c["session"] for c in free if tm.excluded_by_topic(c, task)]
    free = [c for c in free if c["session"] not in skipped]  # مشغولةٌ بموضوعٍ مختلف لا تُقترح
    decision = "assign_candidate" if free else "spawn"
    why = ("جلسةٌ حيّةٌ بالوسم نفسه غيرُ مثقلة — وجِّه إليها إن كانت المهمّةُ من عائلة مهمّتها، وإلّا فاستحدث"
           if free else ("كلُّ جلسات الوسم مثقلة" if cands else "لا جلسةَ حيّةً بهذا الوسم في 04"))
    if decision == "spawn" and base["live_04"] >= base["live_cap_04"]:
        decision, why = "queue", f"04 ممتلئة ({base['live_04']}/{base['live_cap_04']}): تنتظر البطاقةُ في الطابور أو يقرّر المالك"
    return {**base, "decision": decision, "tag": tag, "specialty": tab_id,
            "candidates": sorted(cands, key=lambda c: (c["overloaded"], c["open_prs"], c["context_mb"])),
            "notes": base["notes"] + [why] + ([f"استُبعدت لانشغالها بموضوعٍ مختلف: {'، '.join(skipped)}"] if skipped else [])}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("type", nargs="?")
    ap.add_argument("--paths", nargs="*", default=[])
    ap.add_argument("--load-json")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--task", help="عنوانُ المهمّة المطلوبة؛ تُستبعد الجلساتُ المشغولةُ بموضوعٍ مختلف")
    args = ap.parse_args()
    rt, tabs = routing.load_routing(), load_tabs()
    ptype = args.type or routing.guess_type(args.paths, rt)
    if not ptype:
        print(json.dumps({"decision": "unknown_type", "notes": ["لا مسارَ يطابق path_globs — مرِّر النوعَ صراحةً"]}, ensure_ascii=False, indent=2))
        sys.exit(1)
    if args.load_json:
        rows = json.loads(Path(args.load_json).read_text(encoding="utf-8"))["sessions"]
    elif args.live:
        rows = routing.live_rows()
    else:
        sys.exit("حدّد --live أو --load-json")
    print(json.dumps(decide(ptype, args.paths, rows, tabs, rt, args.task), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
