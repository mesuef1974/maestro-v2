#!/usr/bin/env python3
"""تقليمُ الذاكرة: يجد الكبيرَ وغيرَ المفهرس، ويقسّم بلا فقد — (0102، 2026-10-08).

    python memory_prune.py                       # تقرير (قراءةٌ فقط)
    python memory_prune.py --index               # يكتب INDEX_unindexed_<تاريخ>.md ويضيف سطراً واحداً إلى MEMORY.md
    python memory_prune.py --split FILE --before 2026-10-01   # ينقل الإدخالات المؤرَّخة «- YYYY-MM-DD» الأقدم إلى أرشيف

لا حذفَ أبداً: نسخةٌ احتياطيّةٌ أوّلاً في ~/.claude/backups، والتقسيمُ يتحقّق أنّ كلَّ سطرٍ باقٍ.
"""
from __future__ import annotations

import argparse
import datetime
import re
import shutil
from pathlib import Path

MEM = Path.home() / ".claude/projects/D--shschool-mvp/memory"
BIG = 100_000
DATED = re.compile(r"- (\d{4}-\d\d-\d\d)")


def backup():
    dst = Path.home() / ".claude/backups" / f"memory_{datetime.date.today()}"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MEM / "MEMORY.md", dst / "MEMORY.md")
    shutil.copytree(MEM / "on_demand", dst / "on_demand", dirs_exist_ok=True)


def orphans():
    m = (MEM / "MEMORY.md").read_text(encoding="utf-8")
    idx = "".join(p.read_text(encoding="utf-8") for p in (MEM / "on_demand").glob("INDEX_*.md"))
    return [
        p for p in sorted((MEM / "on_demand").glob("*.md"))
        if not p.name.startswith("INDEX_") and p.name not in m and p.name not in idx and "_archive_" not in p.name
    ]


def split(name: str, before: str):
    p = MEM / "on_demand" / name
    lines = p.read_text(encoding="utf-8").split("\n")
    dated = [(i, DATED.match(x).group(1)) for i, x in enumerate(lines) if DATED.match(x)]
    first = dated[0][0]
    old = [i for i, d in dated if d < before]
    if not old:
        print("لا إدخالات أقدم من التاريخ.")
        return
    cut = max(old) + 1
    for x in lines[first:cut]:
        m = DATED.match(x)
        assert not m or m.group(1) < before, "الترتيب غير زمنيّ: قسّم يدوياً"
    backup()
    arch = p.with_name(p.stem + "_archive_before_" + before.replace("-", "_") + ".md")
    head = f"---\nname: {arch.stem}\ndescription: أرشيفٌ منقولٌ حرفيّاً من {p.stem} (قبل {before})\nmetadata:\n  node_type: memory\n  type: project\n---\n\n"
    arch.write_text(head + "\n".join(lines[first:cut]) + "\n", encoding="utf-8")
    new = lines[:first] + [f"> أُرشفت الإدخالاتُ قبل {before} في `{arch.name}` (نقلٌ حرفيٌّ لا حذف).", ""] + lines[cut:]
    p.write_text("\n".join(new), encoding="utf-8")
    lost = set(lines) - set(new) - set(arch.read_text(encoding="utf-8").split("\n"))
    print(f"نُقل {cut - first} سطراً؛ مفقود: {len(lost)}؛ الرئيسيّ {p.stat().st_size:,}B والأرشيف {arch.stat().st_size:,}B")
    assert not lost


def index(o):
    backup()
    rows = []
    for p in o:
        t = p.read_text(encoding="utf-8", errors="replace")
        d = re.search(r"^description:\s*(.+)$", t, re.M)
        rows.append(f"- [{p.stem}]({p.name}) — {(d.group(1).strip().strip(chr(34)) if d else '')[:140]}")
    today = datetime.date.today().isoformat()
    f = MEM / "on_demand" / f"INDEX_unindexed_{today.replace('-', '_')}.md"
    head = f"---\nname: {f.stem}\ndescription: ملفّاتٌ غير مفهرسة (جُرد {today})\nmetadata:\n  node_type: memory\n  type: reference\n---\n\n"
    f.write_text(head + "\n".join(rows) + "\n", encoding="utf-8")
    with (MEM / "MEMORY.md").open("a", encoding="utf-8") as fh:
        fh.write(f"- [فهرسُ غير المفهرس {today}](on_demand/{f.name}) — {len(o)} ملفّاً\n")
    print(f"فُهرس {len(o)} ملفّاً في {f.name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--split")
    ap.add_argument("--before")
    a = ap.parse_args()
    if a.split:
        return split(a.split, a.before)
    o = orphans()
    if a.index and o:
        return index(o)
    mm = MEM / "MEMORY.md"
    print(f"MEMORY.md {mm.stat().st_size:,}B / {len(mm.read_text(encoding='utf-8').splitlines())} سطراً (السقف 18KB و120)")
    print(f"غير مفهرسة: {len(o)}")
    for p in sorted((MEM / "on_demand").glob("*.md"), key=lambda x: -x.stat().st_size)[:5]:
        print(f"  كبير: {p.name} {p.stat().st_size:,}B" + ("  ← قسّمه بـ --split" if p.stat().st_size > BIG else ""))


main()
