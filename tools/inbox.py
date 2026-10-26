#!/usr/bin/env python3
"""صندوقُ واردٍ لكلّ جلسة (W-20261026-015): المحتوى يُنقل بملفٍّ لا برسالةٍ، فلا يُستهلك حدُّ التطبيق (عشرُ رسائلَ منذ آخر رسالةٍ للمالك)
في نقل المحتوى؛ والرسالةُ الحيّة تبقى للإيقاظ وحدَه.

    python inbox.py send --to 0301 --from 0101 --text "…"        # أو --file مسار
    python inbox.py read 0301 [--peek]                            # الواردُ غيرُ المسلَّم (ويُسلَّم ما لم يكن --peek)
    python inbox.py pending                                       # الأرقامُ التي لها وارد غيرُ مسلَّم وعددُه
    python inbox.py hook                                          # خطّاف PostToolUse (JSON على stdin): يحقن الواردَ في سياق الجلسة العاملة

الملف: ledger/inbox/<رقم>.jsonl يُلحَق فقط: {"k":"msg"} للرسالة و{"k":"ack"} للتسليم و{"k":"block"} لمنع الإنهاء مرّةً لكلّ دفعة.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOHA = timezone(timedelta(hours=3))
NUM = re.compile(r"^\d{4}(?:-[ء-ي])?$")
MAX_TEXT = 6000  # أكبرُ نصٍّ للرسالة الواحدة؛ الأطولُ ملفٌّ في handover_notes ويُرسَل مساره
SHOW_MAX = 8  # أكثرُ ما يُحقن في دفعةٍ واحدة؛ الباقي يبقى معلَّقاً للدفعة التالية


def _dir(root: Path | None) -> Path:
    return (root or ROOT) / "ledger" / "inbox"


def _path(num: str, root: Path | None = None) -> Path:
    if not NUM.match(num):
        raise ValueError(f"رقمُ جلسةٍ غيرُ صالح: {num}")
    return _dir(root) / f"{num}.jsonl"


def _now() -> str:
    return datetime.now(DOHA).isoformat(timespec="seconds")


def _rows(num: str, root: Path | None = None) -> list[dict]:
    p = _path(num, root)
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("k") in ("msg", "ack", "block"):
            out.append(d)
    return out


def _append(num: str, row: dict, root: Path | None = None) -> None:
    p = _path(num, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def send(to: str, frm: str, text: str, root: Path | None = None) -> int:
    """يلحق رسالةً بصندوق `to` ويعيد رقمَها. يرفض الفارغ والأطول من MAX_TEXT ومرسِلاً غيرَ صالح."""
    text = (text or "").strip()
    if not text:
        raise ValueError("نصٌّ فارغ")
    if len(text) > MAX_TEXT:
        raise ValueError(f"النصُّ {len(text)} حرفاً (الحدّ {MAX_TEXT}): اكتبه ملفّاً في handover_notes وأرسل مساره")
    if not NUM.match(frm):
        raise ValueError(f"مرسِلٌ غيرُ صالح: {frm}")
    n = max([r["id"] for r in _rows(to, root) if r["k"] == "msg"] or [0]) + 1
    _append(to, {"k": "msg", "id": n, "ts": _now(), "from": frm, "text": text}, root)
    return n


def pending(num: str, root: Path | None = None) -> list[dict]:
    """رسائلُ الصندوق غيرُ المسلَّمة بترتيب وصولها."""
    rows = _rows(num, root)
    acked = {r["id"] for r in rows if r["k"] == "ack"}
    return [r for r in rows if r["k"] == "msg" and r["id"] not in acked]


def pending_nums(root: Path | None = None) -> dict[str, int]:
    """{الرقم: عددُ غيرِ المسلَّم} لكلّ صندوقٍ فيه واردٌ معلَّق (يقرؤه الكنّاسُ للجرس)."""
    out: dict[str, int] = {}
    d = _dir(root)
    for f in sorted(d.glob("*.jsonl")) if d.exists() else []:
        if NUM.match(f.stem) and (n := len(pending(f.stem, root))):
            out[f.stem] = n
    return out


def ack(num: str, ids: list[int], root: Path | None = None) -> None:
    for i in ids:
        _append(num, {"k": "ack", "id": i, "ts": _now()}, root)


def render(msgs: list[dict]) -> str:
    return "\n".join(f"[وارد #{m['id']} من {m['from']} {m['ts'][11:16]}] {m['text']}" for m in msgs)


def read(num: str, mark: bool = True, root: Path | None = None) -> list[dict]:
    msgs = pending(num, root)[:SHOW_MAX]
    if mark and msgs:
        ack(num, [m["id"] for m in msgs], root)
    return msgs


def claim_block(num: str, root: Path | None = None) -> list[dict]:
    """لمنع الإنهاء مرّةً لكلّ دفعة: إن وُجد واردٌ غيرُ مسلَّم لم يُمنَع الإنهاءُ بسببه من قبلُ فيُسلَّم ويُسجَّل المنعُ ويُعاد؛
    وإلا يعاد فارغاً (فلا حلقةَ منعٍ لا تنتهي). الجلسةُ ترى المحتوى في سبب المنع نفسه."""
    msgs = pending(num, root)
    blocked = max([r["upto"] for r in _rows(num, root) if r["k"] == "block"] or [0])
    batch = [m for m in msgs if m["id"] > blocked][:SHOW_MAX]
    if not batch:
        return []
    ack(num, [m["id"] for m in batch], root)
    _append(num, {"k": "block", "upto": max(m["id"] for m in batch), "ts": _now()}, root)
    return batch


def hook(raw: str, root: Path | None = None, resolve=None) -> str:
    """PostToolUse: يعيد JSON لـadditionalContext فيه الواردُ (ويُسلِّمه) أو سلسلةً فارغة. لا يرفع استثناءً."""
    try:
        payload = json.loads(raw or "{}")
        if resolve is None:
            import msg_counter

            resolve = msg_counter.sender_num
        num = resolve(payload)
        if not num or not isinstance(payload, dict):
            return ""
        msgs = read(num, True, root)
        if not msgs:
            return ""
        more = len(pending(num, root))
        text = "رسائلُ واردةٌ في صندوقك (تُنقل بملفٍّ لا تستهلك حدَّ الرسائل):\n" + render(msgs)
        if more:
            text += f"\n(+{more} أخرى معلَّقة: python tools/inbox.py read {num})"
        return json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}, ensure_ascii=False)
    except Exception:  # noqa: BLE001 — الخطّاف لا يُسقط الجلسة
        return ""


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send")
    s.add_argument("--to", required=True)
    s.add_argument("--from", dest="frm", required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--text")
    g.add_argument("--file")
    r = sub.add_parser("read")
    r.add_argument("num")
    r.add_argument("--peek", action="store_true")
    sub.add_parser("pending")
    sub.add_parser("hook")
    a = ap.parse_args(argv)
    if a.cmd == "send":
        text = a.text if a.text is not None else Path(a.file).read_text(encoding="utf-8")
        try:
            print(f"أُلحقت #{send(a.to, a.frm, text)} بصندوق {a.to}")
        except ValueError as e:
            print(f"رُفض: {e}", file=sys.stderr)
            return 3
        return 0
    if a.cmd == "read":
        msgs = read(a.num, not a.peek)
        print(render(msgs) if msgs else "لا وارد")
        return 0
    if a.cmd == "pending":
        nums = pending_nums()
        print("\n".join(f"{k}: {v}" for k, v in nums.items()) if nums else "لا وارد معلَّق")
        return 0
    out = hook(sys.stdin.read())
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
