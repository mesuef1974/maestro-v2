#!/usr/bin/env python3
"""دراسةُ حِمل المالك من الطلبات المدموجة (قراءةٌ فقط، لا تطبع عناوينَ ولا أسماء): توزيعُ الفئات والأحجام واليوم بتوقيت الدوحة."""
import json, re, subprocess, sys, statistics as st
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
DOHA = timezone(timedelta(hours=3))
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 7
raw = subprocess.run(["gh","pr","list","--state","merged","--limit","700","--json","number,createdAt,mergedAt,additions,deletions,changedFiles,files,author"],
                     capture_output=True, encoding="utf-8", cwd="D:/shschool_mvp").stdout
prs = json.loads(raw)
now = datetime.now(timezone.utc); since = now - timedelta(days=DAYS)
prs = [p for p in prs if datetime.fromisoformat(p["mergedAt"].replace("Z","+00:00")) >= since]
bots = [p for p in prs if (p.get("author") or {}).get("is_bot") or "bot" in ((p.get("author") or {}).get("login","")).lower()]
prs = [p for p in prs if p not in bots]
RANK = ["migration","security","visible_ui","backend","infra","roadmap_data","tests_only","docs_only"]
def cat(paths):
    c = set()
    for f in paths:
        if f.startswith("roadmap/migrations/"): c.add("roadmap_data")
        elif re.search(r"/migrations/[^/]+\.py$", f): c.add("migration")
        elif re.search(r"(^|/)(permissions|rls|crypto|consent|erasure)[^/]*\.py$|/auth/", f): c.add("security")
        elif f.startswith(("templates/","static/")) or f.endswith((".html",".css",".js")): c.add("visible_ui")
        elif f.startswith(("tests/",)): c.add("tests_only")
        elif f.startswith((".github/","scripts/",".claude/","docker","requirements","Makefile")) or "docker-compose" in f: c.add("infra")
        elif f.endswith(".md") or f.startswith(("docs/","AAdocs/")): c.add("docs_only")
        elif f.endswith(".py"): c.add("backend")
        else: c.add("infra")
    for r in RANK:
        if r in c: return r
    return "infra"
by_cat = Counter(); day_cat = defaultdict(Counter); size = defaultdict(list); files = []
for p in prs:
    paths = [x["path"] for x in p.get("files", [])]
    c = cat(paths); by_cat[c] += 1
    d = datetime.fromisoformat(p["mergedAt"].replace("Z","+00:00")).astimezone(DOHA).date()
    day_cat[d][c] += 1; size[c].append(p["additions"] + p["deletions"]); files.append(p["changedFiles"])
tot = len(prs)
print(f"نافذة {DAYS} أيّام | غيرُ آليّة: {tot} (آليّة مستبعدة: {len(bots)}) | {tot/DAYS:.1f}/يوم")
print("الفئة | العدد | نسبة | وسيط الأسطر | وسيط الملفّات؟")
for c in RANK:
    if by_cat[c]:
        print(f"{c:11} {by_cat[c]:4} {100*by_cat[c]/tot:5.1f}%  med_lines={int(st.median(size[c])):5}")
print("وسيطُ الملفّات لكلّ طلب:", st.median(files), "| p90:", sorted(files)[int(0.9*len(files))-1])
print("\nاليوم (الدوحة): إجماليّ | مرئيّ | هجرة/أمن | وثائق+اختبارات+أدوات")
for d in sorted(day_cat):
    c = day_cat[d]; t = sum(c.values())
    print(d, f"{t:4}  visible={c['visible_ui']:3}  mig+sec={c['migration']+c['security']:2}  light={c['docs_only']+c['tests_only']+c['infra']:3}")
# نموذج الحِمل: دقائق المراجعة لكلّ فئة (افتراضٌ صريح يُعدَّل)
MIN = {"roadmap_data":0.5,"migration":5.0,"security":5.0,"visible_ui":3.0,"backend":2.0,"infra":1.0,"tests_only":0.5,"docs_only":0.5}
bund = defaultdict(set); cnt_in = Counter()
for p in prs:
    paths=[x["path"] for x in p.get("files", [])]; c=cat(paths)
    d = datetime.fromisoformat(p["mergedAt"].replace("Z","+00:00")).astimezone(DOHA).date()
    area = (paths[0].split("/")[0] if paths else "-")
    bund[d].add((c, area)); cnt_in[(d,c,area)] += 1
nb = [len(v) for v in bund.values()]
print(f"حزمُ المراجعة (فئة×مجال) في اليوم: وسيط {int(st.median(nb))}، أقصى {max(nb)}، متوسّط {sum(nb)/len(nb):.0f}")
bcost = 0
for (d,c,a),n in cnt_in.items(): bcost += MIN[c]*(1+0.4*(n-1))
print(f"كلفةُ المراجعة بالحزم (الأوّل كاملاً وكلُّ تالٍ 40%): ≈{bcost/len(bund):.0f} د/يوم (على أيّام العمل الفعليّة {len(bund)})")
per_day = sum(by_cat[c]*MIN[c] for c in RANK)/DAYS
print(f"\nدقائقُ المراجعة لو عُرض كلُّ طلبٍ منفرداً (افتراضاتٌ: {MIN}): ≈{per_day:.0f} د/يوم")
