#!/usr/bin/env python3
"""مرشّحو الأرشفة في 04 — قراءةٌ فقط؛ يطبّق archive_check ثمّ يضيف شرطَي 0102: بطاقاتُها نهائيّة وحاويتُها متوقّفةٌ ساعتين فأكثر.

لا يؤرشف شيئاً: يعطي القائمةَ، والأرشفةُ بأداة archive_session بعد تحقّقي أنّ الجلسةَ ليست عاملةً (ListAgents).

    python archive_candidates.py [--min-stopped-h 2]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import archive_check as ac  # noqa: E402
import ledger  # noqa: E402

FINAL_STATES = {"merged", "published", "closed", "deferred"}
UNIT_HOURS = {"second": 1 / 3600, "minute": 1 / 60, "hour": 1, "day": 24, "week": 168}


def stopped_hours(status: str) -> float | None:
    """«Up …» ← None (عاملة)؛ «Exited (0) 3 hours ago» ← 3؛ غيرُ ذلك ← None."""
    m = re.match(r"Exited \(\d+\) (?:About an? |(\d+) )(second|minute|hour|day|week)s? ago", status)
    if not m:
        return None
    return (int(m.group(1)) if m.group(1) else 1) * UNIT_HOURS[m.group(2)]


def containers_of(tree: str, rows: list[tuple[str, str]], min_h: float) -> list[str]:
    """أسبابُ المنع من حاويات الشجرة: أيُّ حاويةٍ غيرِ متوقّفةٍ min_h ساعةً على الأقلّ."""
    blockers = []
    for name, status in rows:
        if not name.startswith(f"schoolos-{tree}-"):
            continue
        h = stopped_hours(status)
        if h is None:
            blockers.append(f"{name}: {status}")
        elif h < min_h:
            blockers.append(f"{name}: توقّفت منذ {h:.1f} س فقط")
    return blockers


def docker_rows() -> list[tuple[str, str]] | None:
    proc = subprocess.run(["docker", "ps", "-a", "--format", "{{.Names}}|{{.Status}}"],
                          capture_output=True, encoding="utf-8", errors="replace", check=False)
    if proc.returncode != 0:
        return None
    return [tuple(line.split("|", 1)) for line in proc.stdout.splitlines() if "|" in line]  # type: ignore[misc]


def cards_of(title: str, items: dict[str, dict]) -> list[dict]:
    """بطاقاتُ الجلسة من رموز عنوانها (W-003/004): كلُّ بطاقةٍ يطابق رقمُها الأخيرُ الرمزَ — قد يلتبس بين يومين فتُعرض كلُّها."""
    tail = title.rsplit("(", 1)[-1].rstrip(")") if "(" in title else ""
    nums = re.findall(r"(?:W-)?(\d{3})", tail)
    return [i for i in items.values() if any(i["id"].endswith(f"-{n}") for n in nums)] if nums else []


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-stopped-h", type=float, default=2.0)
    args = ap.parse_args()
    base = ac.ROOT / "projects" / "schoolos"
    tabs = json.loads((base / "tabs.json").read_text(encoding="utf-8"))
    names = json.loads((base / "session_names.json").read_text(encoding="utf-8"))
    core = ac.permanent_titles(tabs)
    tab04 = next(t for t in tabs["tabs"] if t.get("number") == "04")
    items = ledger.reduce_state(ledger.load_events())
    rows = docker_rows()
    trees_by_title: dict[str, list[str]] = {}
    for tree, title in names.items():
        trees_by_title.setdefault(title, []).append(tree)

    report = []
    for title in tab04["members"]:
        trees = trees_by_title.get(title, [])
        if not trees:
            report.append({"title": title, "eligible": False, "blockers": ["لا شجرةَ مسمّاةً بهذا العنوان في session_names.json"]})
            continue
        blockers: list[str] = []
        for tree in trees:
            verdict = ac.evaluate(ac.gather(tree, title, False, 0), core)
            blockers += [f"{tree}: {b}" for b in verdict["blockers"] if b != "لا تعمل الآن"]
            blockers += [f"{tree}: {b}" for b in (containers_of(tree, rows, args.min_stopped_h) if rows is not None else ["docker غيرُ متاح: تحقّقٌ يدويّ"])]
        cards = cards_of(title, items)
        if not cards:
            blockers.append("لا بطاقةَ في السجلّ لرمز العنوان — تحقّقٌ يدويّ")
        blockers += [f"البطاقة {c['id']} حالتُها {c['state']} (ليست نهائيّة)" for c in cards if c["state"] not in FINAL_STATES]
        report.append({"title": title, "trees": trees, "cards": {c["id"]: c["state"] for c in cards},
                       "eligible": not blockers, "blockers": blockers})
    print(json.dumps({"note": "«تعمل الآن» غيرُ مقيسةٍ هنا — أتحقّق بـListAgents قبل الأرشفة", "sessions": report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
