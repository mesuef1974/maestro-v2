#!/usr/bin/env python3
"""جدولُ أسماء الجلسات القديمة: يحوّل رقماً أو اسماً قديماً إلى الرقم/الاسم الحاليّ (جدول التحويل D-198م).

    python session_alias.py 0105            # ← 0104 · الأمان: الثغراتُ والتنبيهات
    python session_alias.py 0402 --legacy   # الرقمُ القديمُ المُعاد استعمالُه

المصدر: session_policy.aliases في tabs.json. قراءةٌ فقط.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABS = ROOT / "projects" / "schoolos" / "tabs.json"


def _load(tabs: dict | None) -> dict:
    return tabs if tabs is not None else json.loads(TABS.read_text(encoding="utf-8"))


def _titles(tabs: dict) -> dict[str, str]:
    """رقمٌ من أربع خانات ← العنوانُ الكامل للجلسة الحاليّة (النواةُ والأعضاء)."""
    out: dict[str, str] = {}
    for t in tabs["session_policy"].get("core_sessions", []) + [m for tab in tabs["tabs"] for m in tab.get("members", [])]:
        out.setdefault(t[:4], t)
    return out


def number_map(tabs: dict | None = None) -> dict[str, str]:
    """رقمٌ قديمٌ أو مدمَج ← رقمٌ حاليّ، من session_policy.aliases وحدَه (بلا «_reused» ولا «_note»).

    يُقرأ TABS عند النداء؛ وملفٌّ مفقودٌ أو تالفٌ يُرجع {} (لا إحالة) ولا يُسقط الأداة التي تستعمله.
    """
    try:
        tabs = _load(tabs)
    except (OSError, ValueError):
        return {}
    aliases = tabs.get("session_policy", {}).get("aliases", {})
    return {k: v for k, v in aliases.items()
            if re.fullmatch(r"\d{4}", k) and isinstance(v, str) and re.fullmatch(r"\d{4}", v)}


def _tree(path: str) -> str:
    return str(path or "").replace("\\", "/").rstrip("/").lower()


def directory_trees(tabs: dict | None = None) -> dict[str, set[str]]:
    """مجلّدٌ خارج أشجار المنصّة ← الأرقامُ المقبولةُ منه (session_policy.directory_trees؛ بلا «_note»).

    المفتاحُ مطبَّعٌ (/ وحروفٌ صغيرة بلا شرطةٍ ختاميّة) ليطابق cwd كما يكتبه التطبيق. ملفٌّ مفقودٌ أو تالفٌ يُرجع {}.
    """
    try:
        tabs = _load(tabs)
    except (OSError, ValueError):
        return {}
    raw = tabs.get("session_policy", {}).get("directory_trees", {}) or {}
    return {_tree(k): {n for n in v if re.fullmatch(r"\d{4}", str(n))}
            for k, v in raw.items() if not k.startswith("_") and isinstance(v, list)}


def canonical(num: str, mapping: dict[str, str] | None) -> str:
    """يتبع سلسلةَ الإحالة (0204 ← 0201 ← 0101) حتى رقمٍ غير مُحال؛ وعند الدوران يُرجع الرقمَ كما هو."""
    seen = {num}
    cur = num
    while mapping and cur in mapping:
        cur = mapping[cur]
        if cur in seen:
            return num
        seen.add(cur)
    return cur


def resolve(name_or_number: str, tabs: dict | None = None, legacy: bool = False) -> str | None:
    """يُرجع الاسمَ الكاملَ الحاليّ إن عُرف، وإلّا الرقمَ الحاليّ؛ و None إن لم يُعرف شيء.

    الرقمُ الحاليّ يُرجَع كما هو. الرقمُ القديمُ المُعاد استعمالُه (مثل 0402) لا يُحلّ إلّا بـ legacy=True
    لأنّه اليومَ جلسةٌ أخرى.
    """
    tabs = _load(tabs)
    m = re.match(r"\s*(\d{4})\b", name_or_number or "")
    if not m:
        return None
    num = m.group(1)
    aliases = tabs["session_policy"].get("aliases", {})
    titles = _titles(tabs)
    if legacy and num in aliases.get("_reused", {}):
        target = aliases["_reused"][num]
    elif num in aliases and not num.startswith("_"):
        target = aliases[num]
    else:
        return titles.get(num) or (num if num in titles else None)
    return titles.get(target, target)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("name")
    ap.add_argument("--legacy", action="store_true")
    a = ap.parse_args()
    r = resolve(a.name, legacy=a.legacy)
    print(r if r else "غيرُ معروف")
    return 0 if r else 1


if __name__ == "__main__":
    raise SystemExit(main())
