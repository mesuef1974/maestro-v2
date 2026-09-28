#!/usr/bin/env python3
"""يولّد docs/tab_charters.md من projects/<project>/tabs.json (مصدرٌ واحد؛ لا يُحرَّر الناتجُ يدويّاً)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def render(tabs: dict) -> str:
    out = ["# مواثيقُ التبويبات — مولَّدةٌ من tabs.json (لا تُحرَّر يدويّاً)", f"> {tabs['principle']}", f"> نقطتا لمس المالك: {' و'.join(tabs['owner_touchpoints'])}.", ""]
    for tab in sorted(tabs["tabs"], key=lambda t: t["order"]):
        out += [
            f"## {tab.get('number', tab['order'])} · {tabs['group_prefix']}{tab['name']}" + (" (انتقاليّ)" if tab.get("transitional") else ""),
            f"**الطبقة:** {tab['layer']} · **دورة الحياة:** {tab['lifecycle']} · **حدّ الجلسات:** {tab['live_cap']}",
            f"**الغرض:** {tab['purpose']}",
            "**الأهداف:** " + "؛ ".join(tab["goals"]),
            "**المؤشّرات:** " + "؛ ".join(tab["kpis"]),
            "**المداخل:** " + "؛ ".join(tab["inputs"]),
            "**المخارج:** " + "؛ ".join(tab["outputs"]),
            "**المهارات:** " + "، ".join(f"`{s}`" for s in tab["skills"]),
            f"**الصلاحيّات:** {tab['permissions']}",
            *([f"**شرطُ الإخلاء:** {tab['exit_rule']}"] if tab.get("exit_rule") else []),
            "**الأعضاء:** " + "؛ ".join(tab["members"]),
            "",
        ]
    if tabs.get("pending_archive"):
        out += ["## قيد الأرشفة", *(f"- {p['title']}: {p['reason']}" for p in tabs["pending_archive"]), ""]
    out += ["## مشاريعُ أخرى", tabs["parked_other_projects"]["note"], f"المجموعةُ المقترحة: «{tabs['parked_other_projects']['suggested_group']}»", ""]
    return "\n".join(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    project = sys.argv[1] if len(sys.argv) > 1 else "schoolos"
    tabs = json.loads((ROOT / "projects" / project / "tabs.json").read_text(encoding="utf-8"))
    (ROOT / "docs" / "tab_charters.md").write_text(render(tabs), encoding="utf-8")
    print("docs/tab_charters.md ✔")
