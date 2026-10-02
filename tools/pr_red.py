#!/usr/bin/env python3
"""كشفُ الأحمر الحقيقيّ في الطلبات المفتوحة مع تفاصيله — قراءةٌ فقط (طلبُ المالك عبر 0601، 2026-10-02).

    python pr_red.py [--pr N] [--json] [--no-log]

لكلّ طلبٍ مفتوحٍ فيه فحصٌ **فاشلٌ فعلاً**: اسمُ الفحص، وأوّلُ سطرِ خطأٍ من سجلّه، ورقمُ البطاقة من العنوان/الوصف، والجلسةُ المنفِّذة من اسم الفرع.
**الملغى لا يُعدّ أحمر:** فحصٌ ألغاه تشغيلٌ أحدثُ لنفس الاسم يُهمَل، وفحصٌ ملغىً بلا بديلٍ أحدث يُذكَر «ملغى» منفصلاً (معلومةٌ لا إنذار).
المنطقُ هنا؛ و`pr_watch.py` و`watch_once.py` يستعملانه. لا يرسل رسائل (الشيفرةُ لا تراسل الجلسات): يُنتج النصَّ الجاهز.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

REPO = "D:/shschool_mvp"
REAL_FAIL = {"FAILURE", "TIMED_OUT", "ERROR", "STARTUP_FAILURE", "ACTION_REQUIRED"}
CARD = re.compile(r"W-\d{8}-\d{3}")
RUN_ID = re.compile(r"/actions/runs/(\d+)")
ERR_LINE = re.compile(r"(error|failed|assert|traceback|exception|✘|خطأ)", re.I)


def _name(c: dict) -> str:
    return c.get("name") or c.get("context") or "؟"


def _when(c: dict) -> str:
    return c.get("completedAt") or c.get("startedAt") or ""


def classify(rollup: list[dict] | None) -> dict:
    """يقسم الفحوص إلى: failed (فاشلٌ فعلاً، آخرُ تشغيلٍ لاسمه)، cancelled (ملغىً بلا بديلٍ أحدث)، pending."""
    latest: dict[str, dict] = {}
    for i, c in enumerate(rollup or []):
        n = c.get("name") or c.get("context") or f"#{i}"  # بلا اسمٍ: لا يُدمج مع غيره
        if n not in latest or _when(c) >= _when(latest[n]):
            latest[n] = c
    failed, cancelled, pending = [], [], []
    for n, c in latest.items():
        outcome = (c.get("conclusion") or c.get("state") or "").upper()
        status = (c.get("status") or "").upper()
        if outcome in REAL_FAIL:
            failed.append(c)
        elif outcome == "CANCELLED":
            cancelled.append(c)
        elif outcome in ("PENDING", "EXPECTED") or (not outcome and status != "COMPLETED"):
            pending.append(c)
    return {"failed": failed, "cancelled": cancelled, "pending": pending}


def card_of(pr: dict) -> str | None:
    m = CARD.search(f"{pr.get('title', '')}\n{pr.get('body') or ''}\n{pr.get('headRefName', '')}")
    return m.group(0) if m else None


def first_error(check: dict, runner=None) -> str:
    """أوّلُ سطرٍ يشبه خطأً من سجلّ الفحص الفاشل؛ نصٌّ فارغٌ إن تعذّرت القراءة (لا يُخمَّن)."""
    m = RUN_ID.search(check.get("detailsUrl") or "")
    if not m:
        return ""
    run = runner or _gh_log
    text = run(m.group(1))
    for ln in text.splitlines():
        s = ln.strip()
        if ERR_LINE.search(s) and len(s) > 8:
            s = s.split("	")[-1]  # سطرُ gh: «الوظيفة⇥الخطوة⇥الطابع النصّ»
            return re.sub(r"^\d{4}-\d{2}-\d{2}T\S+\s*", "", s).strip()[:160]
    return ""


def _gh_log(run_id: str) -> str:
    p = subprocess.run(["gh", "run", "view", run_id, "--log-failed"], cwd=REPO, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    return p.stdout if p.returncode == 0 else ""


def session_of(branch: str) -> str | None:
    try:
        import post_merge_checklist as pm
        return pm.session_for_branch(branch)
    except Exception:  # noqa: BLE001 — الإسنادُ معلومةٌ لا شرط
        return None


def report_for(pr: dict, with_log: bool = True, runner=None, session_lookup=session_of) -> dict | None:
    """تقريرُ أحمرٍ لطلبٍ واحد؛ None إن لم يكن فيه فشلٌ حقيقيّ."""
    cls = classify(pr.get("statusCheckRollup"))
    if not cls["failed"]:
        return None
    checks = [{"name": _name(c), "error": first_error(c, runner) if with_log else "", "url": c.get("detailsUrl", "")} for c in cls["failed"]]
    return {"pr": pr["number"], "title": pr["title"][:70], "branch": pr.get("headRefName", ""), "card": card_of(pr),
            "session": session_lookup(pr.get("headRefName", "")), "checks": checks,
            "cancelled": [_name(c) for c in cls["cancelled"]]}


def render(rep: dict) -> str:
    who = rep["session"] or "جلسةٌ غيرُ مُسنَدة (اسألي 0101)"
    lines = [f"أحمرٌ حقيقيٌّ #{rep['pr']} «{rep['title']}» — البطاقة {rep['card'] or 'غيرُ مذكورة'} — المنفِّذة: {who}"]
    for c in rep["checks"]:
        lines.append(f"  - فشل «{c['name']}»" + (f": {c['error']}" if c["error"] else " (تعذّرت قراءةُ سبب السجلّ)"))
    if rep["cancelled"]:
        lines.append(f"  (ملغى بلا بديلٍ أحدث — ليس أحمر: {'، '.join(rep['cancelled'])})")
    return "\n".join(lines)


def open_prs(only: int | None = None) -> list[dict]:
    fields = "number,title,body,headRefName,statusCheckRollup,isDraft"
    cmd = ["gh", "pr", "view", str(only), "--json", fields] if only else ["gh", "pr", "list", "--state", "open", "--limit", "50", "--json", fields]
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        return []
    data = json.loads(p.stdout)
    return [data] if only else data


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pr", type=int)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()
    reps = [r for pr in open_prs(a.pr) if (r := report_for(pr, with_log=not a.no_log))]
    if a.json:
        print(json.dumps(reps, ensure_ascii=False, indent=2))
    else:
        print("\n".join(render(r) for r in reps) if reps else "لا أحمرَ حقيقيّاً في الطلبات المفتوحة")
    return 1 if reps else 0


if __name__ == "__main__":
    raise SystemExit(main())
