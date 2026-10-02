#!/usr/bin/env python3
"""يولّد الأقسامَ [آلي] من لوحة الحالة (2 التدفّق، 3 الحِمل) إلى stdout — لا يكتب أيَّ ملفّ (ألصِقها في board_state.md).

    python render_auto_sections.py [--no-fetch] [--write]

--write: يستبدل القسمين 2 و3 داخل board_state.md نفسِه (ويُبقي الأقسامَ اليدويّةَ كما هي) فلا تبقى اللوحةُ «الحيّةُ» قديمة.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def tool(script: str, *extra: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(HERE / script), "--json", *extra], capture_output=True, encoding="utf-8", errors="replace", check=False
    )
    if proc.returncode != 0:
        sys.exit(f"{script} فشل: {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout)


def main() -> None:
    if "--write" in sys.argv:
        write_board()
        return
    render()


def write_board() -> None:
    import contextlib
    import io
    import re

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        render()
    board = HERE.parent / "board_state.md"
    text = board.read_text(encoding="utf-8")
    new = buf.getvalue().rstrip("\n") + "\n\n"
    out, n = re.subn(r"## 2\) التدفّق.*?(?=## 4\))", lambda _m: new, text, count=1, flags=re.S)
    if n != 1:
        sys.exit("لم أجد القسمين 2 و3 في board_state.md — لم أكتب شيئاً")
    board.write_text(out, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("board_state.md ✔ (القسمان 2 و3 مُحدَّثان)")


def render() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # طرفيّةُ ويندوز (cp1256) تُسقط الطباعةَ عند العربيّة وبعض الرموز
    flow = tool("flow_metrics.py", "--days", "3")
    load = tool("session_load_v2.py", *(["--no-fetch"] if "--no-fetch" in sys.argv else []))
    c = flow["cycle_h"]
    print(f"## 2) التدفّق [آلي — الدوحة {flow['generated_doha']}]")
    print(f"- مدموجٌ {flow['merged']} في {flow['window_days']} أيّام ({flow['throughput_per_day']}/يوم)")
    print(f"- زمنُ الدورة (س): متوسّط {c['mean']} · وسيط {c['median']} · p75 {c['p75']} · p90 {c['p90']} · أقصى {c['max']}")
    print(f"- WIP المتوقَّع (ليتل بالمتوسّط): {flow['wip_expected_littles_mean']}؛ المفتوحُ فعلاً: {flow['open_prs']}؛ التراكمُ {flow['backlog_ratio_actual_vs_expected']}×")
    print(f"- عمرُ المفتوح: وسيط {flow['open_age_h']['median']} س، الأقدم {flow['open_age_h']['oldest']} س\n")
    print(f"## 3) حِملُ الجلسات [آلي — الدوحة {load['generated_doha']}] (WIP≤{load['wip_limit']}، ثقيل≥{load['heavy_mb']}MB)")
    print("| الجلسة | طلبات | إيداعاتٌ غيرُ مدموجة | MB | أحداثُ اليوم | الحالة |\n|---|---|---|---|---|---|")
    for r in load["sessions"]:
        flags = "، ".join(f for f, on in (("فوق-WIP", r["over_wip"]), ("ثقيل", r["heavy"]), ("مثقلة", r["overloaded"])) if on) or "—"
        prs = (" (#" + ", #".join(map(str, r["pr_numbers"])) + ")") if r["pr_numbers"] else ""
        print(f"| {r['session']} | {r['open_prs']}{prs} | {r['unmerged_commits']} | {r['context_mb']} | {r['events_today']} | {flags} |")
    print(f"\n- لا إسنادَ جديداً: {[r['session'] for r in load['sessions'] if r['overloaded']] or 'لا أحد'}")
    if load["unowned_prs"]:
        print(f"- طلباتٌ بلا صاحب: {load['unowned_prs']}")
    if load["unnamed_trees"]:
        print(f"- أشجارٌ بلا اسم (أضِفها إلى session_names.json): {load['unnamed_trees']}")
    for w in load["warnings"]:
        print(f"- ⚠ {w}")


if __name__ == "__main__":
    main()
