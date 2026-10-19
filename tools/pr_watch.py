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
import publish_sync  # noqa: E402

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


GH_RETRY_DELAYS = (5, 15)  # ثانيتان فاصلتان بين المحاولات: أعطالُ GitHub المؤقّتة (504) لا تُعلَن إنذاراً كاذباً
STATE_FILE = ROOT / "ledger" / "pr_watch_state.json"


def _run_gh(args: list[str], sleep=time.sleep) -> subprocess.CompletedProcess:
    """يشغّل gh مع إعادةِ المحاولة عند الفشل؛ يعيد آخرَ نتيجة (فاشلةً أو ناجحة)."""
    p = None
    for attempt in range(len(GH_RETRY_DELAYS) + 1):
        p = subprocess.run(["gh", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if p.returncode == 0:
            return p
        if attempt < len(GH_RETRY_DELAYS):
            sleep(GH_RETRY_DELAYS[attempt])
    return p


def fetch() -> list[dict] | None:
    fields = "number,title,body,isDraft,state,mergeStateStatus,statusCheckRollup,createdAt"
    p = _run_gh(["pr", "list", "--state", "all", "--limit", "40", "--json", fields])  # 80 كان يُسقط GraphQL بـ504
    return json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip() else None


def save_state(prev: dict | None, ops_state: dict, alerted: dict, ops_alerted: dict, path: Path = STATE_FILE) -> None:
    """حالةُ دورةٍ مجدولة بين التشغيلات: آخرُ لقطة PR، وحالةُ الطابور والإنتاج، وساعاتُ التكرار."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "prev": {str(k): v for k, v in (prev or {}).items()},
        "ops": ops_state,
        "alerted": [[list(k), v.isoformat()] for k, v in alerted.items()],
        "ops_alerted": [[list(k), v.isoformat()] for k, v in ops_alerted.items()],
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def load_state(path: Path = STATE_FILE):
    """يعيد (prev, ops_state, alerted, ops_alerted)؛ الملفُ الغائبُ أو المعطوبُ = بدايةٌ جديدة (يُعلَن ولا يُخمَّن)."""
    if not path.is_file():
        return None, {}, {}, {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        prev = {int(k): v for k, v in data["prev"].items()} if data.get("prev") is not None else None
        ops = data.get("ops", {})
        if "queue" in ops:
            ops["queue"] = {int(k): v for k, v in ops["queue"].items()}
        alerted = {tuple(k): datetime.fromisoformat(v) for k, v in data.get("alerted", [])}
        ops_alerted = {tuple(k): datetime.fromisoformat(v) for k, v in data.get("ops_alerted", [])}
        return prev, ops, alerted, ops_alerted
    except (ValueError, KeyError, TypeError) as exc:
        print(f"تعذّر قراءةُ حالة المراقبة ({exc}) — أبدأ من جديد", file=sys.stderr)
        return None, {}, {}, {}


def beat(ok: bool, open_count: int, path: Path = HEARTBEAT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ok": ok, "open": open_count}), encoding="utf-8")


def heartbeat_age(now: datetime, path: Path = HEARTBEAT) -> float | None:
    if not path.is_file():
        return None
    return _age(json.loads(path.read_text(encoding="utf-8"))["ts"], now)


def heartbeat_ok(path: Path = HEARTBEAT) -> bool:
    """آخرُ دورةٍ نجحت؟ الدورةُ الفاشلةُ حديثةٌ لكنها ليست سليمة، فلا تُخفيها نبضتُها الطازجة."""
    return path.is_file() and bool(json.loads(path.read_text(encoding="utf-8")).get("ok"))


MAIN_RED_NAMES_SKIP = ()  # أسماءٌ تُستثنى من إنذار main (فارغ: كلُّ تشغيلٍ على main يُفحص)
QUEUE_QUERY = (
    'query{repository(owner:"sh-school",name:"shschool_mvp"){mergeQueue(branch:"main")'
    "{entries(first:50){nodes{position state pullRequest{number}}}}}}"
)
PROD_LAG_MIN = 30


def _gh_json(args: list[str]):
    """نتيجةُ gh كـJSON، أو None عند الفشل (يُعلن المستدعي ولا يُخمِّن)."""
    p = _run_gh(args)
    if p.returncode != 0 or not p.stdout.strip():
        return None
    return json.loads(p.stdout)


def _gh_raw(args: list[str]) -> str | None:
    """نصُّ مخرجات gh (لا JSON، مثل `-q .status`)، أو None عند الفشل أو الفراغ."""
    p = _run_gh(args)
    text = p.stdout.strip()
    return text if p.returncode == 0 and text else None


def queue_map(nodes: list[dict]) -> dict[int, str]:
    """رقمُ الطلب ← حالتُه في طابور الدمج."""
    return {n["pullRequest"]["number"]: n["state"] for n in nodes}


def queue_events(prev: dict[int, str] | None, nodes: list[dict]) -> list[str]:
    """أحداثُ طابور الدمج بين دورتين: دخولٌ، أو تغيُّرُ حالة، أو خروج. لا تُحكم على الحالات بأسمائها."""
    cur = queue_map(nodes)
    pos = {n["pullRequest"]["number"]: n["position"] for n in nodes}
    out: list[str] = []
    for num in sorted(cur):
        if prev is None or num not in prev:
            out.append(f"طابور الدمج: #{num} دخل في الموقع {pos[num]} (الحالة {cur[num]})")
        elif prev[num] != cur[num]:
            out.append(f"طابور الدمج: #{num} تغيّرت حالتُه من {prev[num]} إلى {cur[num]}")
    for num in sorted(set(prev or {}) - set(cur)):
        out.append(f"طابور الدمج: #{num} غادر الطابور (دُمج أو أُخرج)")
    return out


def main_red_events(runs: list[dict], main_head: str) -> list[str]:
    """أحمرُ main: آخرُ تشغيلٍ مكتمل لكلّ فحصٍ على رأس main نفسه، إن كان فشلاً حقيقيّاً (لا ملغىً)."""
    latest: dict[str, dict] = {}
    for r in runs:
        if r.get("status") != "completed" or r.get("headSha", "")[:8] != main_head[:8]:
            continue
        latest.setdefault(r["name"], r)
    out = []
    for name, r in sorted(latest.items()):
        if name in MAIN_RED_NAMES_SKIP:
            continue
        if r.get("conclusion") == "failure":
            out.append(f"أحمرُ main: «{name}» فشل على {main_head[:8]} (التشغيل {r['databaseId']})")
    return out


def prod_lag_events(prod: str | None, err: str | None, status: str | None, state: dict, now: datetime) -> list[str]:
    """نشرُ الإنتاج: عطلُ /health/، أو تأخّرُ الإنتاج عن main أكثرَ من PROD_LAG_MIN دقيقة.

    `status` = حالةُ compare من الإنتاج إلى main: ahead يعني أنّ main أمامه (الإنتاج متأخّر)."""
    out: list[str] = []
    if err:
        out.append(f"نشرُ الإنتاج: {err}")
    if status == "ahead":
        since = state.setdefault("lag_since", now.isoformat(timespec="seconds"))
        mins = int(_age(since, now))
        if mins >= PROD_LAG_MIN:
            out.append(f"الإنتاج {prod[:7] if prod else '?'} متأخّرٌ عن main منذ {mins} د")
    elif status is not None:
        state.pop("lag_since", None)
    if status == "diverged":
        out.append(f"الإنتاج {prod[:7] if prod else '?'} متفرّعٌ عن main (diverged) — يحتاج تدخّلاً")
    return out


def ops_lines(now: datetime, state: dict, alerted: dict[tuple, datetime]) -> list[str]:
    """فحوصُ الطابور والإنتاج وأحمرِ main؛ كلُّ خطأٍ شبكيٍّ يُعلن ولا يُخمَّن، والتكرارُ يُكبح بالساعة."""
    out: list[str] = []

    def throttled(key: tuple) -> bool:
        last = alerted.get(key)
        if last and (now - last) < timedelta(minutes=REPEAT_MIN):
            return True
        alerted[key] = now
        return False

    nodes = _gh_json(["api", "graphql", "-f", f"query={QUEUE_QUERY}"])
    if nodes is None:
        if not throttled(("queue", "err")):
            out.append("تعذّر قراءةُ طابور الدمج (gh) — لا أعرف حالتَه الآن")
    else:
        entries = nodes["data"]["repository"]["mergeQueue"]["entries"]["nodes"]
        out += queue_events(state.get("queue"), entries)
        state["queue"] = queue_map(entries)

    main_head = _gh_raw(["api", "repos/sh-school/shschool_mvp/git/ref/heads/main", "-q", ".object.sha"])

    runs = _gh_json(["run", "list", "--branch", "main", "--limit", "20", "--json",
                     "databaseId,name,conclusion,headSha,status"])
    if runs is None or main_head is None:
        if not throttled(("main", "err")):
            out.append("تعذّر قراءةُ تشغيلات main (gh) — لا أعرف حالتَها الآن")
    else:
        for line in main_red_events(runs, main_head):
            if not throttled(("main", line)):
                out.append(line)

    try:
        prod, err = publish_sync.fetch_health(), None
    except publish_sync.SyncError as exc:
        prod, err = None, str(exc)
    status = None
    if prod and main_head:
        status = _gh_raw(["api", f"repos/sh-school/shschool_mvp/compare/{prod}...{main_head}", "-q", ".status"])
    for line in prod_lag_events(prod, err, status, state, now):
        if not throttled(("prod", line)):
            out.append(line)
    return out


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
        ok = heartbeat_ok()
        if age is None:
            print("مراقبُ الطلبات: لا نبضةَ قطّ")
        elif not ok:
            print(f"مراقبُ الطلبات: آخرُ دورةٍ قبل {int(age)} د فشلت (تعذّر gh)")
        else:
            print(f"مراقبُ الطلبات: آخرُ دورةٍ قبل {int(age)} د")
        return 1 if age is None or age > HEARTBEAT_STALE_MIN or not ok else 0
    if args.once:
        # وضعُ الجدولة: حالةٌ محفوظة بين التشغيلات، فلا يُعاد إعلانُ ما أُعلن، ونبضةٌ لكلّ تشغيل
        prev, ops_state, alerted, ops_alerted = load_state()
        snap = snapshot(now)
        if snap is None:
            beat(False, 0)
            print("تعذّر gh بعد إعادات المحاولة")
            return 1
        cur, _, lost = snap
        for line in events(prev, cur, now, alerted):
            print(line)
        for line in ops_lines(now, ops_state, ops_alerted):
            print(line)
        for cid in lost:
            print(f"بطاقةٌ pushed بلا طلبٍ يذكرها: {cid}")
        save_state(cur, ops_state, alerted, ops_alerted)
        beat(True, len(cur))
        print(f"— {len(cur)} طلباً مفتوحاً")
        return 0
    if not args.loop:
        sys.exit("أعطِ --once أو --loop أو --check-heartbeat")
    prev, alerted, warned_lost, failing = None, {}, set(), False
    ops_state, ops_alerted = {}, {}
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
            for line in ops_lines(now, ops_state, ops_alerted):
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
