#!/usr/bin/env python3
"""سجلّ الجلسة قبل المسح (D-510م، W-20261101-012) — امتدادٌ لـ session_state.

لكلّ جلسةٍ ثابتةٍ ملفٌّ `ledger/session_records/<رقم>.json` بستّة حقول يكتبها النموذجُ (لا يشتقّها الدفتر):
next_step (الخطوة التالية بدقّة)، tried_failed (ما جُرّب وفشل)، decisions (قرارات التصميم المحلّيّة)،
promises (الوعود المعلّقة)، work_set (فرع/رأس/غير مودَع/تثبيت 8500)، summary (آخر ملخّص ضغط).
ويحمل ختماً (رأس git، حالة بطاقاتها، آخر رقمِ رسالة وارد) وقت آخر تحديث.

الضمان الصارم، في تجربة أسبوع على TRIAL وحدَها (0501 و0601؛ التعميم بأمر المالك):
  - check(): يتغيّر الرأس أو حالةُ بطاقةٍ أو تصلُ رسالةٌ بعد الختم ⇒ مخالفات (خطّاف Stop يرفض إنهاء الدور).
  - clear_issues(): لا مسحَ بسجلٍّ أقدمَ من آخر فعلٍ للجلسة في الدفتر.
كلُّ رفضٍ يُسجَّل في refusals.jsonl ليُقاس ما كان سيضيع.

    python tools/session_record.py set <رقم> --next "…" [--failed "…"] [--decision "…"] [--promise "…"] [--summary "…"] [--cwd <شجرة>]
    python tools/session_record.py show <رقم>
    python tools/session_record.py check <رقم> [--cwd <شجرة>]
    python tools/session_record.py report
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DOHA = timezone(timedelta(hours=3))
ROOT = Path(__file__).resolve().parent.parent
#: تجربةُ الأسبوع (D-510م): الجلساتُ الثابتة التي يُفرض عليها الضمان؛ ما عداها لا يُرفض لها دورٌ ولا مسح.
TRIAL = ("0501", "0601")
LIST_FIELDS = ("tried_failed", "decisions", "promises")
LIST_MAX = 12
ITEM_MAX = 400
NUM_RE = re.compile(r"\d{4}(?:-[ء-ي])?")


def _now() -> datetime:
    return datetime.now(DOHA)


def _fmt(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat(timespec="seconds")


def main_root(root: Path | None = None) -> Path:
    return Path(root) if root else ROOT


def records_dir(root: Path | None = None) -> Path:
    return main_root(root) / "ledger" / "session_records"


def record_path(num: str, root: Path | None = None) -> Path:
    return records_dir(root) / f"{num}.json"


def load(num: str, root: Path | None = None) -> dict | None:
    try:
        d = json.loads(record_path(num, root).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def git_head(cwd: str | None) -> str:
    """الرأسُ القصير للشجرة؛ "" إن تعذّر."""
    if not cwd:
        return ""
    try:
        return subprocess.run(["git", "-C", cwd, "rev-parse", "--short", "HEAD"], capture_output=True, text=True,  # noqa: S603,S607 — أمرٌ ثابت
                              encoding="utf-8", timeout=15, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def work_set(cwd: str | None) -> dict:
    """مجموعةُ العمل: فرع/رأس/غير مودَع (التثبيتُ على 8500 تكتبه الجلسةُ حين يُسأل عنه)."""
    if not cwd:
        return {}
    try:
        def run(*a):
            return subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True, encoding="utf-8", timeout=15, check=True).stdout.strip()  # noqa: S603,S607 — أمرٌ ثابت

        dirty = len([x for x in run("status", "--porcelain").splitlines() if x.strip()])
        return {"branch": run("rev-parse", "--abbrev-ref", "HEAD"), "head": run("rev-parse", "--short", "HEAD"), "dirty": dirty}
    except Exception:  # noqa: BLE001
        return {}


def held_cards(num: str, root: Path | None = None, ledger_path: Path | None = None) -> dict[str, str]:
    """بطاقاتُ الجلسة الحاجزة وحالاتُها الآن من الدفتر."""
    import ledger

    events = ledger.load_events(ledger_path or (main_root(root) / "ledger" / "events.jsonl"))
    items = ledger.reduce_state(events)
    return {i["id"]: i.get("state", "") for i in items.values()
            if i.get("held_by") == num and i.get("state") not in ledger.RELEASING_STATES}


def last_action_ts(num: str, root: Path | None = None, ledger_path: Path | None = None) -> str:
    """وقتُ آخر فعلٍ للجلسة في الدفتر (حدثُ state بتوقيعها)؛ "" إن لم يوجد."""
    import ledger

    events = ledger.load_events(ledger_path or (main_root(root) / "ledger" / "events.jsonl"))
    for ev in reversed(events):
        if ev.get("kind") == "state" and (ev.get("data") or {}).get("by") == num:
            return str(ev.get("ts", ""))
    return ""


def stamp(num: str, cwd: str | None, root: Path | None = None, ledger_path: Path | None = None) -> dict:
    import inbox

    return {"head": git_head(cwd), "cards": held_cards(num, root, ledger_path), "msg": inbox.last_message_id(num, root)}


def update(num: str, fields: dict, cwd: str | None = None, root: Path | None = None, now: datetime | None = None,
           ledger_path: Path | None = None) -> dict:
    """يكتب السجلَّ كاملاً (idempotent): الحقولُ النصّيّة تُستبدل، والقوائمُ تُلحَق بما سبق مقصوصةً بالحدّ، ثمّ يُختم."""
    if not NUM_RE.fullmatch(num or ""):
        raise ValueError(f"رقمُ جلسةٍ غيرُ صالح: {num!r}")
    cur = load(num, root) or {}
    rec = {"next_step": cur.get("next_step", ""), "summary": cur.get("summary", "")}
    for k in LIST_FIELDS:
        rec[k] = list(cur.get(k) or [])
    for k in ("next_step", "summary"):
        if fields.get(k):
            rec[k] = str(fields[k])[:ITEM_MAX * 2]
    for k in LIST_FIELDS:
        for item in fields.get(k) or []:
            if item and item not in rec[k]:
                rec[k].append(str(item)[:ITEM_MAX])
        rec[k] = rec[k][-LIST_MAX:]
    for item in fields.get("done_promises") or []:  # وعدٌ أُنجز يُسقط
        rec["promises"] = [p for p in rec["promises"] if item not in p]
    rec["work_set"] = work_set(cwd) or cur.get("work_set", {})
    rec["num"] = num
    rec["updated_at"] = _fmt(now or _now())
    rec["stamp"] = stamp(num, cwd, root, ledger_path)
    p = record_path(num, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + chr(10), encoding="utf-8")
    os.replace(tmp, p)
    return rec


def check(num: str, cwd: str | None = None, root: Path | None = None, ledger_path: Path | None = None) -> list[str]:
    """مخالفاتُ السجلّ الآن: غيابُه، أو تغيّرُ الرأس/حالةِ بطاقةٍ/وصولُ رسالةٍ بعد الختم. فارغةٌ = السجلُّ يعكس الواقع."""
    rec = load(num, root)
    if rec is None:
        return [f"لا سجلَّ للجلسة {num}: python tools/session_record.py set {num} --next \"الخطوة التالية\""]
    st = rec.get("stamp") or {}
    now = stamp(num, cwd, root, ledger_path)
    issues = []
    if now["head"] and st.get("head") != now["head"]:
        issues.append(f"تغيّر رأسُ git ({st.get('head') or '—'} ← {now['head']})")
    if (st.get("cards") or {}) != now["cards"]:
        changed = sorted(k for k in set(st.get("cards") or {}) | set(now["cards"]) if (st.get("cards") or {}).get(k) != now["cards"].get(k))
        issues.append("تغيّرت حالةُ بطاقة: " + "،".join(changed[:5]))
    if int(st.get("msg") or 0) < now["msg"]:
        issues.append(f"وصلت رسالةٌ (#{now['msg']}) بعد آخر تحديث")
    return issues


def clear_issues(num: str, cwd: str | None = None, root: Path | None = None, ledger_path: Path | None = None) -> list[str]:
    """مانعُ المسح: لا سجلَّ، أو سجلٌّ أقدمُ من آخر فعلٍ للجلسة، أو لا يعكس الواقع. للجلسات خارج TRIAL فارغ."""
    if num not in TRIAL:
        return []
    rec = load(num, root)
    if rec is None:
        return check(num, cwd, root, ledger_path)
    last = last_action_ts(num, root, ledger_path)
    out = []
    if last and str(rec.get("updated_at", "")) < last:
        out.append(f"سجلُّ الجلسة أقدمُ من آخر فعلٍ لها في الدفتر ({rec.get('updated_at')} < {last})")
    return out + check(num, cwd, root, ledger_path)


def log_refusal(num: str, kind: str, issues: list[str], root: Path | None = None, now: datetime | None = None) -> None:
    """سطرٌ في refusals.jsonl لكلّ رفضٍ (دور أو مسح): أساسُ تقرير الأسبوع. لا يرفع استثناءً."""
    try:
        p = records_dir(root) / "refusals.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": _fmt(now or _now()), "num": num, "kind": kind, "issues": issues[:4]}, ensure_ascii=False) + chr(10))
    except OSError:
        pass


def stop_block(num: str, cwd: str | None, root: Path | None = None, ledger_path: Path | None = None) -> str:
    """نصُّ سبب رفض إنهاء الدور لجلسة التجربة، أو "" (لا رفض: خارج TRIAL أو السجلُّ عاكس)."""
    if num not in TRIAL:
        return ""
    issues = check(num, cwd, root, ledger_path)
    if not issues:
        return ""
    log_refusal(num, "stop", issues, root)
    return ("[سجلّ الجلسة — D-510م] لا تُنهِ الدور قبل تحديث سجلّك: " + "؛ ".join(issues)
            + f". نفّذ: python {main_root(root).as_posix()}/tools/session_record.py set {num} --next \"الخطوة التالية بدقّة\""
            " [--failed …] [--decision …] [--promise …] ثمّ أنهِ.")


def report(root: Path | None = None) -> str:
    """تقريرُ التجربة: عددُ الرفوض لكلّ جلسةٍ ونوع (دور/مسح) وآخرُ سجلٍّ محدَّث."""
    p = records_dir(root) / "refusals.jsonl"
    counts: dict[str, dict[str, int]] = {}
    try:
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            counts.setdefault(d.get("num", "؟"), {}).setdefault(d.get("kind", "؟"), 0)
            counts[d["num"]][d["kind"]] += 1
    except OSError:
        pass
    lines = []
    for n in TRIAL:
        rec = load(n, root)
        c = counts.get(n, {})
        lines.append(f"{n}: رفضُ دور {c.get('stop', 0)}، رفضُ مسح {c.get('clear', 0)}، آخرُ تحديث {rec.get('updated_at') if rec else '—'}")
    return chr(10).join(lines)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set")
    s.add_argument("num")
    s.add_argument("--next", dest="next_step", default="")
    s.add_argument("--failed", action="append", default=[])
    s.add_argument("--decision", action="append", default=[])
    s.add_argument("--promise", action="append", default=[])
    s.add_argument("--done-promise", action="append", default=[])
    s.add_argument("--summary", default="")
    s.add_argument("--cwd", default=os.getcwd())
    for name in ("show", "check"):
        c = sub.add_parser(name)
        c.add_argument("num")
        c.add_argument("--cwd", default=os.getcwd())
    sub.add_parser("report")
    a = ap.parse_args(argv)
    if a.cmd == "set":
        rec = update(a.num, {"next_step": a.next_step, "tried_failed": a.failed, "decisions": a.decision, "promises": a.promise,
                             "done_promises": a.done_promise, "summary": a.summary}, a.cwd)
        print(f"سُجّل سجلُّ {a.num} ({rec['updated_at']})")
        return 0
    if a.cmd == "show":
        rec = load(a.num)
        print(json.dumps(rec, ensure_ascii=False, indent=1) if rec else "لا سجلّ")
        return 0 if rec else 1
    if a.cmd == "check":
        errs = check(a.num, a.cwd)
        print("سليم" if not errs else "فشل: " + "؛ ".join(errs))
        return 0 if not errs else 5
    print(report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
