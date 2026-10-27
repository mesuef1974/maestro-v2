#!/usr/bin/env python3
"""قياس رموز الحمل الابتدائي بمحلّل حقيقي — قراءةٌ فقط (0103، W-20261013-029).

    python token_measure.py --roles [--json]       رموز كل مكوّنٍ لكل دور
    python token_measure.py --reinject [--days 7]  إعادات حقن ملفات التعليمات لكل جلسة
    python token_measure.py --file <مسار> [--json] رموز ملفٍّ واحد
    python token_measure.py --calibrate            معامل الفرق عن تقدير الحروف÷2.2

المحلّل المحلّي `tiktoken` (cl100k_base) بلا شبكة. وليس محلّلَ Anthropic، فالعدُّ تقريبيٌّ للعربية
ويُعلَن معاملُ خطئه في `docs/token_baseline_2026-10-13.md`. عدّادُ Anthropic الرسميّ `--api` يرسل نصَّ الملفّات
إلى خدمةٍ خارجيّة فهو معطَّلٌ إلّا بإذن المالك الصريح ولم يُنفَّذ هنا عمداً.
لا يكتب الأداةُ في أيّ ملفٍّ تقيسه.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

HOME = Path.home()
WORK = Path(__file__).resolve().parent.parent  # delivery_manager_work
PROJECT_ROOTS = [Path("D:/shschool_mvp")]  # الدستور المحمَّل في الجلسات الأصليّة
#: مواضعُ احتياطيّة لـflow.md حين لا يوجد في الجذر الأصليّ (شجرةُ عملٍ أحدثُ منه)
FLOW_FALLBACKS = sorted(Path("D:/shschool_mvp/.claude/worktrees").glob("*/docs/governance/flow.md"))
MEMORY = HOME / ".claude" / "projects" / "D--shschool-mvp" / "memory" / "MEMORY.md"
GLOBAL_MD = HOME / ".claude" / "CLAUDE.md"
CARDS = WORK / "role_cards"
LOGS = HOME / ".claude" / "projects"
REINJECT_MARK = "Instruction files were re-read"


def _encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception as exc:  # بلا شبكة ولا حزمة: فشلٌ نظيف لا تقدير صامت
        sys.exit(f"المحلّل tiktoken غير متاح ({exc.__class__.__name__}); لا عدَّ بلا محلّل حقيقي")


_ENC = None


def count(text: str) -> int:
    global _ENC
    if _ENC is None:
        _ENC = _encoder()
    return len(_ENC.encode(text, disallowed_special=()))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def estimate_chars(text: str) -> int:
    """التقدير القديم المستعمل في التقارير: حروف÷2.2."""
    return round(len(text) / 2.2)


def _project_files() -> tuple[Path | None, Path | None]:
    """الدستور وflow.md المستورد من أوّل جذرٍ فيه الاثنان."""
    for root in PROJECT_ROOTS:
        md = root / "CLAUDE.md"
        flow = root / "docs" / "governance" / "flow.md"
        if md.exists():
            if flow.exists():
                return md, flow
            return md, (FLOW_FALLBACKS[0] if FLOW_FALLBACKS else None)
    return None, None


def components(role: str) -> dict[str, tuple[Path | None, str]]:
    md, flow = _project_files()
    card = CARDS / f"{role}.md"
    return {
        "CLAUDE.md العام": (GLOBAL_MD, read(GLOBAL_MD)),
        "CLAUDE.md المشروع": (md, read(md) if md else ""),
        "flow.md المستورد": (flow, read(flow) if flow else ""),
        "MEMORY.md": (MEMORY, read(MEMORY)),
        "بطاقة الدور": (card, read(card)),
        "INDEX.md": (CARDS / "INDEX.md", read(CARDS / "INDEX.md")),
    }


def roles() -> list[str]:
    return sorted(p.stem for p in CARDS.glob("*.md") if p.stem != "INDEX")


def measure_roles() -> dict:
    out = {}
    for role in roles():
        comp = {}
        for name, (_p, text) in components(role).items():
            comp[name] = {"chars": len(text), "tokens": count(text), "estimate": estimate_chars(text)}
        out[role] = {
            "components": comp,
            "total_tokens": sum(c["tokens"] for c in comp.values()),
            "total_estimate": sum(c["estimate"] for c in comp.values()),
        }
    return out


def reinject(days: int) -> dict:
    cut = time.time() - days * 86400
    per = defaultdict(int)
    for f in LOGS.glob("*/**/*.jsonl"):
        if f.stat().st_mtime < cut:
            continue
        sid = f.stem if f.parent.parent == LOGS else f.parent.parent.name
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                n = sum(1 for line in fh if REINJECT_MARK in line)
        except OSError:
            continue
        if n:
            per[sid] += n
    return dict(per)


def first_request_median(days: int = 7) -> int | None:
    """وسيط أوّل طلبٍ رئيسيّ (مدخلات + قراءة/كتابة الذاكرة المؤقتة) من السجلّات."""
    cut = time.time() - days * 86400
    firsts = []
    for f in LOGS.glob("*/**/*.jsonl"):
        if f.stat().st_mtime < cut or f.parent.name == "subagents":
            continue
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"usage"' not in line or '"type":"assistant"' not in line.replace(" ", ""):
                        continue
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    u = (d.get("message") or {}).get("usage")
                    if u and not d.get("isSidechain"):
                        firsts.append(
                            u.get("input_tokens", 0)
                            + u.get("cache_read_input_tokens", 0)
                            + u.get("cache_creation_input_tokens", 0)
                        )
                        break
        except OSError:
            continue
    return int(statistics.median(firsts)) if firsts else None


def calibrate() -> dict:
    rows = []
    for role in roles():
        for name, (_p, text) in components(role).items():
            if text:
                rows.append((count(text), estimate_chars(text)))
    real = sum(r for r, _ in rows)
    est = sum(e for _, e in rows)
    return {
        "sum_tokens": real,
        "sum_estimate": est,
        "ratio_real_over_estimate": round(real / est, 3) if est else None,
        "median_first_request": first_request_median(),
    }


def _table(data: dict) -> str:
    lines = ["الدور | رموز المجموع | تقدير حروف÷2.2 | أكبر مكوّن"]
    for role, d in data.items():
        top = max(d["components"].items(), key=lambda kv: kv[1]["tokens"])
        lines.append(f"{role} | {d['total_tokens']} | {d['total_estimate']} | {top[0]} ({top[1]['tokens']})")
    return "\n".join(lines[:21])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roles", action="store_true")
    ap.add_argument("--reinject", action="store_true")
    ap.add_argument("--file")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--api", action="store_true", help="معطَّل: يرسل النصَّ إلى خدمة خارجيّة")
    a = ap.parse_args()
    if a.api:
        sys.exit("--api معطَّلٌ: إرسالُ نصوص المشروع إلى خدمةٍ خارجيّةٍ يلزمه إذنُ المالك الصريح")
    if a.file:
        text = read(Path(a.file))
        res = {"file": a.file, "chars": len(text), "tokens": count(text), "estimate": estimate_chars(text)}
        print(json.dumps(res, ensure_ascii=False) if a.json else f"{a.file}: {res['tokens']} رمزاً ({res['chars']} حرفاً)")
        return 0
    if a.calibrate:
        res = calibrate()
        print(json.dumps(res, ensure_ascii=False) if a.json else res)
        return 0
    if a.reinject:
        res = reinject(a.days)
        if a.json:
            print(json.dumps(res, ensure_ascii=False))
        else:
            vals = sorted(res.values(), reverse=True)
            print(f"جلسات فيها إعادة حقن: {len(res)}؛ المجموع {sum(vals)}؛ الأكبر {vals[:5]}")
        return 0
    res = measure_roles()
    print(json.dumps(res, ensure_ascii=False) if a.json else _table(res))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
