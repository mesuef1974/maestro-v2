#!/usr/bin/env python3
"""دليلُ عناوين الجلسات: رقمُ الجلسة ← معرّفُها `local_<uuid>` الحيّ (0102، 2026-10-09).

    python session_directory.py            # كلُّ الجلسات غير المؤرشفة: رقم ومعرّف واسم
    python session_directory.py 0101       # معرّفُ جلسةٍ واحدة (يُطبع المعرّفُ وحده)
    python session_directory.py 0102       # رقمٌ مدمَج ← معرّفُ مستقبِلته (0701) مع سطرِ تنبيهٍ في stderr
    python session_directory.py --json     # للسكربتات

السبب (قياس 2026-10-09): الإرسال بالاسم يصل الصندوقَ ولا يوقظ جلسةً خاملة، والإرسال بالمعرّف `local_<uuid>` يوقظها؛
والمعرّفُ لا يُعرف إلا من `list_sessions` أو من `from` في رسالةٍ واردة، فكانت الجلساتُ تضلّ وتُوجَّه يدوياً.
المصدر: ملفّاتُ جلسات تطبيق Claude على القرص (sessionId وtitle وisArchived وlastActivityAt). قراءةٌ فقط.
عند تكرار الرقم (جلسةٌ أُعيد تشغيلُها) يُختار الأحدثُ نشاطاً.
الرقمُ المدمَج (مفتاحٌ في session_policy.aliases بـtabs.json، مثل 0102 ← 0301) لا يظهر في الدليل
ولو بقيت جلستُه القديمةُ حيّة، فلا يُوقَظ؛ ويُحلّ عند الطلب إلى مستقبِلته. الجدولُ يُقرأ من tabs.json وحدَه (session_alias).
جلسةٌ ثابتةٌ خارج أشجار المنصّة (0101 الخفيفة في delivery_manager_work) تُقبل من session_policy.directory_trees وحدَه:
مجلّدٌ ← أرقامٌ، والرقمُ المذكورُ لا يُقبل إلا من مجلّده؛ والمطابقةُ بالرقم والمجلّد لا بالعنوان فلا تكسرها إعادةُ التسمية،
وأيُّ جلسةٍ أخرى في المجلّد نفسِه (مثل 0703) لا تُقبل فلا تُوقَظ خطأً.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import session_alias  # noqa: E402

BASE = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude-code-sessions"
NUM = re.compile(r"^\s*(\d{4})\b")


def _admitted(num: str, tree: str, trees: dict[str, set[str]]) -> bool:
    """شجرةُ المنصّة لكلّ رقمٍ غيرِ مربوطٍ بمجلّد؛ والرقمُ المربوطُ (directory_trees) من مجلّده وحدَه."""
    bound = {t for t, nums in trees.items() if num in nums}
    if bound:
        # مفتاحٌ ينتهي بـ«/*» يقبل أيَّ شجرةٍ مباشرةً تحته (أشجارُ العمل تتبدّل عند كلّ إعادة تشغيل؛ W-20261028-007)
        return tree in bound or any(b.endswith("/*") and tree.startswith(b[:-1]) and "/" not in tree[len(b) - 1:] for b in bound)
    return "shschool_mvp" in tree


def entries(base: Path | None = None, aliases: dict[str, str] | None = None,
            trees: dict[str, set[str]] | None = None) -> dict[str, dict]:
    """رقمٌ ← {id, title, at} لأحدث جلسةٍ غير مؤرشفةٍ في شجرة المنصّة أو في مجلّدٍ مربوطٍ برقمها (directory_trees)؛
    بلا الأرقام المدمَجة (مفاتيح aliases)."""
    root = BASE if base is None else base
    merged = session_alias.number_map() if aliases is None else aliases
    bound = session_alias.directory_trees() if trees is None else trees
    best: dict[str, dict] = {}
    for f in root.glob("*/*/local_*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        m = NUM.match(str(d.get("title", "")))
        if not m or d.get("isArchived"):
            continue
        num, act = m.group(1), int(d.get("lastActivityAt") or 0)
        # worktreePath قد يكون null لجلسةٍ بلا شجرة (الخفيفة): المجلّدُ حينها cwd
        if not _admitted(num, session_alias._tree(d.get("worktreePath") or d.get("cwd") or ""), bound):
            continue
        if num in merged:
            continue  # رقمٌ مدمَج: لا يُوقَظ ولا يُعرض، والإحالةُ إلى مستقبِلته
        if num not in best or act > best[num]["at"]:
            best[num] = {"id": d["sessionId"], "title": d["title"], "at": act}
    return dict(sorted(best.items()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("number", nargs="?")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    aliases = session_alias.number_map()
    e = entries(aliases=aliases)
    if a.number:
        target = session_alias.canonical(a.number, aliases)
        if target != a.number:
            print(f"{a.number} مدمَجةٌ في {target} (session_policy.aliases): المعرّفُ أدناه لـ{target}", file=sys.stderr)
        if target not in e:
            print(f"لا جلسةَ حيّةً بالرقم {target}", file=sys.stderr)
            return 1
        print(e[target]["id"])
    elif a.json:
        print(json.dumps({k: v["id"] for k, v in e.items()}, ensure_ascii=False))
    else:
        for k, v in e.items():
            print(f"{k}  {v['id']}  {v['title'][:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
