#!/usr/bin/env python3
"""التوجيهُ كبياناتٍ: نوعُ المشكلة ← المقعدُ المنفِّذ الأخفُّ حِملاً في تبويب الاختصاص، وإلا طلبُ استحداثٍ داخل التبويب.

    python routing.py ui --live
    python routing.py schedule --load-json load.json
    python routing.py --paths templates/x.html static/css/custom/20-components.css --live

القرارُ يبقى «اقتراحاً» في المخرجات؛ الإنشاءُ والأرشفةُ والنقلُ بموافقة المالك في التطبيق.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECTS = HERE.parent / "projects"


def load_routing(project: str = "schoolos") -> dict:
    return json.loads((PROJECTS / project / "routing.json").read_text(encoding="utf-8"))


def guess_type(paths: list[str], routing: dict) -> str | None:
    """أكثرُ الأنواع مطابقةً لمسارات الملفّات (glob)؛ None إن لم يطابق شيء."""
    votes: Counter[str] = Counter()
    for ptype, spec in routing["problem_types"].items():
        for path in paths:
            p = path.replace("\\", "/")
            if any(fnmatch.fnmatch(p, g) for g in spec.get("path_globs", [])):
                votes[ptype] += 1
    return votes.most_common(1)[0][0] if votes else None


def route(problem_type: str, rows: list[dict], routing: dict, wip_limit: int | None = None) -> dict:
    spec = routing["problem_types"].get(problem_type)
    if spec is None:
        return {"decision": "unknown_type", "reasons": [f"نوعٌ غيرُ معروف: {problem_type}"], "known": sorted(routing["problem_types"])}
    limit = wip_limit or routing.get("default_wip_limit", 3)
    by_name = {r["session"]: r for r in rows}
    out = {"type": problem_type, "tab": spec["tab"], "owners": spec["owners"], "reasons": []}
    if spec["executors"] == ["file_owner"]:
        return {**out, "decision": "file_owner", "seat": None,
                "reasons": ["المقعدُ المنفِّذ هو صاحبُ الملفّ (يُحدَّد بمسارات الملفّات المتأثرة)؛ المالكُ الوصيُّ: " + "، ".join(spec["owners"])]}
    present = [e for e in spec["executors"] if e in by_name]
    free = [e for e in present if by_name[e]["open_prs"] < limit and not by_name[e]["overloaded"]]
    if free:
        best = min(free, key=lambda e: (by_name[e]["open_prs"], by_name[e]["unmerged_commits"]))
        return {**out, "decision": "assign", "seat": best,
                "reasons": [f"{best}: {by_name[best]['open_prs']} طلبات مفتوحة (الحدّ {limit})، ليست مثقلة"]}
    if present:
        busy = ", ".join(f"{e} ({by_name[e]['open_prs']} طلبات، {by_name[e]['context_mb']}MB)" for e in present)
        return {**out, "decision": "request_spawn", "seat": None,
                "reasons": [f"كلُّ مقاعد الاختصاص مثقلة: {busy}", "اقترح على المالك جلسةً مؤقّتةً داخل التبويب بعد فحص الذاكرة (watch_once)، أو أجّل"]}
    return {**out, "decision": "wake_or_spawn", "seat": None,
            "reasons": ["لا جلسةَ ظاهرةً لهذا الاختصاص في قياس الحِمل: أعِد فتحَ المقعد (unarchive) أو اقترح جلسةً جديدة"]}


def live_rows() -> list[dict]:
    proc = subprocess.run([sys.executable, str(HERE / "session_load_v2.py"), "--json", "--no-fetch"],
                          capture_output=True, encoding="utf-8", errors="replace", check=False)
    if proc.returncode != 0:
        sys.exit(f"session_load_v2 فشل: {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout)["sessions"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("type", nargs="?")
    ap.add_argument("--paths", nargs="*", default=[])
    ap.add_argument("--load-json"); ap.add_argument("--live", action="store_true")
    ap.add_argument("--project", default="schoolos")
    args = ap.parse_args()
    routing = load_routing(args.project)
    ptype = args.type or guess_type(args.paths, routing)
    if not ptype:
        sys.exit("تعذّر تحديدُ النوع: مرِّره صراحةً أو أعطِ --paths تطابق path_globs")
    if args.load_json:
        rows = json.loads(Path(args.load_json).read_text(encoding="utf-8"))["sessions"]
    elif args.live:
        rows = live_rows()
    else:
        sys.exit("حدّد --live أو --load-json")
    print(json.dumps(route(ptype, rows, routing), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
