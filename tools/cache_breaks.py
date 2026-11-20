#!/usr/bin/env python3
"""مقياس انكسار ذاكرة التخزين المؤقت في جلسات Claude — قراءةٌ فقط (بند aitmpl، 2026-11-20).

    python cache_breaks.py [--days 7] [--top 8] [--min-prefix 20000] [--json]

نسبة الإصابة الكلّيّة في `token_report.py` لا تقول أين ضاعت الذاكرة. هذا المقياس يمشي طلبات الخيط
الرئيسيّ لكل جلسة بترتيبها، ويعدّ «انكساراً» كلَّ طلبٍ قرأ من الذاكرة أقلَّ من نصف بادئة الطلب
السابق (مدخلاته كلّها)، فيُعاد كتابة ما كان يُفترض أن يُقرأ. لكل انكسار سبب:

- مهلة: الفجوة بين الطلبين أطول من عمر الذاكرة (ساعة إن كُتبت بـ1h، وإلا خمس دقائق).
- نموذج: تغيّر النموذج بين الطلبين.
- ضغط: حدّ ضغط أو مسح وقع بينهما.
- بادئة: لا شيء مما سبق؛ تغيّرت البادئة نفسها (ملف تعليمات أو قائمة أدوات أو خادم MCP).

الهدر = البادئة السابقة − المقروء، ووزنه بمضاعِف الكتابة ناقص مضاعِف القراءة (2.0 أو 1.25، و0.1)
بوحدة رمز إدخال أساسيّ، فيُقارن بين الجلسات بلا ربطٍ بسعر نموذج بعينه.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path.home() / ".claude" / "projects"
TTL_1H = 3600
TTL_5M = 300
WRITE_MULT = {"1h": 2.0, "5m": 1.25}
READ_MULT = 0.1
CAUSES = ("مهلة", "نموذج", "ضغط", "بادئة")


@dataclass
class Req:
    """طلبٌ واحد من الخيط الرئيسيّ بما يلزم المقياس."""

    ts: float
    model: str
    inp: int
    cr: int
    cc: int
    ttl: str  # "1h" أو "5m"
    compact_before: bool = False

    @property
    def prefix(self) -> int:
        return self.inp + self.cr + self.cc


@dataclass
class Break:
    ts: float
    cause: str
    wasted: int
    weighted: float


@dataclass
class Session:
    sid: str
    proj: str
    reqs: int = 0
    cr: int = 0
    cc: int = 0
    breaks: list[Break] = field(default_factory=list)

    @property
    def wasted(self) -> int:
        return sum(b.wasted for b in self.breaks)


def _ts(s: str | None) -> float:
    if not s:
        return 0.0
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return 0.0


def parse_lines(lines) -> list[Req]:
    """يحوّل أسطر سجلّ جلسة إلى طلبات الخيط الرئيسيّ مرتّبةً، بلا تكرار رقم الطلب."""
    out: list[Req] = []
    seen: set[str] = set()
    pending_compact = False
    for line in lines:
        if '"compact_boundary"' in line or '"isCompactSummary":true' in line:
            pending_compact = True
            continue
        if '"usage"' not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        m = d.get("message") or {}
        u = m.get("usage")
        if d.get("type") != "assistant" or not u or d.get("isSidechain"):
            continue
        rid = d.get("requestId") or d.get("uuid")
        if rid in seen:
            continue
        seen.add(rid)
        cache = u.get("cache_creation") or {}
        ttl = "1h" if cache.get("ephemeral_1h_input_tokens", 0) or not cache.get("ephemeral_5m_input_tokens", 0) else "5m"
        out.append(Req(
            ts=_ts(d.get("timestamp")), model=m.get("model") or "",
            inp=u.get("input_tokens", 0), cr=u.get("cache_read_input_tokens", 0),
            cc=u.get("cache_creation_input_tokens", 0), ttl=ttl, compact_before=pending_compact,
        ))
        pending_compact = False
    return out


def classify(prev: Req, cur: Req) -> str:
    """سبب الانكسار بأولويّة: ضغط ثم نموذج ثم مهلة ثم بادئة."""
    if cur.compact_before:
        return "ضغط"
    if prev.model and cur.model and prev.model != cur.model:
        return "نموذج"
    if cur.ts - prev.ts > (TTL_1H if prev.ttl == "1h" else TTL_5M):
        return "مهلة"
    return "بادئة"


def find_breaks(reqs: list[Req], min_prefix: int = 20000) -> list[Break]:
    """انكسار: طلبٌ قرأ أقلّ من نصف بادئة سابقه، والبادئة السابقة لا تقلّ عن min_prefix."""
    out: list[Break] = []
    for prev, cur in itertools.pairwise(reqs):
        if prev.prefix < min_prefix or cur.cr * 2 >= prev.prefix:
            continue
        wasted = min(prev.prefix - cur.cr, cur.cc + cur.inp)
        if wasted <= 0:
            continue
        out.append(Break(cur.ts, classify(prev, cur), wasted, wasted * (WRITE_MULT[cur.ttl] - READ_MULT)))
    return out


def scan(days: int, min_prefix: int, root: Path = ROOT) -> list[Session]:
    cut = time.time() - days * 86400
    sessions: list[Session] = []
    # ملفات الوكلاء الفرعيّين في subagents/ خيوطٌ جانبيّة لها بادئتها الخاصّة: خارج المقياس
    for f in root.glob("*/*.jsonl"):
        if f.stat().st_mtime < cut:
            continue
        with f.open(encoding="utf-8", errors="replace") as fh:
            reqs = [r for r in parse_lines(fh) if r.ts >= cut]
        if not reqs:
            continue
        s = Session(f.stem, f.parent.name, len(reqs), sum(r.cr for r in reqs), sum(r.cc for r in reqs))
        s.breaks = find_breaks(reqs, min_prefix)
        sessions.append(s)
    return sessions


def summarize(sessions: list[Session], days: int) -> dict:
    breaks = [b for s in sessions for b in s.breaks]
    cr = sum(s.cr for s in sessions)
    cc = sum(s.cc for s in sessions)
    by = {c: {"n": 0, "wasted": 0} for c in CAUSES}
    for b in breaks:
        by[b.cause]["n"] += 1
        by[b.cause]["wasted"] += b.wasted
    wasted = sum(b.wasted for b in breaks)
    return {
        "days": days, "sessions": len(sessions), "requests": sum(s.reqs for s in sessions),
        "breaks": len(breaks), "wasted": wasted, "weighted": round(sum(b.weighted for b in breaks)),
        "cache_write": cc, "wasted_share_of_write": round(wasted / cc, 3) if cc else 0,
        "hit": round(cr / (cr + cc), 3) if cr + cc else 0, "by_cause": by,
    }


def render(r: dict, sessions: list[Session], top: int) -> str:
    lines = [
        f"آخر {r['days']} أيام — {r['sessions']} جلسة، {r['requests']:,} طلباً في الخيط الرئيسيّ",
        (f"إصابة {r['hit']:.3f} | انكسارات {r['breaks']} | هدر {r['wasted']/1e6:.1f}M رمز"
         f" = {r['wasted_share_of_write']:.1%} من كتابة الذاكرة | موزون {r['weighted']/1e6:.1f}M رمز إدخال أساسيّ"),
        "حسب السبب (عدد | هدر):",
    ]
    for c in CAUSES:
        x = r["by_cause"][c]
        lines.append(f"  {c:6} {x['n']:5} {x['wasted']/1e6:7.1f}M")
    lines.append("أكثر الجلسات هدراً (هدر | انكسارات | طلبات):")
    for s in sorted(sessions, key=lambda s: -s.wasted)[:top]:
        if not s.breaks:
            break
        lines.append(f"  {s.sid[:8]} {s.proj[-34:]:34} {s.wasted/1e6:6.1f}M {len(s.breaks):4} {s.reqs:5}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--min-prefix", type=int, default=20000)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    sessions = scan(a.days, a.min_prefix)
    r = summarize(sessions, a.days)
    print(json.dumps(r, ensure_ascii=False) if a.json else render(r, sessions, a.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
