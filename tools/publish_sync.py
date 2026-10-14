#!/usr/bin/env python3
"""إبلاغُ «نُشر + الرأس» مجمَّعاً بالرأس بدل رسائل 0601 النصّيّة — بطاقة W-20261014-023 (0701).

    python publish_sync.py --prod-head 331f3ae            # عرضٌ فقط: ما صار في الإنتاج وبطاقاتُه، ويُكتب ملفُّ الإبلاغ
    python publish_sync.py --health-url <رابط /health/>   # يقرأ رأسَ الإنتاج من الحقل commit
    python publish_sync.py --prod-head 331f3ae --no-write  # بلا كتابة ملف

يقابل رؤوسَ الطلبات المدموجة (gh) برأس الإنتاج بـ`git merge-base --is-ancestor` (قراءةٌ فقط، لا fetch ولا تبديل فرع)،
ثمّ برؤوس اعتماد البطاقات في الدفتر (كما تفعل merged_cards_sync.py). فيخرج إبلاغٌ واحدٌ لكلّ رأس إنتاج:
`publish_digest/<رأس8>.md` و`publish_digest/latest.md`؛ وتقرؤه الجلساتُ (0701 و0101 و0105 و0702 والمنفِّذة) بدل رسالةٍ نصّيّةٍ لكلّ منها.

لا تنقل بطاقةً إلى published: النقلُ لـ0601 وحدَها (D-88م) بالأوامر المطبوعة. وما لا بطاقةَ له يُذكر طلباً بلا بطاقة (أدواتٌ/CI).
هذه الأداةُ لا تدّعي قياساً: «في الإنتاج» تعني أنّ إيداعَ الدمج سلفٌ لرأس الإنتاج المعطى، لا أنّ الإنتاج سليمٌ.
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

SLUG = "sh-school/shschool_mvp"
OUT_DIR = HERE.parent / "publish_digest"
DEFAULT_REPO = "D:/shschool_mvp"


def prod_head_from_health(url: str) -> str:
    """يقرأ الحقل commit من /health/ (JSON)."""
    import urllib.request

    with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310 — رابطٌ يمرّره المشغّل
        body = r.read().decode("utf-8", "replace")
    m = re.search(r'"commit"\s*:\s*"([0-9a-f]{7,40})"', body)
    if not m:
        raise SystemExit("لا حقلَ commit في ردّ /health/")
    return m.group(1)


def merged_prs(limit: int) -> list[dict]:
    out = subprocess.run(
        [
            "gh", "pr", "list", "--repo", SLUG, "--state", "merged", "--limit", str(limit),
            "--json", "number,title,headRefOid,mergeCommit,mergedAt",
        ],
        capture_output=True, text=True, encoding="utf-8",
    )
    if out.returncode:
        raise SystemExit("فشل gh: " + (out.stderr or "").strip()[:200])
    return json.loads(out.stdout)


def is_ancestor(repo: str, commit: str, prod: str) -> bool:
    r = subprocess.run(
        ["git", "-C", repo, "merge-base", "--is-ancestor", commit, prod],
        capture_output=True, text=True,
    )
    if r.returncode not in (0, 1):
        raise SystemExit(f"تعذّر merge-base لـ{commit[:8]} مع {prod[:8]}: {(r.stderr or '').strip()[:160]}")
    return r.returncode == 0


def cards_by_head(events: list[dict]) -> dict[str, tuple[str, str]]:
    """رأسُ الاعتماد (8 خانات) ← (رمز البطاقة، آخر حالة).

    الرأسُ يُسجَّل في حدث approved وحدَه (أحداثُ pushed/merged/published بلا رأس)، فيؤخذ آخرُ رأسٍ غيرِ فارغ وآخرُ حالة.
    """
    head_of: dict[str, str] = {}
    state_of: dict[str, str] = {}
    for e in events:
        if e.get("kind") != "state":
            continue
        d = e.get("data", {})
        head = (d.get("head") or d.get("approved_head") or "")[:8]
        if head:
            head_of[e["id"]] = head
        state_of[e["id"]] = d.get("state", "")
    return {h: (cid, state_of.get(cid, "")) for cid, h in head_of.items()}


def build_digest(prod: str, prs: list[dict], cards: dict[str, tuple[str, str]], in_prod) -> dict:
    """يصنّف الطلباتِ المدموجة السلفَ لرأس الإنتاج: بطاقةٌ تنتظر النقل، بطاقةٌ منشورةٌ أصلاً، أو بلا بطاقة."""
    pending, done, no_card = [], [], []
    for p in sorted(prs, key=lambda x: x["number"]):
        mc = (p.get("mergeCommit") or {}).get("oid") or ""
        if not mc or not in_prod(mc):
            continue
        card = cards.get(p["headRefOid"][:8])
        row = {"pr": p["number"], "title": p["title"][:90], "head": p["headRefOid"][:8]}
        if card is None:
            no_card.append(row)
        elif card[1] == "published":
            done.append({**row, "card": card[0]})
        else:
            pending.append({**row, "card": card[0], "state": card[1]})
    return {"prod": prod[:8], "pending": pending, "published": done, "no_card": no_card}


def render(d: dict) -> str:
    lines = [f"# نُشر — رأس الإنتاج {d['prod']}", ""]
    lines.append(
        "تعني «في الإنتاج» أنّ إيداع الدمج سلفٌ لهذا الرأس؛ لا قياسَ لسلامة الإنتاج ولا للمعاينة. النقلُ إلى published لـ0601 وحدَها."
    )
    lines += ["", f"## بطاقاتٌ في الإنتاج وتنتظر النقل إلى published ({len(d['pending'])})"]
    for r in d["pending"]:
        lines.append(f"- {r['card']} ← #{r['pr']} ({r['state']}) {r['title']}")
        lines.append(f"  `python tools/ledger.py move {r['card']} published --head {r['head']} --by 0601`")
    lines += ["", f"## بطاقاتٌ منشورةٌ أصلاً ({len(d['published'])})"]
    lines += [f"- {r['card']} ← #{r['pr']} {r['title']}" for r in d["published"]]
    lines += ["", f"## طلباتٌ في الإنتاج بلا بطاقةٍ بهذا الرأس (أدواتٌ/CI أو رأسٌ تغيّر) ({len(d['no_card'])})"]
    lines += [f"- #{r['pr']} {r['title']}" for r in d["no_card"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--prod-head")
    g.add_argument("--health-url")
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()

    import ledger

    prod = a.prod_head or prod_head_from_health(a.health_url)
    d = build_digest(prod, merged_prs(a.limit), cards_by_head(ledger.load_events()), lambda c: is_ancestor(a.repo, c, prod))
    text = render(d)
    print(text)
    if not a.no_write:
        OUT_DIR.mkdir(exist_ok=True)
        (OUT_DIR / f"{d['prod']}.md").write_text(text, encoding="utf-8")
        (OUT_DIR / "latest.md").write_text(text, encoding="utf-8")
        print(f"كُتب: {OUT_DIR / (d['prod'] + '.md')}")


if __name__ == "__main__":
    main()
