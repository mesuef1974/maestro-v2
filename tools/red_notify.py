#!/usr/bin/env python3
"""إحالةُ الأحمر آلياً (P0-2، أمر المالك 10-16: كلُّ أحمر يُبلَّغ فوراً) — بلا انتظار 0601.

لكلّ طلبٍ مفتوحٍ على sh-school/shschool_mvp، إن ظهر فحصٌ ساقطٌ جديد (فشلٌ حقيقيّ بـpr_red.classify لا إلغاءٌ بديلُه أحدث)
تُطبع رسالةٌ واحدةٌ لحامل البطاقة (من الدفتر) ورسالةٌ لـ0101، باسم الفحص والرأس. لا دمجَ ولا دفعَ ولا تعديلَ في المستودع: قراءةُ gh والدفتر فقط.

القيد: لا قناةَ يرسل بها سكربتٌ إلى جلسة Claude Desktop؛ فالأداةُ تكشف وتمنع التكرارَ وتحلّ المستلمَ وتسجّل في msg_counter،
وتطبع سطراً لكلّ رسالة (الإرسالُ نفسُه أداةُ SendMessage في الجلسة التي تشغّلها بـMonitor، فيصلها كلُّ سطرٍ فوراً).

    python red_notify.py --once [--dry-run]         دورةٌ واحدة
    python red_notify.py --loop [--interval 300]    للمراقبة بأداة Monitor

سطرُ الخرج (مفصولٌ بـTab):  إحالة <رقم المستلم> <معرّف الجلسة أو —> <نصّ الرسالة>
منعُ التكرار: لا تُعاد رسالةٌ لنفس (طلب، فحص) قبل 15 دقيقة، ولا لنفس الرأس مرّتين؛ والرأسُ الجديد يُعلن (بعد المهلة).
الحالة: ledger/red_notify_state.json.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import ledger  # noqa: E402
import pr_red  # noqa: E402
import pr_watch  # noqa: E402

STATE_FILE = ROOT / "ledger" / "red_notify_state.json"
COUNTER = Path("C:/Users/mesue/delivery_manager_work/tools/msg_counter.py")
SENDER = "0702"
ALWAYS = "0101"
REPEAT_MIN = 15
KEEP_H = 24  # مدّةُ تذكّر (طلب، فحص) كي لا يتكرّر تذبذبُ أحمر←أخضر←أحمر
CARD_RE = re.compile(r"W-\d{8}-\d{3}")
FIELDS = "number,title,body,isDraft,state,headRefName,headRefOid,statusCheckRollup"


def failed_checks(pr: dict) -> list[str]:
    """أسماءُ الفحوص الساقطة فعلاً (آخرُ تشغيلٍ لكلّ اسم)، مرتّبة."""
    return sorted(
        {
            c.get("name") or c.get("context") or "؟"
            for c in pr_red.classify(pr.get("statusCheckRollup"))["failed"]
        }
    )


def holder_of(pr: dict, items: dict) -> tuple[str | None, str | None]:
    """(رقم الحامل، رمز البطاقة) من الدفتر؛ None للحامل إن لم يُعرف."""
    text = f"{pr.get('title', '')}\n{pr.get('body') or ''}\n{pr.get('headRefName', '')}"
    for cid in CARD_RE.findall(text):
        h = (items.get(cid) or {}).get("held_by")
        if h and h != "-":
            return str(h), cid
    cids = CARD_RE.findall(text)
    return None, (cids[0] if cids else None)


def fresh_failures(prs: list[dict], state: dict, now: datetime) -> list[dict]:
    """الفحوصُ الساقطةُ الجديدةُ فقط: (طلب، فحص) بلا سجلّ، أو برأسٍ جديد، وفاتت مهلةُ التكرار منذ آخر إعلانٍ له. يعدّل state في مكانه."""
    out = []
    for pr in prs:
        if pr.get("state") != "OPEN" or pr.get("isDraft"):
            continue
        head = (pr.get("headRefOid") or "")[:8]
        for name in failed_checks(pr):
            key = f"{pr['number']}|{name}"
            rec = state.get(key)
            if rec and rec["head"] == head:
                continue  # نفسُه على نفس الرأس: أُعلن
            if rec and now - datetime.fromisoformat(rec["at"]) < timedelta(
                minutes=REPEAT_MIN
            ):
                continue  # تكرارٌ ضمن المهلة
            state[key] = {"head": head, "at": now.isoformat(timespec="seconds")}
            out.append({"pr": pr, "check": name, "head": head})
    cutoff = now - timedelta(hours=KEEP_H)
    for k in [k for k, v in state.items() if datetime.fromisoformat(v["at"]) < cutoff]:
        del state[k]
    return out


ANSI = re.compile(
    "(?:\x1b|\\^\\[)\\[[0-9;]*m"
)  # رمزُ التلوين الحقيقيّ أو نسخته المطبوعة بـ^[[
SUMMARY = (
    "Security Summary",
    "ملخص بوابة الجودة",
)  # فحوصٌ تجميعيّةٌ تتبع غيرَها: تُذكر ولا يُقرأ سجلُّها


def _detail(pr: dict, name: str, err) -> str:
    """أوّلُ سطر خطأ من سجلّ الفحص؛ فارغٌ إن تعذّر أو كان الفحصُ تجميعيّاً."""
    if not err or name in SUMMARY:
        return ""
    try:
        chk = next(
            (
                c
                for c in pr_red.classify(pr.get("statusCheckRollup"))["failed"]
                if (c.get("name") or c.get("context")) == name
            ),
            {},
        )
        line = ANSI.sub("", err(chk)).strip()
        return "" if line.startswith("echo ") else line
    except Exception:  # noqa: BLE001 — السجلُّ اختياريّ
        return ""


def messages(
    fresh: list[dict], items: dict, directory: dict, err=None
) -> list[tuple[str, str, str]]:
    """(رقم المستلم، معرّفه أو «—»، النصّ): رسالةٌ واحدةٌ لكلّ طلب تضمّ فحوصَه الساقطة الجديدة، للحامل ثم لـ0101 (مرّةً إن كان الحاملَ نفسَه)."""
    by_pr: dict[int, list[dict]] = {}
    for f in fresh:
        by_pr.setdefault(f["pr"]["number"], []).append(f)
    out = []
    for group in by_pr.values():
        pr = group[0]["pr"]
        holder, cid = holder_of(pr, items)
        parts = []
        for f in group:
            d = _detail(pr, f["check"], err)
            parts.append(f"«{f['check']}»" + (f" ({d})" if d else ""))
        ref = f"#{pr['number']}" + (f" ({cid})" if cid else "")
        base = (
            f"{ref}: فحصٌ ساقطٌ جديد على الرأس {group[0]['head']}: "
            + "؛ ".join(parts)
            + f" — {pr['title'][:60]}"
        )
        targets = [holder] if holder else []
        if ALWAYS not in targets:
            targets.append(ALWAYS)
        for t_ in targets:
            note = base
            if t_ == ALWAYS and holder is None:
                note += " (حاملُ البطاقة غيرُ معروفٍ في الدفتر)"
            elif t_ == ALWAYS and holder != ALWAYS:
                note += f" (الحامل {holder})"
            out.append((t_, (directory.get(t_) or {}).get("id", "—"), note))
    return out


def load_state(path: Path | None = None) -> dict:
    path = path or STATE_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        return {}


def save_state(state: dict, path: Path | None = None) -> None:
    path = path or STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def fetch_open() -> list[dict] | None:
    p = pr_watch._run_gh(
        ["pr", "list", "--state", "open", "--limit", "40", "--json", FIELDS]
    )
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout)
    except ValueError:
        return None


def count_messages(n: int) -> None:
    """تسجيلٌ في msg_counter باسم المرسِل (الجلسةُ التي تُرسل فعلاً)؛ يتخطّى بصمتٍ إن لم يوجد العدّاد."""
    if n and COUNTER.is_file():
        cmd = [sys.executable, str(COUNTER), "add", SENDER, str(n)]
        subprocess.run(cmd, capture_output=True, check=False)  # noqa: S603


def cycle(
    now: datetime,
    dry_run: bool = False,
    prs: list[dict] | None = None,
    items: dict | None = None,
    directory: dict | None = None,
    err=pr_red.first_error,
) -> list[tuple[str, str, str]] | None:
    prs = fetch_open() if prs is None else prs
    if prs is None:
        return None  # غيرُ مقيس: لا نطبع «لا جديد»
    if items is None:
        items = ledger.reduce_state(ledger.load_events(ledger.ledger_path()))
    if directory is None:
        import session_directory

        directory = session_directory.entries()
    state = load_state()
    fresh = fresh_failures(prs, state, now)
    msgs = messages(fresh, items, directory, err)
    if not dry_run:
        save_state(state)
        count_messages(len(msgs))
    return msgs


def emit(msgs: list[tuple[str, str, str]]) -> None:
    for to, sid, text in msgs:
        print(f"إحالة\t{to}\t{sid}\t{text}", flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=300)
    ap.add_argument(
        "--dry-run", action="store_true", help="لا يحفظ الحالةَ ولا يسجّل في msg_counter"
    )
    args = ap.parse_args(argv)
    if not (args.once or args.loop):
        ap.error("اختر --once أو --loop")
    while True:
        msgs = cycle(datetime.now(UTC), args.dry_run)
        if msgs is None:
            print("تعذّر gh — أعيد المحاولة (غير مقيس)", file=sys.stderr, flush=True)
        else:
            emit(msgs)
        if args.once:
            return 0 if msgs is not None else 1
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
