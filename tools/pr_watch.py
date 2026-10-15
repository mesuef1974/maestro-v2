#!/usr/bin/env python3
"""مراقبُ الطلبات — يكشف ما يفوت المراقبةَ اليدويّة: طلبٌ جديد، أخضرٌ جاهز، أحمر، تعارض، بلا سطر اعتماد، أخضرٌ ينتظر الدمج،
وبطاقةٌ في `pushed` بلا طلب. المصدرُ GitHub والسجلُّ لا الرسائل، ويطبع **عند التغيّر فقط**.

    python pr_watch.py --once                       لقطةٌ واحدة بما يحتاج انتباهاً
    python pr_watch.py --loop [--interval 120]      للمراقبة بأداة Monitor (كلُّ سطرٍ حدث)
    python pr_watch.py --check-heartbeat            عمرُ آخر دورة بالدقائق؛ رمزُ الخروج 1 إن تجاوز 40 (لـwatch_once)

النبضةُ في `ledger/pr_watch_heartbeat.json`: موتُ المراقبة نفسِها (مهلةُ Monitor 30 د، أو موتُ الجلسة) لا يمرّ صامتاً.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import ledger  # noqa: E402

REPO = Path("D:/shschool_mvp")
HEARTBEAT = ROOT / "ledger" / "pr_watch_heartbeat.json"
HEARTBEAT_STALE_MIN = 40
APPROVAL = re.compile(r"اعتُمد من المالك|اعتمد من المالك")
EXEMPT = re.compile(r"مزامنةُ خارطةٍ")
NO_APPROVAL_MIN, GREEN_WAIT_MIN, PUSHED_NO_PR_MIN, REPEAT_MIN = 10, 30, 15, 60
RED = {"FAILURE", "CANCELLED", "TIMED_OUT", "ERROR", "STARTUP_FAILURE", "ACTION_REQUIRED"}
AR = {"green": "أخضر", "red": "أحمر", "pending": "قيدَ التشغيل", "cancelled": "ملغى بلا بديل"}


def check_state(rollup: list[dict] | None) -> str:
    """أخضر / أحمر (فشلٌ حقيقيّ فقط) / ملغى (بلا بديلٍ أحدث) / معلّق من statusCheckRollup.

    الملغى الذي حلّ محلَّه تشغيلٌ أحدثُ لا يُحسب (pr_red.classify)؛ فلا يُقرأ إلغاءُ التزامنِ أحمرَ كاذباً.
    """
    import pr_red

    cls = pr_red.classify(rollup)
    if cls["failed"]:
        return "red"
    if cls["pending"]:
        return "pending"
    return "cancelled" if cls["cancelled"] else "green"


def normalize(pr: dict) -> dict:
    text = f"{pr.get('title', '')}\n{pr.get('body') or ''}"
    return {"n": pr["number"], "title": pr["title"][:70], "draft": bool(pr.get("isDraft")),
            "merge": pr.get("mergeStateStatus"), "checks": check_state(pr.get("statusCheckRollup")),
            "approval": bool(APPROVAL.search(text)), "exempt": bool(EXEMPT.search(text)),
            "created": pr["createdAt"], "text": text}


def _age(iso: str, now: datetime) -> float:
    return (now - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds() / 60


def events(prev: dict[int, dict] | None, cur: dict[int, dict], now: datetime, alerted: dict[tuple, datetime]) -> list[str]:
    """أحداثُ الفرق بين الدورتين؛ `alerted` يمنع تكرارَ التنبيه الزمنيّ أكثرَ من مرّةٍ في الساعة."""
    out: list[str] = []

    def throttled(key: tuple) -> bool:
        last = alerted.get(key)
        if last and (now - last) < timedelta(minutes=REPEAT_MIN):
            return True
        alerted[key] = now
        return False

    for n, p in sorted(cur.items()):
        old = (prev or {}).get(n)
        tag = f"#{n} — {p['title']}"
        if old is None:
            out.append(f"طلبٌ جديد {tag} — الفحوص: {AR[p['checks']]} — سطرُ الاعتماد: {'✔' if p['approval'] or p['exempt'] else '✘'}")
        else:
            if old["checks"] != p["checks"] and p["checks"] == "red":
                out.append(f"أحمر {tag}")
            if old["checks"] != p["checks"] and p["checks"] == "green":
                out.append(f"أخضرُ الآن {tag}" + (" — جاهزٌ للدمج" if p["approval"] or p["exempt"] else " — لكن بلا سطر اعتماد"))
            if old["merge"] != p["merge"] and p["merge"] == "DIRTY":
                out.append(f"تعارضٌ مع main {tag}")
        if p["draft"]:
            continue
        age = _age(p["created"], now)
        if not (p["approval"] or p["exempt"]) and age > NO_APPROVAL_MIN and not throttled((n, "approval")):
            out.append(f"بلا سطر اعتماد منذ {int(age)} د {tag}")
        if p["checks"] == "green" and (p["approval"] or p["exempt"]) and p["merge"] in ("CLEAN", "UNSTABLE") \
                and age > GREEN_WAIT_MIN and not throttled((n, "waiting")):
            out.append(f"أخضرٌ ومعتمَدٌ ينتظر الدمج منذ {int(age)} د {tag}")
    for n in sorted(set(prev or {}) - set(cur)):
        out.append(f"لم يعد مفتوحاً #{n} (دُمج أو أُغلق)")
    return out


def pushed_without_pr(items: dict[str, dict], prs_text: list[str], now: datetime) -> list[str]:
    """بطاقاتٌ في pushed منذ أكثر من 15 د لا يذكرها أيُّ طلب: تسليمٌ منسيّ (v2.16: لا pushed إلّا من approved)."""
    lost = []
    for cid, it in items.items():
        if it["state"] == "pushed" and _age(it.get("state_ts") or it["created"], now) > PUSHED_NO_PR_MIN:
            if not any(cid in t for t in prs_text):
                lost.append(cid)
    return lost


def fetch() -> list[dict] | None:
    fields = "number,title,body,isDraft,state,mergeStateStatus,statusCheckRollup,createdAt"
    p = subprocess.run(["gh", "pr", "list", "--state", "all", "--limit", "80", "--json", fields], cwd=REPO,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip() else None


def beat(ok: bool, open_count: int, path: Path = HEARTBEAT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ok": ok, "open": open_count}), encoding="utf-8")


def heartbeat_age(now: datetime, path: Path = HEARTBEAT) -> float | None:
    if not path.is_file():
        return None
    return _age(json.loads(path.read_text(encoding="utf-8"))["ts"], now)


def snapshot(now: datetime) -> tuple[dict[int, dict], list[str], list[str]] | None:
    rows = fetch()
    if rows is None:
        return None
    cur = {p["number"]: normalize(p) for p in rows if p["state"] == "OPEN"}
    lost = pushed_without_pr(ledger.reduce_state(ledger.load_events()), [f"{p['title']}\n{p.get('body') or ''}" for p in rows], now)
    return cur, [], lost


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=120)
    ap.add_argument("--check-heartbeat", action="store_true")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    if args.check_heartbeat:
        age = heartbeat_age(now)
        print("مراقبُ الطلبات: لا نبضةَ قطّ" if age is None else f"مراقبُ الطلبات: آخرُ دورةٍ قبل {int(age)} د")
        return 1 if age is None or age > HEARTBEAT_STALE_MIN else 0
    if args.once:
        snap = snapshot(now)
        if snap is None:
            print("تعذّر gh")
            return 1
        cur, _, lost = snap
        for line in events(None, cur, now, {}):
            print(line)
        for cid in lost:
            print(f"بطاقةٌ pushed بلا طلبٍ يذكرها: {cid}")
        print(f"— {len(cur)} طلباً مفتوحاً")
        return 0
    if not args.loop:
        sys.exit("أعطِ --once أو --loop أو --check-heartbeat")
    prev, alerted, warned_lost, failing = None, {}, set(), False
    while True:
        now = datetime.now(timezone.utc)
        snap = snapshot(now)
        if snap is None:
            beat(False, 0)
            if not failing:
                print("تعذّر gh — أعيد المحاولة (تُطبع مرّةً واحدةً لكلّ انقطاع)", flush=True)
            failing = True
        else:
            failing = False
            cur, _, lost = snap
            if prev is None:
                print(f"بدأت المراقبة — {len(cur)} طلباً مفتوحاً", flush=True)
            for line in events(prev, cur, now, alerted):
                print(line, flush=True)
            for cid in lost:
                if cid not in warned_lost:
                    warned_lost.add(cid)
                    print(f"بطاقةٌ pushed بلا طلبٍ يذكرها: {cid}", flush=True)
            prev = cur
            beat(True, len(cur))
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
