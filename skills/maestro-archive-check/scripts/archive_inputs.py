#!/usr/bin/env python3
"""مُدخلاتُ فاحص الأرشفة من قائمة الجلسات — قراءةٌ فقط، لا يكتب شيئاً.

لماذا: `tools/archive_check.py` يثق بـ--running و--shared كما يُعطَيان (الافتراضيّ «لا تعمل» و0)،
ويحكم على المذكّرة بوجود ملفٍّ باسم الشجرة لا باسم الجلسة. فمن نسي --shared أُرشفت معه جلسةٌ
تشاركه الشجرة، ومن ورث شجرةً أُعيد استعمالُها رأى «مذكّرةً محفوظة» كتبتها جلسةٌ سابقة.

    python archive_inputs.py --sessions sessions.json --title "04SS · <اسم الجلسة>"

sessions.json: مخرجُ list_sessions (مصفوفةُ JSON بحقول title وcwd وisRunning وisArchived وpinned) محفوظاً في ملفّ.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MAESTRO = Path("C:/Users/mesue/delivery_manager_work")


def tree_of(cwd: str) -> str:
    """اسمُ مجلّد الشجرة من cwd (ويندوز أو POSIX)."""
    return cwd.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def inspect(sessions: list[dict], title: str, core: set[str], notes_dir: Path) -> dict:
    live = [s for s in sessions if not s.get("isArchived")]
    target = next((s for s in live if s.get("title") == title), None)
    if target is None:
        return {"error": f"لا جلسةَ حيّةً بالعنوان «{title}» — انسخه حرفيّاً من list_sessions"}
    tree = tree_of(target.get("cwd", ""))
    # الجلساتُ الأخرى التي cwd لها الشجرةُ نفسُها: التطبيقُ يؤرشفها مع الهدف
    mates = [s for s in live if s is not target and tree_of(s.get("cwd", "")) == tree]
    note = notes_dir / f"{tree}.md"
    note_text = note.read_text(encoding="utf-8") if note.is_file() else ""
    return {
        "title": title,
        "tree": tree,
        "is_core": title in core,
        "running": bool(target.get("isRunning")),
        "pinned": bool(target.get("pinned")),
        "shared_with": [s.get("title") for s in mates],
        "shared_running": [s.get("title") for s in mates if s.get("isRunning")],
        # المذكّرةُ تُقبل إن ذكرت عنوانَ هذه الجلسة؛ وإلّا فهي لجلسةٍ سابقةٍ في الشجرة نفسِها
        "note_exists": note.is_file(),
        "note_names_this_session": bool(note_text) and title in note_text,
    }


def command(facts: dict) -> str:
    # المسارُ بشرطاتٍ أماميّةٍ بلا اقتباس ليطابق نمطَ allowed-tools؛ والعنوانُ بين علامتَي تنصيص
    title = facts["title"].replace('"', '\\"')
    cmd = f'python {(MAESTRO / "tools" / "archive_check.py").as_posix()} {facts["tree"]} --title "{title}"'
    if facts["running"]:
        cmd += " --running"
    return cmd + f" --shared {len(facts['shared_with'])}"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # طرفيّةُ ويندوز cp1256 تُسقط العربيّة
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sessions", required=True, help="ملفُّ JSON من list_sessions")
    ap.add_argument("--title", required=True, help="عنوانُ الجلسة حرفيّاً")
    ap.add_argument("--project", default="schoolos")
    ap.add_argument("--notes-dir", default=str(MAESTRO / "handover_notes"))
    args = ap.parse_args()
    sessions = json.loads(Path(args.sessions).read_text(encoding="utf-8"))
    tabs = json.loads((MAESTRO / "projects" / args.project / "tabs.json").read_text(encoding="utf-8"))
    core = set(tabs.get("session_policy", {}).get("core_sessions", []))
    facts = inspect(sessions, args.title, core, Path(args.notes_dir))
    if "error" not in facts:
        facts["archive_check_cmd"] = command(facts)
    print(json.dumps(facts, ensure_ascii=False, indent=2))
    sys.exit(1 if "error" in facts else 0)


if __name__ == "__main__":
    main()
