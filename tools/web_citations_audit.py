#!/usr/bin/env python3
"""تدقيقُ الاستشهادات بالويب: هل كلُّ رابطٍ خارجيٍّ استُشهد به مسجَّلٌ في مصدر الحقيقة (ext_*.md)؟ — قراءةٌ فقط (قرارُ المالك 2026-10-04).

القاعدة: كلُّ ما يُجلب من الإنترنت أو يُسكرَب يُضاف إلى `AAdocs/ministry_data/2026_2027/ext_<الموضوع>_<التاريخ>.md` بحقولٍ إلزاميّة؛ ولا يُستشهَد بنتيجة بحثٍ ما لم تُسجَّل.
هذه الأداةُ تحسب مؤشّرَ 0301: «ما بُحث عنه في الويب ووُثِّق ÷ ما بُحث عنه في الويب».

    python web_citations_audit.py                                  # الإعداد الافتراضيّ
    python web_citations_audit.py --sot <مجلّد> [--sot <مجلّد>…] --scan <ملفّ|مجلّد> [--scan …] [--strict]

المخرج: عددُ الروابط الخارجيّة المستشهَد بها، المسجَّل منها في ext_، غيرُ المسجَّل (قائمة)، وملفّاتُ ext_ الناقصة الحقول. --strict: رمزُ خروج 1 عند أيّ نقص.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOT = [
    Path("D:/shschool_mvp/AAdocs/ministry_data/2026_2027"),
    Path("D:/shschool_mvp/.claude/worktrees/epic-tesla-9f1df1/AAdocs/ministry_data/2026_2027"),  # شجرة 0301 قبل الدفع
]
DEFAULT_SCAN = [ROOT / "decisions.md", ROOT / "docs", ROOT / "handover_notes"]

#: الحقولُ الإلزاميّة في ملفّ ext_ (قرارُ المالك 2026-10-04) — تُفحص بوجود الكلمة المفتاحيّة.
REQUIRED_FIELDS = {
    "الرابط": ("الرابط", "رابط", "http"),
    "تاريخ الجلب": ("تاريخ الجلب", "تاريخ الجلب:"),
    "النوع": ("النوع",),
    "الثقة": ("الثقة", "ثقة"),
    "حرفي أم ملخّص": ("حرفي", "ملخّص", "ملخص"),
    "ما لم يُتحقَّق منه": ("لم يُتحقَّق", "لم يتحقق", "لم يُتحقق"),
}

URL_RE = re.compile(r"https?://[^\s<>)\]»\"'`،؛]+")
#: روابطُ ليست «ويباً خارجيّاً» بحثيّاً: المحلّيّ والمستودع وأدوات الجلسات.
IGNORED_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "github.com", "claude.ai", "claude.com", "anthropic.com", "railway.app", "example.com", "fonts.googleapis.com", "fonts.gstatic.com", "cdnjs.cloudflare.com", "cdn.jsdelivr.net", "unpkg.com")


def normalize(url: str) -> str:
    u = url.rstrip(".,;:!?)")
    u = re.sub(r"^https?://(www\.)?", "", u, flags=re.I)
    return u.rstrip("/").lower()


def is_external(url: str) -> bool:
    host = re.sub(r"^https?://", "", url, flags=re.I).split("/")[0].split(":")[0].lower()
    return not any(host == h or host.endswith("." + h) for h in IGNORED_HOSTS)


def iter_text_files(paths):
    for p in paths:
        p = Path(p)
        if p.is_file():
            yield p
        elif p.is_dir():
            yield from (f for f in sorted(p.rglob("*")) if f.is_file() and f.suffix.lower() in (".md", ".txt", ".html"))


def urls_in(text: str) -> set[str]:
    return {normalize(m.group(0)) for m in URL_RE.finditer(text) if is_external(m.group(0))}


def ext_files(sot_dirs):
    out = []
    for d in sot_dirs:
        d = Path(d)
        if d.is_dir():
            out.extend(sorted(d.glob("ext_*.md")))
    return out


def missing_fields(text: str) -> list[str]:
    miss = []
    for name, keys in REQUIRED_FIELDS.items():
        if not any(k in text for k in keys):
            miss.append(name)
    return miss


def audit(scan_paths, sot_dirs):
    registered: set[str] = set()
    incomplete: dict[str, list[str]] = {}
    exts = ext_files(sot_dirs)
    for f in exts:
        text = f.read_text(encoding="utf-8", errors="replace")
        registered |= urls_in(text)
        m = missing_fields(text)
        if m:
            incomplete[f.name] = m
    cited: dict[str, set[str]] = {}
    ext_names = {f.name for f in exts}
    for f in iter_text_files(scan_paths):
        if f.name in ext_names:  # ملفُّ المصدر نفسُه ليس استشهاداً
            continue
        for u in urls_in(f.read_text(encoding="utf-8", errors="replace")):
            cited.setdefault(u, set()).add(f.name)
    unregistered = {u: sorted(v) for u, v in cited.items() if u not in registered}
    return {
        "ext_files": len(exts),
        "cited": len(cited),
        "registered": len(cited) - len(unregistered),
        "unregistered": unregistered,
        "incomplete": incomplete,
    }


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sot", action="append", help="مجلّد مصدر الحقيقة (يتكرّر)")
    ap.add_argument("--scan", action="append", help="ملفّ أو مجلّد يُفحص استشهاداته (يتكرّر)")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args(argv)
    r = audit(a.scan or DEFAULT_SCAN, a.sot or DEFAULT_SOT)
    pct = (100 * r["registered"] / r["cited"]) if r["cited"] else 100.0
    print(f"ملفّات ext_ في مصدر الحقيقة: {r['ext_files']} | روابطُ خارجيّةٌ مستشهَدٌ بها: {r['cited']} | مسجَّلةٌ: {r['registered']} ({pct:.0f}%؛ الهدف 100%)")
    for u, where in sorted(r["unregistered"].items()):
        print(f"  [غيرُ مسجَّل] {u}  ← {', '.join(where[:3])}")
    for name, miss in r["incomplete"].items():
        print(f"  [ناقصُ الحقول] {name}: {', '.join(miss)}")
    bad = bool(r["unregistered"] or r["incomplete"])
    return 1 if (a.strict and bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())
