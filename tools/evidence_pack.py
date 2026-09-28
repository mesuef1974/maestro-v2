#!/usr/bin/env python3
"""حزمةُ الأدلّة لطلب دمجٍ (المرحلة 5 ← 6): ما يقرؤه المالكُ بدل الفروق الخام. قراءةٌ فقط عبر gh.

المبنيُّ الآن (المرحلة 1): خطورةٌ من المسارات، حجمٌ، حالةُ الفحوص، سطرُ الاعتماد، صفحاتٌ يُنصح بمعاينتها.
المواصفةُ فقط (المرحلة 2، تحتاج خادماً يعمل): لقطاتُ قبل/بعد، CSS الخامّ، CLS/LCP/INP، عددُ الاستعلامات — تظهر «غير مقيس»
بدل أن تُخترَع أرقامُها. التفاصيلُ في docs/evidence_pack_spec.md.

    python evidence_pack.py 700
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from risk_tier import BASE_TEMPLATES, classify_paths  # noqa: E402

FIELDS = "number,isDraft,mergeStateStatus,additions,deletions,changedFiles,headRefOid,body,files,statusCheckRollup"
APPROVAL = re.compile(r"اعتُمد من المالك على 8500 — \d{4}-\d{2}-\d{2}")
EXEMPT = re.compile(r"مشمولٌ باستثناء الفلو")
TIER_AR = {"light": "خفيفة (اعتمادٌ بكلمة)", "low": "منخفضة", "medium": "متوسّطة", "high": "عالية"}


def summarize_checks(rollup: list[dict] | None) -> dict:
    ok = fail = pending = 0
    failing: list[str] = []
    for c in rollup or []:
        verdict = (c.get("conclusion") or c.get("state") or "").upper()
        if verdict in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            ok += 1
        elif verdict in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"):
            fail += 1
            failing.append(c.get("name") or c.get("context") or "؟")
        else:
            pending += 1
    return {"ok": ok, "fail": fail, "pending": pending, "failing": failing[:5]}


def page_hints(paths: list[str]) -> list[str]:
    hints = []
    for p in paths:
        p = p.replace("\\", "/")
        if p.startswith("static/css/custom/"):
            hints.append("كلُّ الصفحات (CSS عامّ) — نهاراً وليلاً وبعرض 375")
        elif p in BASE_TEMPLATES:
            hints.append("كلُّ الصفحات (قالبٌ أساسيّ)")
        elif p.startswith("templates/") and p.endswith(".html"):
            hints.append(f"القالب {p.removeprefix('templates/')}")
    return sorted(set(hints))[:8]


def build_pack(pr: dict) -> str:
    paths = [f["path"] for f in pr.get("files", [])]
    info = classify_paths(paths)
    checks = summarize_checks(pr.get("statusCheckRollup"))
    body = pr.get("body") or ""
    approval = "موجود" if APPROVAL.search(body) else ("مشمولٌ باستثناء الفلو" if EXEMPT.search(body) else "غائب — لا يُدمج")
    lines = [
        f"# حزمةُ الأدلّة — #{pr['number']}",
        f"**الخطورة:** {TIER_AR[info['tier']]} · **الفئة:** {info['category']} · **المجال:** {info['area']}"
        + (f" · **علامات:** {', '.join(info['flags'])}" if info["flags"] else ""),
        f"**الحجم:** +{pr['additions']} −{pr['deletions']} في {pr['changedFiles']} ملفّاً · **الحالة:** {pr.get('mergeStateStatus', '؟')}"
        + (" · مسوّدة" if pr.get("isDraft") else ""),
        f"**الفحوص:** {checks['ok']} خضراء، {checks['fail']} فاشلة، {checks['pending']} جارية"
        + (f" — الفاشل: {', '.join(checks['failing'])}" if checks["failing"] else ""),
        f"**سطرُ اعتماد المالك في الوصف:** {approval}",
        "",
        "## أين يُعاين",
        *(f"- {h}" for h in page_hints(paths)),
        *([] if page_hints(paths) else ["- لا أثرَ مرئيّاً مستنتَجاً من المسارات"]),
        "",
        "## قياساتٌ قبل النشر",
        "- [x] حرّاسُ CI وبوّابةُ الجودة (أعلاه)",
        "- [ ] لقطاتُ قبل/بعد لكلّ دورٍ (غيرُ مقيسٍ آليّاً بعد — المرحلة 2)",
        "- [ ] CSS الخامّ مقابل السقف (غيرُ مقيس)",
        "- [ ] CLS/LCP/INP مقابل الميزانيّة (غيرُ مقيس)",
        "- [ ] عددُ الاستعلامات للصفحات المتأثّرة (غيرُ مقيس)",
    ]
    if info["tier"] == "high":
        lines += ["", "## خطورةٌ عالية", "- هجرةٌ أو أمنٌ: تحقّقْ من توسيعٍ-ثمّ-تقليص (P4-1)، وقابليّةِ الرجوع، وأثرِ PDPPL قبل الاعتماد"]
    if "hot_file" in info["flags"]:
        lines += ["- ملفٌّ ساخنٌ مشترك: رتّبْ الدمجَ لتفادي التعارض"]
    return "\n".join(lines) + "\n"


def fetch(number: int) -> dict:
    proc = subprocess.run(["gh", "pr", "view", str(number), "--json", FIELDS], capture_output=True,
                          encoding="utf-8", errors="replace", check=False, cwd="D:/shschool_mvp")
    if proc.returncode != 0:
        sys.exit(f"gh فشل: {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(build_pack(fetch(int(sys.argv[1]))))
