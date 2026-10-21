"""تفكيك أرضيّة «أوّل طلب»: توزيعها، وارتباطها برسالة المستخدم الأولى، ووسيطها لكل مجلّد مشروع (أداة 0102).
الاستعمال: python tools/floor_decomp.py [--days 7]"""
import sys
import argparse, json, statistics, time
from collections import defaultdict
from pathlib import Path

ROOT = Path.home() / ".claude" / "projects"


def first_request(f):
    """(توكنات أوّل طلب، حروف رسالة المستخدم الأولى) أو None."""
    first, ulen = None, 0
    for line in f.open(encoding="utf-8", errors="replace"):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("isSidechain"):
            continue
        t = d.get("type")
        if t == "user" and first is None:
            c = (d.get("message") or {}).get("content")
            ulen += len(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
        elif t == "assistant" and first is None:
            u = (d.get("message") or {}).get("usage")
            if u:
                first = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                break
    return (first, ulen) if first else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args()
    cut = time.time() - a.days * 86400
    rows, proj = [], defaultdict(list)
    for f in ROOT.glob("*/*.jsonl"):
        if f.stat().st_mtime < cut:
            continue
        r = first_request(f)
        if r:
            rows.append(r)
            proj[f.parent.name[-22:]].append(r[0])
    fs = sorted(x[0] for x in rows)
    print(f"جلسات {len(rows)} | وسيط {int(statistics.median(fs)):,} | أدنى {fs[0]:,} | ر25 {fs[len(fs)//4]:,} | ر75 {fs[3*len(fs)//4]:,} | أقصى {fs[-1]:,}")
    print(f"رسالة المستخدم الأولى: وسيط {int(statistics.median([x[1] for x in rows])):,} حرفاً")
    print("وسيط أوّل طلب لكل مجلّد مشروع (العدد | الوسيط | الأدنى):")
    for k, v in sorted(proj.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"  {k}  {len(v)}  {int(statistics.median(v)):,}  {min(v):,}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
