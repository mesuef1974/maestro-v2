#!/usr/bin/env python3
"""مكنسةُ الأرشفة (D-75م): تفحص كلَّ جلسةٍ مرنةٍ في 04 بفحوصٍ آليّةٍ كاملةٍ وتُخرج ما يجوز أرشفتُه الآن.

تُؤتمت خطواتُ مهارة maestro-archive-check كلُّها ما عدا فعلَ الأرشفة نفسِه (أداةُ التطبيق `archive_session` لا يبلغها إلّا المايسترو):
الحقائقُ من list_sessions، فاحصُ archive_check، **النشرُ** (هل بلغ الطلبُ المدموجُ الإنتاجَ الحيّ؟)، **الخارطةُ** (هل ذُكر رقمُ الطلب
في هجرة roadmap على main؟)، **مذكّرةُ التسليم** (تُكتب من الحقائق بقالبها المعتمَد إن غابت)، ثمّ **تسجيلُ الأرشفة** في tabs.json.

    python archive_sweep.py --sessions sessions.json [--write-notes] [--json]
    python archive_sweep.py --record-archived "<عنوان>" ["<عنوان>" ...]   # بعد أن تؤرشف الجلساتِ في التطبيق

لا تؤرشف الأداةُ ولا تُغيّر شيئاً بلا `--write-notes` أو `--record-archived`. النواةُ لا تدخل الفحص أصلاً (D-43م).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "skills" / "maestro-archive-check" / "scripts"))
import archive_check as ac  # noqa: E402
import archive_inputs as ai  # noqa: E402
import branch_status as bs  # noqa: E402

REPO = Path("D:/shschool_mvp")
HEALTH_URL = "https://shschoolmvp-production.up.railway.app/health/"
MERGED_STATES = {bs.MERGED, bs.MERGED_ELSEWHERE}
FLEX_TITLE = re.compile(r"^04\d\d · ")
NOTE_LINES = ("لا مذكّرةَ تسليمٍ محفوظة",)


def is_candidate(session: dict, core: set[str]) -> bool:
    title = session.get("title", "")
    return not session.get("isArchived") and bool(FLEX_TITLE.match(title)) and title not in core


def _run(cmd: list[str], cwd: Path = REPO) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout.strip()


def production_commit() -> str | None:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=10) as r:  # قراءةٌ فقط، وهو ما يقرؤه verify_deploy
            return json.loads(r.read().decode("utf-8")).get("commit")
    except Exception:
        return None


def pr_merge_oid(number: int) -> str | None:
    code, out = _run(["gh", "pr", "view", str(number), "--json", "mergeCommit", "--jq", ".mergeCommit.oid // empty"])
    return out or None if code == 0 else None


def is_ancestor(oid: str, commit: str) -> bool:
    return _run(["git", "merge-base", "--is-ancestor", oid, commit])[0] == 0


def roadmap_mentions(numbers: list[int]) -> set[int]:
    """أرقامُ الطلبات المذكورة في هجرات roadmap على origin/main (بصيغة #N)."""
    found: set[int] = set()
    for n in numbers:
        code, _ = _run(["git", "grep", "-q", "-E", f"#{n}([^0-9]|$)", "origin/main", "--", "roadmap/migrations"])
        if code == 0:
            found.add(n)
    return found


def extra_blockers(merged_prs: list[int], live_commit: str | None, oid_of, ancestor, mentioned: set[int]) -> tuple[list[str], list[str]]:
    """(موانع، ملاحظات): النشرُ والخارطةُ للطلبات المدموجة. تعذّرُ معرفة الإنتاج مانعٌ (الأحوط)."""
    blockers, notes = [], []
    if not merged_prs:
        return blockers, ["لا طلبَ مدموجاً على فرعها — لا فحصَ نشرٍ ولا خارطة"]
    undeployed, unknown = [], []
    for n in merged_prs:
        oid = oid_of(n)
        if live_commit is None or oid is None:
            unknown.append(n)
        elif not ancestor(oid, live_commit):
            undeployed.append(n)
    if unknown:
        blockers.append("تعذّر التحقّق من نشر " + ", ".join(f"#{n}" for n in unknown) + " (الإنتاج أو gh)")
    if undeployed:
        blockers.append("طلبٌ مدموجٌ لم يبلغ الإنتاجَ الحيّ: " + ", ".join(f"#{n}" for n in undeployed))
    missing = [n for n in merged_prs if n not in mentioned]
    if missing:
        blockers.append("الخارطةُ لم تذكر: " + ", ".join(f"#{n}" for n in missing) + " (تنتظر 0701)")
    if not blockers:
        notes.append("منشورةٌ في الإنتاج الحيّ ومذكورةٌ في الخارطة: " + ", ".join(f"#{n}" for n in merged_prs))
    return blockers, notes


def note_section(title: str, tree: str, branch: str | None, facts: dict, notes: list[str], now: datetime) -> str:
    prs = ", ".join(f"#{n}" for n in facts.get("branch_prs", [])) or "لا طلب"
    label = bs.LABEL_AR.get(facts.get("branch_status"), "غيرُ معروفة")
    return "\n".join([
        f"# مذكّرةُ تسليم — «{title}»",
        "",
        f"- التاريخ: {now:%Y-%m-%d %H:%M} (الدوحة، من الأداة)، كتبتها «مكنسةُ الأرشفة (archive_sweep.py)» بتفويض المايسترو الدائم D-62م.",
        f"- الشجرة: `{tree}`؛ الفرع: `{branch or 'غيرُ معروف'}`؛ حالةُ الفرع: {label} ({prs}).",
        f"- طلباتٌ مفتوحة: {len(facts.get('open_prs', []))}؛ ملفّاتٌ غيرُ مودَعة: {facts.get('dirty_files', 0)}؛ إيداعاتُ git cherry الظاهرة: {facts.get('cherry_plus', 0)} (أثرُ سحقٍ إن كان الطلبُ مدموجاً).",
        "- النشرُ والخارطة: " + ("؛ ".join(notes) or "غيرُ منطبقين"),
        "- ما بقي مفتوحاً: لا شيء عند وقت الفحص.",
        "- المعرفة: لا ينطبق.",
        "- العودة: unarchive_session للجلسة نفسِها، أو جلسةٌ مرنةٌ جديدةٌ برقمٍ جديد في 04 للمهمّة نفسِها.",
        "",
    ])


def write_note(path: Path, title: str, section: str) -> str:
    """مذكّرةٌ جديدة، أو قسمٌ في أعلى مذكّرة شجرةٍ أُعيد استعمالُها (لا تُمحى القديمة)."""
    if not path.is_file():
        path.write_text(section, encoding="utf-8", newline="\n")
        return "كُتبت"
    old = path.read_text(encoding="utf-8")
    if title in old:
        return "موجودة"
    path.write_text(section + "\n---\n\n" + old, encoding="utf-8", newline="\n")
    return "أُلحقت"


def evaluate_session(session: dict, live: list[dict], tabs: dict, core: set[str], write_notes: bool,
                     live_commit: str | None, now: datetime) -> dict:
    title = session["title"]
    inp = ai.inspect(live, title, core, ROOT / "handover_notes")
    if "error" in inp:
        return {"title": title, "ready": False, "blockers": [inp["error"]], "notes": []}
    tree = inp["tree"]
    try:
        facts = ac.gather(tree, title, inp["running"], len(inp["shared_with"]), REPO)
    except SystemExit as e:
        return {"title": title, "ready": False, "blockers": [str(e)], "notes": []}
    verdict = ac.evaluate(facts, ac.permanent_titles(tabs))
    blockers = [b for b in verdict["blockers"] if b not in NOTE_LINES]
    merged = facts.get("branch_prs", []) if facts.get("branch_status") in MERGED_STATES else []
    more, notes = extra_blockers(merged, live_commit, pr_merge_oid, is_ancestor, roadmap_mentions(merged) if merged else set())
    blockers += more
    note_path = ROOT / "handover_notes" / f"{tree}.md"
    note_state = "موجودة" if inp["note_names_this_session"] else "غائبة"
    if note_state == "غائبة":
        if write_notes and not blockers:  # لا تُكتب مذكّرةٌ لجلسةٍ لن تُؤرشف
            note_state = write_note(note_path, title, note_section(title, tree, session.get("branch"), facts, notes, now))
        else:
            blockers.append("مذكّرةُ التسليم غائبةٌ أو لا تذكر هذه الجلسة" + ("" if write_notes else " (تُكتب بـ--write-notes)"))
    return {"title": title, "sessionId": session.get("sessionId"), "tree": tree, "ready": not blockers,
            "blockers": blockers, "notes": notes, "note": note_state}


def record_archived(titles: list[str], tabs_path: Path, now: datetime, decision: str = "D-62م") -> list[str]:
    tabs = json.loads(tabs_path.read_text(encoding="utf-8"))
    done = []
    for title in titles:
        for tab in tabs["tabs"]:
            if title in tab.get("members", []):
                tab["members"].remove(title)
                tabs.setdefault("archived_log", []).append({
                    "title": title, "at": f"{now:%Y-%m-%d}", "decision": decision,
                    "note": "أُرشفت بمكنسة الأرشفة (archive_sweep.py) بعد فحوصٍ آليّةٍ كاملة؛ مذكّرتُها في handover_notes/؛ العودةُ بـunarchive_session"})
                done.append(title)
                break
    tabs_path.write_text(json.dumps(tabs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return done


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sessions", help="مخرجُ list_sessions محفوظاً JSON")
    ap.add_argument("--write-notes", action="store_true", help="اكتب مذكّرةَ التسليم من الحقائق للجلسات الجاهزة")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--record-archived", nargs="+", metavar="TITLE", help="سجّلْ جلساتٍ أُرشفت للتوّ في tabs.json")
    ap.add_argument("--project", default="schoolos")
    args = ap.parse_args()
    tabs_path = ROOT / "projects" / args.project / "tabs.json"
    now = datetime.now(timezone(timedelta(hours=3)))
    if args.record_archived:
        done = record_archived(args.record_archived, tabs_path, now)
        print("سُجّلت في archived_log:", "؛ ".join(done) or "لا شيء (عناوينُ غيرُ موجودةٍ في members)")
        return 0
    if not args.sessions:
        sys.exit("أعطِ --sessions أو --record-archived")
    tabs = json.loads(tabs_path.read_text(encoding="utf-8"))
    core = set(tabs.get("session_policy", {}).get("core_sessions", []))
    sessions = json.loads(Path(args.sessions).read_text(encoding="utf-8"))
    live = [s for s in sessions if not s.get("isArchived")]
    commit = production_commit()
    results = [evaluate_session(s, live, tabs, core, args.write_notes, commit, now) for s in live if is_candidate(s, core)]
    if args.json:
        print(json.dumps({"production_commit": commit, "results": results}, ensure_ascii=False, indent=2))
        return 0
    ready = [r for r in results if r["ready"]]
    print(f"مكنسةُ الأرشفة — {now:%Y-%m-%d %H:%M} — الإنتاجُ الحيّ: {commit or 'غيرُ معروف'} — مرشَّحات: {len(results)}")
    print(f"\nجاهزةٌ للأرشفة الآن ({len(ready)}):")
    for r in ready:
        print(f"  ✔ {r['title']} — sessionId={r.get('sessionId')} — المذكّرة: {r['note']}")
    print(f"\nغيرُ جاهزة ({len(results) - len(ready)}):")
    for r in results:
        if not r["ready"]:
            print(f"  ✘ {r['title']} ← " + " · ".join(r["blockers"]))
    if ready:
        print("\nالخطوةُ التالية: `archive_session` لكلٍّ من الجاهزات (تفويضُ D-62م)، ثمّ:\n  python tools/archive_sweep.py --record-archived " + " ".join(f'"{r["title"]}"' for r in ready))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
