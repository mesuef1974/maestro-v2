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
    if tabs.get("specialties"):
        out += ["## الاختصاصات (مهاراتُ جلسات 04 وصلاحيّاتُها — ليست تبويبات)", tabs.get("specialties_note", ""), ""]
        for s in tabs["specialties"]:
            out += [f"### {s['name']} (وسم «{s.get('name_tag', '')}»)", f"**الغرض:** {s['purpose']}",
                    "**المهارات:** " + "، ".join(f"`{k}`" for k in s["skills"]), f"**الصلاحيّات:** {s['permissions']}", ""]
    for title, ch in tabs.get("session_policy", {}).get("charters", {}).items():
        out += [f"## ميثاقُ «{title}»", f"**الدور:** {ch['role']}",
                *(f"- **{k}:** {v}" for k, v in ch["scope"].items()),
                "**الأهداف:** " + "؛ ".join(ch["goals"]), "**المؤشّرات:** " + "؛ ".join(ch["kpis"]),
                "**طريقةُ العمل:**", *(f"- {m}" for m in ch["method"]),
                "**المخرجات:** " + "؛ ".join(ch["outputs"]), f"**الحدود:** {ch['boundaries']}", ""]
    if tabs.get("pending_archive"):
        out += ["## قيد الأرشفة", *(f"- {p['title']}: {p['reason']}" for p in tabs["pending_archive"]), ""]
    out += ["## مشاريعُ أخرى", tabs["parked_other_projects"]["note"], f"المجموعةُ المقترحة: «{tabs['parked_other_projects']['suggested_group']}»", ""]
    return "\n".join(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    project = sys.argv[1] if len(sys.argv) > 1 else "schoolos"
    import hashlib

    tabs = json.loads((ROOT / "projects" / project / "tabs.json").read_text(encoding="utf-8"))
    target = ROOT / "docs" / "tab_charters.md"
    sidecar = ROOT / "docs" / ".tab_charters.sha"
    # حارسٌ: تعديلٌ يدويٌّ على الملفّ المولَّد كان يضيع صامتاً عند إعادة التوليد (ضاعت بنودُ STOP وبوّابة المنطق وD-88م — 2026-10-02)
    if target.exists() and sidecar.exists() and "--force" not in sys.argv:
        on_disk = hashlib.sha256(target.read_bytes()).hexdigest()
        if on_disk != sidecar.read_text().strip():
            sys.exit("docs/tab_charters.md عُدِّل يدويّاً منذ آخر توليد — أيُّ تعديلٍ يجب أن يكون في tabs.json (المصدر). انقل التعديلَ إليه ثمّ أعد التشغيل (أو --force لتجاهل الحارس).")
    text = render(tabs)
    target.write_text(text, encoding="utf-8")
    sidecar.write_text(hashlib.sha256(target.read_bytes()).hexdigest())
    print("docs/tab_charters.md ✔")
