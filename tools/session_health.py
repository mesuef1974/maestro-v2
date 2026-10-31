#!/usr/bin/env python3
"""صحّةُ الجلسات: حجمُ السياق الحاليّ والخمولُ وتعدّدُ النماذج — قراءةٌ فقط (0102، 2026-10-08).

    python session_health.py [--hours 72] [--warn 250000]

السياقُ = آخرُ طلبٍ (input + قراءة + كتابة ذاكرة). فوق --warn: مرشّحةٌ لـ/compact أو للاستبدال بجلسةٍ خفيفة.
خاملةٌ ≥ 6 س: مرشّحةٌ للأرشفة بعد التحقّق من الدفتر (archive_candidates.py) — لا أرشفةَ بلا أمر المالك.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path.home() / ".claude" / "projects"


def info(f: Path):
    last, models, title, cwd = None, set(), "", ""
    for line in f.open(encoding="utf-8", errors="replace"):
        if '"usage"' not in line and "itle" not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        for k in ("customTitle", "aiTitle", "title"):
            if isinstance(d.get(k), str):
                title = d[k]
        m = d.get("message") or {}
        u = m.get("usage")
        if d.get("type") == "assistant" and u and not d.get("isSidechain"):
            last = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
            cwd = d.get("cwd", cwd)
            if m.get("model"):
                models.add(m["model"])
    return last, models, title, cwd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=72)
    ap.add_argument("--warn", type=int, default=250000)
    a = ap.parse_args()
    now = time.time()
    rows = []
    for f in ROOT.glob("*/*.jsonl"):
        age = (now - f.stat().st_mtime) / 3600
        if age > a.hours:
            continue
        ctx, models, title, cwd = info(f)
        if ctx is None:
            continue
        rows.append((ctx, age, len(models), title or Path(cwd).name or f.stem[:8], f.stem[:8]))
    rows.sort(reverse=True)
    heavy = [r for r in rows if r[0] >= a.warn]
    idle = [r for r in rows if r[1] >= 6]
    print(f"{len(rows)} جلسة خلال {a.hours} س | ثقيلة (≥{a.warn // 1000}k): {len(heavy)} | خاملة ≥6س: {len(idle)}")
    for ctx, age, nm, name, sid in rows[:15]:
        flag = "ثقيلة" if ctx >= a.warn else ""
        flag += " خاملة" if age >= 6 else ""
        flag += " نماذج>1" if nm > 1 else ""
        print(f"  {sid} {name[:36]:36} سياق {ctx // 1000:4}k  خمول {age:5.1f}س {flag}")


main()
