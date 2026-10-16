#!/usr/bin/env python3
"""المعاينةُ الدفعيّة (W-20261014-010): ورقةٌ واحدةٌ بالبطاقات الجاهزة للمعاينة — قراءةٌ فقط.

    python preview_batch.py [--out ورقة.html] [--integrate-file مخرج.txt] [--platform-dir D:/shschool_mvp] [--json]

تقرأ الدفترَ (ready_for_review) ومخرجَ `scripts/preview.sh integrate` وتبني ورقةً بثلاثة أقسام:
  يظهر تلقائياً على 8500 · يحتاج تثبيتاً أو لم يُعرف فرعه · لا يظهر (بسببه من integrate).
لا تعتمد ولا تثبّت ولا تعدّل preview.sh ولا الدفتر؛ والاعتمادُ للمالك وحدَه.
حقلُ المعاينة في البطاقة `preview` = {url, role, username, severity, head}؛ ما غاب يُعلَّم ناقصاً ولا يُخمَّن.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

import ledger
import ledger_lead_time as llt

AUTO, PIN, BLOCKED = "auto", "pin", "blocked"
TITLES = {
    AUTO: "يظهر تلقائياً على 8500 (مودَع ومُدمَج في التكامل)",
    PIN: "يحتاج تثبيتاً من 0501 (غير مودَع) أو لم يُعرف فرعه",
    BLOCKED: "لا يظهر على 8500",
}
MISSING = "ناقص"
FIELDS = ("url", "role", "username", "severity", "head")
FIELD_LABELS = {"url": "الرابط الكامل", "role": "الدور", "username": "الرقم الوظيفي التجريبي", "severity": "الخطورة", "head": "الرأس"}
#: معنى كلّ رقمٍ يُعرض على المالك (قاعدة 10-09).
MEANINGS = {
    "median": "الوسيط: نصف البطاقات اعتُمدت في هذا الزمن أو أقلّ",
    "mean": "المتوسّط: يرفعه ما طال انتظاره",
    "p90": "p90: تسعٌ من كلّ عشر بطاقاتٍ اعتُمدت في هذا الزمن أو أقلّ",
}

_PLUS = re.compile(r"^\s*\+\s+(\S+)")
_CROSS = re.compile(r"^\s*✗\s+(\S+)\s+—\s+(.*)$")


def parse_integrate(text: str) -> tuple[set[str], dict[str, str]]:
    """من مخرج integrate: الأشجارُ الداخلةُ (+) والمستثناةُ (✗) بسببها؛ سطرُ «pr-1067 «…»» يُؤخذ اسمُه الأوّل."""
    shown: set[str] = set()
    blocked: dict[str, str] = {}
    for line in text.splitlines():
        m = _PLUS.match(line)
        if m:
            shown.add(m.group(1))
            continue
        m = _CROSS.match(line)
        if m:
            blocked[m.group(1)] = m.group(2).strip()
    return shown, blocked


def tree_of(card: dict) -> str | None:
    """اسمُ الشجرة/الفرع من البطاقة نصّاً دقيقاً (بلا تخمين): tree ثم branch بلا بادئة claude/."""
    name = card.get("tree") or card.get("branch")
    if not name:
        return None
    return name.removeprefix("refs/heads/").removeprefix("claude/")


def classify(card: dict, shown: set[str], blocked: dict[str, str]) -> tuple[str, str]:
    tree = tree_of(card)
    if tree is None:
        return PIN, "لم يُسجَّل فرعُ البطاقة؛ تُعامَل كغير مودَعة ويثبّتها 0501"
    if tree in shown:
        return AUTO, "تدخل التكاملَ تلقائياً"
    if tree in blocked:
        return BLOCKED, blocked[tree]
    return PIN, "لا تظهر في مخرج integrate: غيرُ مودَعة أو فرعُها غير مسجَّل"


def build_rows(items: dict, shown: set[str], blocked: dict[str, str], states=("ready_for_review",)) -> list[dict]:
    rows = []
    for cid in sorted(items):
        card = items[cid]
        if card.get("state") not in states:
            continue
        section, why = classify(card, shown, blocked)
        pv = card.get("preview") or {}
        row = {"id": cid, "section": section, "why": why, "holder": card.get("held_by") or MISSING,
               "problem": (card.get("problem") or "")[:140], "tree": tree_of(card)}
        for f in FIELDS:
            row[f] = pv.get(f) or MISSING
        rows.append(row)
    return rows


def baseline(events: list[dict]) -> dict:
    """زمنُ «جاهزٌ للمعاينة»←الاعتماد بالساعات: وسيط ومتوسّط وp90 وعدد (من ledger_lead_time نفسه)."""
    v = sorted(llt.stage_hours(events)["review_to_approve"])
    if not v:
        return {"n": 0}
    p90 = v[min(len(v) - 1, int(round(0.9 * (len(v) - 1))))]
    return {"median": round(statistics.median(v), 1), "mean": round(statistics.mean(v), 1), "p90": round(p90, 1), "n": len(v)}


def run_integrate(platform_dir: str) -> str:
    """قراءةٌ فقط: أمر integrate بلا وسيطٍ يعرض الخطّة ولا يغيّر الحالة."""
    r = subprocess.run(["bash", "scripts/preview.sh", "integrate"], cwd=platform_dir, capture_output=True, text=True,
                       encoding="utf-8", timeout=180)
    return r.stdout


def render_html(rows: list[dict], base: dict, stamp: str) -> str:
    e = html.escape

    def section(key: str) -> str:
        part = [r for r in rows if r["section"] == key]
        head = f"<h2>{e(TITLES[key])} <span class=n>({len(part)})</span></h2>"
        if not part:
            return head + "<p class=empty>لا بطاقات.</p>"
        cols = "".join(f"<th>{e(FIELD_LABELS[f])}</th>" for f in FIELDS)
        body = ""
        for r in part:
            cells = "".join(
                f"<td class={'miss' if r[f] == MISSING else 'ok'}>{e(str(r[f]))}</td>" for f in FIELDS)
            body += f"<tr><td>{e(r['id'])}<br><small>{e(r['holder'])}</small></td><td>{e(r['problem'])}</td>{cells}<td>{e(r['why'])}</td></tr>"
        return (f"{head}<div class=wrap><table><thead><tr><th>البطاقة / المنفِّذ</th><th>المشكلة</th>{cols}"
                f"<th>السبب</th></tr></thead><tbody>{body}</tbody></table></div>")

    if base.get("n"):
        meas = (f"<p>زمنُ «جاهزٌ للمعاينة» إلى الاعتماد (ساعات، على {base['n']} بطاقة): "
                f"وسيط {base['median']} — {e(MEANINGS['median'])}؛ متوسّط {base['mean']} — {e(MEANINGS['mean'])}؛ "
                f"p90 {base['p90']} — {e(MEANINGS['p90'])}.</p>")
    else:
        meas = "<p>الأساس غيرُ مقيس.</p>"
    return f"""<!doctype html><html lang=ar dir=rtl><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>ورقة المعاينة الدفعية</title>
