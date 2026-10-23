#!/usr/bin/env python3
"""قياسُ زمن CI بالمراحل (W-20261020-021، أمر المالك 2026-10-20) — قراءةٌ فقط من gh، لا يكتب في GitHub ولا يشغّل شيئاً.

    python ci_stage_times.py --repo sh-school/shschool_mvp --workflow quality-gate.yml --prs 10 [--out handover_notes/ci_stage_times_….md]

يجمع آخرَ N طلبٍ مختلفٍ (آخرُ تشغيلٍ مكتملٍ لكلّ فرع طلب) ويحسب لكلّ وظيفةٍ وخطوةٍ: العددَ والوسيطَ وp90 والأقصى بالثواني،
ثمّ ترتيبَ أكبر الخطوات هدراً. ما لم يُقَس: انتظارُ المنفِّذ في الطابور قبل بدء الوظيفة (يُعرض منفصلاً كفرق created→started)،
وزمنُ ما بعد CI (الدمج). خطواتُ الإعداد (Set up job وPost) تدخل في الحساب ولا تُحذف.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from datetime import datetime

RUN_FIELDS = "databaseId,headBranch,event,conclusion,status,createdAt,startedAt,updatedAt"


def gh(args: list[str]) -> str:
    p = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if p.returncode:
        raise RuntimeError(f"gh {' '.join(args[:3])}: {(p.stderr or '').strip()[-200:]}")
    return p.stdout


def secs(start: str | None, end: str | None) -> float | None:
    """الثواني بين طابعين ISO؛ None إن غاب أحدهما أو كان «0001» (لم يكتمل)."""
    try:
        if not start or not end or start.startswith("0001") or end.startswith("0001"):
            return None
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return None
    d = (b - a).total_seconds()
    return d if d >= 0 else None


def pick_runs(runs: list[dict], prs: int) -> list[dict]:
    """آخرُ تشغيلٍ مكتملٍ لكلّ فرعٍ حتى prs فروع، من الأحدث؛ تُهمل التشغيلاتُ غير المكتملة."""
    seen, out = set(), []
    for r in sorted(runs, key=lambda r: r.get("createdAt", ""), reverse=True):
        if r.get("status") != "completed" or r.get("conclusion") in ("cancelled", "skipped"):
            continue
        key = r.get("headBranch") or str(r.get("databaseId"))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
        if len(out) >= prs:
            break
    return out


def _stats(vals: list[float]) -> dict:
    s = sorted(vals)
    p90 = s[min(len(s) - 1, int(round(0.9 * (len(s) - 1))))]
    return {"n": len(s), "median": statistics.median(s), "p90": p90, "max": s[-1], "total": sum(s)}


def collect(runs: list[dict], jobs_of) -> dict:
    """يجمع {runs: [...], jobs: {اسم: [ثوانٍ]}, steps: {(وظيفة، خطوة): [ثوانٍ]}, queue: [ثوانٍ]}؛ jobs_of(run_id) -> قائمة jobs."""
    jobs: dict[str, list[float]] = {}
    steps: dict[tuple[str, str], list[float]] = {}
    queue: list[float] = []
    walls: list[tuple[int, str, float]] = []
    for r in runs:
        starts, ends = [], []
        for j in jobs_of(r["databaseId"]):
            d = secs(j.get("startedAt"), j.get("completedAt"))
            if d is None:
                continue
            jobs.setdefault(j["name"], []).append(d)
            starts.append(j["startedAt"])
            ends.append(j["completedAt"])
            q = secs(r.get("createdAt"), j.get("startedAt"))
            if q is not None:
                queue.append(q)
            for s in j.get("steps", []):
                sd = secs(s.get("startedAt"), s.get("completedAt"))
                if sd is not None:
                    steps.setdefault((j["name"], s["name"]), []).append(sd)
        if starts:
            wall = secs(min(starts), max(ends))
            if wall is not None:
                walls.append((r["databaseId"], r.get("headBranch", ""), wall))
    return {"jobs": jobs, "steps": steps, "queue": queue, "walls": walls}


def fmt(x: float) -> str:
    return f"{x:.0f}"


def report(data: dict, runs: list[dict], repo: str, workflow: str, top: int = 15) -> str:
    L = [f"# زمن CI بالمراحل — {workflow} ({repo})", ""]
    L.append(f"عيّنة: {len(runs)} طلباً (آخرُ تشغيلٍ مكتملٍ لكلّ فرع). المصدر: gh run list/view. كلُّ الأزمنة بالثواني من طوابع GitHub.")
    L.append("ما لم يُقَس: زمنُ ما بعد CI (الدمج)، ومحتوى الخطوات الداخلي، وتشغيلاتُ push على main.")
    L += ["", "## الزمن الكلّيّ لكلّ تشغيل (أول وظيفة تبدأ ← آخر وظيفة تنتهي)", "", "| التشغيل | الفرع | ثوانٍ |", "|---|---|---|"]
    for rid, br, w in data["walls"]:
        L.append(f"| {rid} | {br} | {fmt(w)} |")
    if data["walls"]:
        st = _stats([w for _, _, w in data["walls"]])
        L.append(f"\nالوسيط {fmt(st['median'])} · p90 {fmt(st['p90'])} · الأقصى {fmt(st['max'])}")
    if data["queue"]:
        st = _stats(data["queue"])
        L.append(f"\nانتظارُ المنفِّذ (إنشاء التشغيل ← بدء الوظيفة): وسيط {fmt(st['median'])} · p90 {fmt(st['p90'])} · أقصى {fmt(st['max'])}")
    L += ["", "## لكلّ وظيفة", "", "| الوظيفة | عدد | وسيط | p90 | أقصى |", "|---|---|---|---|---|"]
    for name, v in sorted(data["jobs"].items(), key=lambda kv: -_stats(kv[1])["median"]):
        st = _stats(v)
        L.append(f"| {name} | {st['n']} | {fmt(st['median'])} | {fmt(st['p90'])} | {fmt(st['max'])} |")
    L += ["", f"## أكبر {top} خطوةً بالوسيط", "", "| الوظيفة | الخطوة | عدد | وسيط | p90 | أقصى |", "|---|---|---|---|---|---|"]
    ranked = sorted(data["steps"].items(), key=lambda kv: -_stats(kv[1])["median"])[:top]
    for (job, step), v in ranked:
        st = _stats(v)
        L.append(f"| {job} | {step} | {st['n']} | {fmt(st['median'])} | {fmt(st['p90'])} | {fmt(st['max'])} |")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default="sh-school/shschool_mvp")
    ap.add_argument("--workflow", default="quality-gate.yml")
    ap.add_argument("--prs", type=int, default=10)
    ap.add_argument("--fetch", type=int, default=80, help="عدد التشغيلات المسحوبة قبل الانتقاء")
    ap.add_argument("--out", help="ملف التقرير (مثلاً handover_notes/ci_stage_times_….md)")
    a = ap.parse_args(argv)
    try:
        runs = json.loads(gh(["run", "list", "--repo", a.repo, "--workflow", a.workflow, "--event", "pull_request",
                              "--limit", str(a.fetch), "--json", RUN_FIELDS]))
        chosen = pick_runs(runs, a.prs)

        def jobs_of(rid):
            return json.loads(gh(["run", "view", str(rid), "--repo", a.repo, "--json", "jobs"]))["jobs"]

        text = report(collect(chosen, jobs_of), chosen, a.repo, a.workflow)
    except (RuntimeError, ValueError) as exc:
        print(f"✘ {exc}", file=sys.stderr)
        return 3
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)
    return 0 if len(chosen) >= a.prs else 4  # 4: العيّنة أقلّ من المطلوب (القبول عشرة)


if __name__ == "__main__":
    raise SystemExit(main())
