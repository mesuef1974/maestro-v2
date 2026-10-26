#!/usr/bin/env python3
"""فحصُ المسارات المذكورة في المواثيق (W-20261026-009): كلُّ مسارٍ في role_cards/**.md بين علامتَي ` يجب أن يوجد.

    python charter_paths_check.py            # يطبع المكسورَ ويخرج 1 إن وُجد، وإلا 0
    python charter_paths_check.py --json

يُحَلّ المسارُ نسبةً إلى جذر الأدوات (delivery_manager_work) ثمّ إلى الجذر نفسه مطلقاً. تُتجاهل الروابطُ والأنماطُ (* و<…> و{…})
والمسارات التي تبدأ بـ~ أو مجلّداتٌ بلا امتداد. لا يكتب شيئاً.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "role_cards"
EXT = r"(?:md|py|json|jsonl|html|sh|txt|yml|yaml)"
TICK = re.compile(r"`([^`\n]+)`")
PATH = re.compile(r"^(?:[A-Za-z]:)?[\w./\\-]+\." + EXT + r"$")
SKIP_PARTS = ("http://", "https://", "<", ">", "*", "{", "}", "~")
#: مسارٌ نسبيٌّ يُجرَّب بعد هذه البوادئ (الأدواتُ تُشير إلى tools/ والمذكّرات إلى handover_notes/…)
PREFIXES = ("", "tools/", "docs/", "handover_notes/", "ledger/", "projects/schoolos/", "role_cards/", "role_cards/details/")
#: مجلّداتٌ خارج الجذر تُجرَّب أيضاً (ذاكرة المشروع)
EXTRA_ROOTS = (Path.home() / ".claude" / "projects" / "D--shschool-mvp" / "memory", Path.home() / ".claude" / "projects" / "D--shschool-mvp",
               Path("D:/shschool_mvp"))
_SKIP_DIRS = {".git", "node_modules", ".venv", "worktrees", "__pycache__", "staticfiles"}
_names_cache: dict[Path, set[str]] = {}


def _platform_names(base: Path) -> set[str]:
    """أسماءُ الملفّات تحت مستودع المنصّة (لمسارٍ مذكورٍ باسم الملفّ وحده، مثل ui.py)؛ تُخزَّن لمرّةٍ واحدة."""
    if base not in _names_cache:
        names: set[str] = set()
        if base.exists():
            for dirpath, dirs, files in __import__("os").walk(base):
                dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
                names.update(files)
        _names_cache[base] = names
    return _names_cache[base]


def _candidates(raw: str, root: Path) -> list[Path]:
    text = raw.replace(chr(92), "/")
    if re.match(r"^[A-Za-z]:/", text):
        return [Path(text)]
    return [root / (p + text) for p in PREFIXES] + [r / text for r in EXTRA_ROOTS]


BARE = re.compile(r"(?<![\w/.:-])((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\." + EXT + r")(?![\w/])")


def paths_in(text: str) -> list[str]:
    """المسارات بين علامتَي ` ثمّ المسارات المكتوبة عاريةً وفيها مجلّدٌ واحدٌ على الأقل."""
    out = []
    out.extend(m.group(1) for m in BARE.finditer(TICK.sub(" ", text)) if not any(s in m.group(1) for s in SKIP_PARTS))
    for m in TICK.finditer(text):
        token = m.group(1).strip().split()[0] if m.group(1).strip() else ""
        if not token or any(s in token for s in SKIP_PARTS) or not PATH.match(token):
            continue
        out.append(token.rstrip(".,;:)"))
    return out


def check(cards: Path = CARDS, root: Path = ROOT) -> list[dict]:
    """[{file, path}] لكلّ مسارٍ مذكورٍ لا يوجد في أيّ من المواضع المرشَّحة."""
    broken = []
    for f in sorted(cards.rglob("*.md")):
        seen: set[str] = set()
        for raw in paths_in(f.read_text(encoding="utf-8")):
            if raw in seen:
                continue
            seen.add(raw)
            bare = "/" not in raw.replace(chr(92), "/")
            if not any(c.exists() for c in _candidates(raw, root)) and not (bare and root == ROOT and raw in _platform_names(EXTRA_ROOTS[-1])):
                broken.append({"file": str(f.relative_to(cards)).replace(chr(92), "/"), "path": raw})
    return broken


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:] if argv is None else argv
    broken = check()
    if "--json" in argv:
        print(json.dumps(broken, ensure_ascii=False, indent=1))
    elif broken:
        print(f"مسارات مكسورة في المواثيق ({len(broken)}):")
        for b in broken:
            print(f"  {b['file']}: {b['path']}")
    else:
        print("كلُّ المسارات المذكورة في المواثيق موجودة")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