<style>:root{{--bg:#fafaf7;--fg:#1d1d1b;--line:#d9d6cc;--miss:#a33;--ok:#1d1d1b}}
@media(prefers-color-scheme:dark){{:root{{--bg:#181816;--fg:#ecebe5;--line:#3a3935;--miss:#ff8a8a;--ok:#ecebe5}}}}
body{{background:var(--bg);color:var(--fg);font:16px/1.7 Tajawal,sans-serif;margin:0 auto;max-width:1200px;padding:1rem 16px}}
h1{{font-size:1.4rem}}h2{{font-size:1.1rem;margin-block-start:1.6rem}}.n{{opacity:.7}}
.wrap{{overflow-x:auto}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid var(--line);padding:.4rem .6rem;text-align:start;vertical-align:top}}
thead th{{position:sticky;top:0;background:var(--bg)}}.miss{{color:var(--miss);font-weight:700}}small{{opacity:.7}}
.note{{border:1px solid var(--line);padding:.6rem .8rem}}</style>
<h1>ورقة المعاينة الدفعية</h1><p><small>{e(stamp)} — قراءةٌ فقط من الدفتر ومخرج integrate</small></p>
<p class=note>هذه الورقة لا تعتمد ولا تثبّت: الاعتمادُ للمالك وحدَه على الرأس المذكور، وصمتُه ليس اعتماداً. «ناقص» يعني أنّ البطاقة لم تحمل الحقل في <code>preview</code> فلم يُخمَّن.</p>
{meas}{section(AUTO)}{section(PIN)}{section(BLOCKED)}</html>"""


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out")
    ap.add_argument("--integrate-file")
    ap.add_argument("--platform-dir", default="D:/shschool_mvp")
    ap.add_argument("--ledger", help="مسار ملف الدفتر (الافتراضيّ دفترُ هذا المستودع)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    text = Path(a.integrate_file).read_text(encoding="utf-8") if a.integrate_file else run_integrate(a.platform_dir)
    shown, blocked = parse_integrate(text)
    events = ledger.load_events(a.ledger)
    rows = build_rows(ledger.reduce_state(events), shown, blocked)
    base = baseline(events)
    if a.json:
        print(json.dumps({"rows": rows, "baseline": base}, ensure_ascii=False, indent=2))
    else:
        for key in (AUTO, PIN, BLOCKED):
            part = [r for r in rows if r["section"] == key]
            print(f"{TITLES[key]}: {len(part)}" + "".join(f"\n  {r['id']} — {r['why']}" for r in part))
        if base.get("n"):
            print(f"الأساس جاهز←اعتماد: وسيط {base['median']} س | متوسّط {base['mean']} س | p90 {base['p90']} س | عدد {base['n']}")
    if a.out:
        Path(a.out).write_text(render_html(rows, base, ledger.now_doha()), encoding="utf-8")
        print(f"كُتبت الورقة: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
