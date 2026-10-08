#!/usr/bin/env python3
"""تقريرُ التوكنز الأسبوعيّ من سجلّات جلسات Claude — قراءةٌ فقط (0102، 2026-10-08).

    python token_report.py [--days 7] [--top 8] [--json]

يطبع ≤20 سطراً: المخرجات، وقراءةَ/كتابةَ الذاكرة المؤقتة، ووسيطَ أوّل طلبٍ (الأرضيّة)، ونصيبَ الوكلاء الفرعيّين،
وأكثرَ الجلسات استهلاكاً. الأساسُ 2026-10-08: مخرجات 283M، وسيط أوّل طلب 109k، نصيب الوكلاء 11.9%.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path.home() / ".claude" / "projects"


def scan(days: int):
    cut = time.time() - days * 86400
    sess = defaultdict(lambda: dict(req=0, out=0, cr=0, cc=0, first=None, models=set(), side_out=0, proj=""))
    for f in ROOT.glob("*/**/*.jsonl"):
        if f.stat().st_mtime < cut:
            continue
        sid = f.stem if f.parent.parent == ROOT else f.parent.parent.name
        seen = set()
        for line in f.open(encoding="utf-8", errors="replace"):
            if '"usage"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            m = d.get("message") or {}
            u = m.get("usage")
            if d.get("type") != "assistant" or not u:
                continue
            rid = d.get("requestId") or d.get("uuid")
            if rid in seen:
                continue
            seen.add(rid)
            s = sess[sid]
            s["proj"] = f.relative_to(ROOT).parts[0]
            o = u.get("output_tokens", 0)
            cr = u.get("cache_read_input_tokens", 0)
            cc = u.get("cache_creation_input_tokens", 0)
            s["req"] += 1
            s["out"] += o
            s["cr"] += cr
            s["cc"] += cc
            if d.get("isSidechain") or f.parent.name == "subagents":
                s["side_out"] += o
            elif s["first"] is None:
                s["first"] = u.get("input_tokens", 0) + cr + cc
            if m.get("model"):
                s["models"].add(m["model"])
    return sess


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    s = scan(a.days)
    out = sum(x["out"] for x in s.values())
    cr = sum(x["cr"] for x in s.values())
    cc = sum(x["cc"] for x in s.values())
    side = sum(x["side_out"] for x in s.values())
    firsts = [x["first"] for x in s.values() if x["first"]]
    multi = sum(1 for x in s.values() if len(x["models"]) > 1)
    r = dict(
        days=a.days, sessions=len(s), output=out, cache_read=cr, cache_create=cc,
        hit=round(cr / (cr + cc), 3) if cr + cc else 0,
        first_median=int(statistics.median(firsts)) if firsts else 0,
        subagent_output_share=round(side / out, 3) if out else 0, multi_model_sessions=multi,
    )
    if a.json:
        print(json.dumps(r, ensure_ascii=False))
        return
    print(f"آخر {a.days} أيام — {r['sessions']} جلسة")
    print(f"مخرجات {out/1e6:.1f}M | قراءة ذاكرة {cr/1e6:.0f}M | كتابة {cc/1e6:.0f}M | إصابة {r['hit']:.3f}")
    print(f"وسيط أوّل طلب (الأرضيّة) {r['first_median']:,} | نصيب الوكلاء الفرعيّين {r['subagent_output_share']:.1%} | جلسات بأكثر من نموذج {multi}")
    print("أكثر الجلسات استهلاكاً (مخرجات | كتابة ذاكرة | طلبات):")
    for sid, x in sorted(s.items(), key=lambda kv: -(kv[1]["out"] + kv[1]["cc"]))[: a.top]:
        print(f"  {sid[:8]} {x['proj'][-34:]:34} {x['out']/1e6:5.1f}M {x['cc']/1e6:6.1f}M {x['req']:5}")


main()
