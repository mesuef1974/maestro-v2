#!/usr/bin/env python3
"""أرشفةُ قرارات decisions.md القديمة إلى decisions_archive.md (W-20261025-016، أمر المالك: أرشفة بفهرس).

لا حذفَ: القرارُ القديم يُنقل بنصّه حرفاً بحرف إلى decisions_archive.md (بالترتيب نفسه)، ويبقى في decisions.md الرأسُ والقراراتُ
من تاريخ القطع فصاعداً وكلُّ قرارٍ تاريخُه غيرُ مقروء (الأمان). فهرسُ الأرقام decisions_index.md يغطّي الملفّين معاً.
الافتراضُ عرضٌ فقط (plan)؛ `--apply` ينقل ولا يُشغَّل إلا بعد عرض المسوّدة على 0101. يعيد التشغيلُ نفسُه الناتجَ نفسَه (idempotent).

    python decisions_archive.py                 # عرض: كم قراراً وبايتاً يُنقل، وأيّها محالٌ إليه من الأدوات والبطاقات
    python decisions_archive.py --cutoff 10-11  # تاريخ القطع شهر-يوم (الافتراضي: قبل 14 يوماً من اليوم)
    python decisions_archive.py --apply         # ينفّذ النقل
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "decisions.md"
ARCHIVE = ROOT / "decisions_archive.md"
ARCHIVE_HEAD = (
    "# أرشيف قرارات المالك — مايسترو إدارة الجلسات\n"
    "> قراراتٌ قديمة منقولةٌ بنصّها من decisions.md بلا تعديل ولا حذف (W-20261025-016). الفهرسُ: decisions_index.md. "
    "القراراتُ الجديدة تُلحَق في decisions.md وحده.\n\n"
)
ENTRY = re.compile(r"^- D-(\d+)(?:م)?(-[ء-ي])?(?: \([^)]*\))? \| ([^|]*)\|")
HEADING = re.compile(r"^## D-(\d+)م(-[ء-ي])?\s*\(([^)]*)\)")
DATE = re.compile(r"(\d\d)-(\d\d)")
DREF = re.compile(r"D-(\d+)م")


def all_text(root: Path | None = None) -> str:
    """نصُّ الأرشيف ثم نصُّ السجلّ الحيّ: قارئو القرارات (الفهرس، الفحص، رقمُ التالي، أوامرُ المالك) يقرؤون الاثنين."""
    base = root or ROOT
    parts = []
    for p in (base / "decisions_archive.md", base / "decisions.md"):
        if p.is_file():
            parts.append(p.read_bytes().decode("utf-8").replace("\r\n", "\n"))
    return "\n".join(parts)


def _entry_date(line: str) -> str | None:
    m = ENTRY.match(line) or HEADING.match(line)
    if not m:
        return None
    d = DATE.search(m.group(3))
    return f"{d.group(1)}-{d.group(2)}" if d else ""


def split(text: str, cutoff: str, pinned: frozenset[str] = frozenset()) -> tuple[str, str, list[str]]:
    """(الباقي في الحيّ، المنقول، أرقامُ المنقول). كتلةُ القرار = سطرُه وما يليه حتى القرار التالي؛ التاريخُ غيرُ المقروء يبقى."""
    keep: list[str] = []
    moved: list[str] = []
    ids: list[str] = []
    target = keep
    for line in text.splitlines(keepends=True):
        d = _entry_date(line)
        if d is not None:
            m = ENTRY.match(line) or HEADING.match(line)
            did = f"D-{m.group(1)}م{m.group(2) or ''}"
            old = bool(d) and d < cutoff and did not in pinned
            target = moved if old else keep
            if old:
                ids.append(did)
        target.append(line)
    return "".join(keep), "".join(moved), ids


def references(ids: list[str], root: Path | None = None) -> dict[str, int]:
    """كم موضعاً خارج السجلّين يحيل إلى كلّ قرارٍ منقول (أدواتٌ غير اختبارات، بطاقاتُ الأدوار، الوثائق)."""
    base = root or ROOT
    wanted = {i for i in ids}
    hits: dict[str, int] = {}
    files = [p for p in (base / "tools").glob("*.py") if not p.name.startswith("test_")]
    for sub in ("role_cards", "docs", "handover_notes"):
        files += [p for p in (base / sub).rglob("*.md")] if (base / sub).is_dir() else []
    for p in files:
        try:
            body = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in DREF.finditer(body):
            did = f"D-{m.group(1)}م"
            if did in wanted:
                hits[did] = hits.get(did, 0) + 1
    return hits


PIN_REFS = 10


def pinned_ids(text: str, cutoff: str, min_refs: int, root: Path | None = None) -> frozenset[str]:
    """قراراتٌ كانت ستُنقل لكن الأدوات والبطاقات تحيل إليها كثيراً: تبقى في السجلّ الحيّ."""
    if min_refs <= 0:
        return frozenset()
    _, _, ids = split(text, cutoff)
    return frozenset(i for i, n in references(ids, root).items() if n >= min_refs)


def default_cutoff(days: int = 14) -> str:
    return (datetime.now(timezone(timedelta(hours=3))) - timedelta(days=days)).strftime("%m-%d")


def apply(cutoff: str, live: Path = LIVE, archive: Path = ARCHIVE, pinned: frozenset[str] = frozenset()) -> tuple[int, int]:
    text = live.read_bytes().decode("utf-8").replace("\r\n", "\n")
    keep, moved, ids = split(text, cutoff, pinned)
    if not ids:
        return 0, 0
    existing = archive.read_bytes().decode("utf-8").replace("\r\n", "\n") if archive.is_file() else ARCHIVE_HEAD
    # الأرشيفُ أوّلاً: لو انقطع التنفيذ بعده بقيت القراراتُ في الملفّين لا ضائعة، وإعادةُ التشغيل تُصلح
    archive.write_bytes((existing.rstrip("\n") + "\n" + moved).encode("utf-8"))
    live.write_bytes(keep.encode("utf-8"))
    return len(ids), len(moved.encode("utf-8"))


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cutoff", default=None, help="شهر-يوم؛ القراراتُ الأقدم تُنقل")
    ap.add_argument("--keep-referenced", type=int, default=PIN_REFS,
                    help="قرارٌ يُحال إليه بهذا العدد فأكثر من الأدوات والبطاقات يبقى حيّاً (قاعدةٌ عاملة)؛ 0 يعطّل")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    cutoff = a.cutoff or default_cutoff()
    text = LIVE.read_bytes().decode("utf-8").replace("\r\n", "\n")
    pinned = pinned_ids(text, cutoff, a.keep_referenced)
    keep, moved, ids = split(text, cutoff, pinned)
    print(f"مثبَّتٌ حيّاً لكثرة الإحالة إليه (≥{a.keep_referenced}): {len(pinned)} قراراً")
    refs = references(ids)
    print(f"قطعٌ قبل {cutoff}: يُنقل {len(ids)} قراراً ({len(moved.encode('utf-8'))} بايت) ويبقى {len(keep.encode('utf-8'))} بايتاً")
    top = sorted(refs.items(), key=lambda kv: -kv[1])[:8]
    print(f"قراراتٌ منقولةٌ يحال إليها خارج السجلّين: {len(refs)} — الأكثر: " + ("، ".join(f"{k}×{v}" for k, v in top) or "—"))
    if not a.apply:
        print("عرضٌ فقط — لا نقل (--apply للتنفيذ بعد موافقة 0101)")
        return 0
    n, b = apply(cutoff, pinned=pinned)
    print(f"نُقل {n} قراراً ({b} بايت) إلى {ARCHIVE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
