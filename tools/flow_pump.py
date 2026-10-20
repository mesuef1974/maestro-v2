#!/usr/bin/env python3
"""مضخّةُ التدفّق (تكليف المالك 2026-10-20: حلٌّ جذريّ لتأخّر حلقة الاعتماد←الدفع←الدمج←النشر) — عرضٌ افتراضيّاً و`--apply` للنقل.

تنقل البطاقاتِ آليّاً متى ثبت شرطُها **من المصدر** لا من رسائل الجلسات:
  1. جاهز للمعاينة ← approved: الرأس المعلَن في آخر مذكّرة «جاهزٌ للمعاينة بالرأس <sha8>» يثبت اعتمادُه (approval_check ✔ برمز 0).
     الدفترُ نفسُه يرفض ما لا يستوفي بوّاباتِه (أدلّة بصريّة، مواصفة) فيُبلَّغ ولا يُفرض.
  2. approved/pushed/merged ← published: ledger_sync (طلبٌ مدموج بالرأس نفسه).
لا تدفع ولا تدمج ولا ترسل. تُبلَّغ البطاقاتُ العالقة نصّاً مجمَّعاً (للمهمّة المجدولة) بدل رسائلَ بين جلسات.

    python flow_pump.py               # عرض
    python flow_pump.py --apply       # ينقل ويطبع الإبلاغ
    python flow_pump.py --apply --skip W-20261001-006   # يستثني بطاقاتٍ من مرحلة النشر
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ledger  # noqa: E402
import ledger_sync  # noqa: E402

HEAD_RE = re.compile(r"(?:بالرأس|للرأس|الرأس)\s+([0-9a-f]{8,40})")
SENDER = "0101"


def ready_head(item: dict) -> str | None:
    """آخر رأسٍ أُعلن في مذكّرات البطاقة."""
    for note in reversed(item.get("notes") or []):
        m = HEAD_RE.search(note.get("text", ""))
        if m:
            return m.group(1)[:8]
    return None


def approval_ok(card: str, head: str) -> bool:
    p = subprocess.run(
        [sys.executable, str(HERE / "approval_check.py"), "card", card, "--head", head],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return p.returncode == 0


def approve_pass(states: dict[str, dict], apply: bool) -> list[str]:
    out: list[str] = []
    for cid, item in sorted(states.items()):
        if item.get("state") != "ready_for_review":
            continue
        head = ready_head(item)
        if not head:
            out.append(f"{cid}: بلا رأسٍ معلَن في المذكّرات — لا نقل")
            continue
        if not approval_ok(cid, head):
            out.append(f"{cid}: رأس {head} بلا اعتمادٍ ثابت (أو ينقصه دليلٌ بصريّ) — ينتظر")
            continue
        if not apply:
            out.append(f"{cid}: رأس {head} معتمَد ← approved (عرض)")
            continue
        p = subprocess.run(
            [
                sys.executable, str(HERE / "ledger.py"), "move", cid, "approved",
                "--by", SENDER, "--head", head,
                "--note", f"اعتمادٌ آليّ من المصدر: approval_check ✔ بالرأس {head} (مضخّة التدفّق)",
            ],
            capture_output=True, encoding="utf-8", errors="replace",
        )
        tail = (p.stdout + p.stderr).strip().splitlines()[-1:] or [""]
        out.append(f"{cid}: رأس {head} ← approved: {'✔' if p.returncode == 0 else '✘ ' + tail[0][:160]}")
    return out


LOCK = HERE.parent / "ledger" / "flow_pump.lock"
LOG = HERE.parent / "ledger" / "flow_pump.log"
STALE_LOCK_S = 900


def _lock() -> bool:
    """قفلٌ بملفّ: دورتان لا تتداخلان؛ القفلُ الأقدم من 15 دقيقة يُعدّ ميتاً."""
    import os
    import time

    try:
        if LOCK.exists() and time.time() - LOCK.stat().st_mtime > STALE_LOCK_S:
            LOCK.unlink()
        os.close(os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except FileExistsError:
        return False


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not _lock():
        print("دورةٌ أخرى تعمل — تخطٍّ")
        return 0
    try:
        return _run(argv)
    finally:
        LOCK.unlink(missing_ok=True)


def _run(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--skip", nargs="*", default=[], help="بطاقاتٌ تُستثنى من النقل")
    a = ap.parse_args(argv)

    states = ledger.reduce_state(ledger.load_events())
    for line in approve_pass({k: v for k, v in states.items() if k not in a.skip}, a.apply):
        print("اعتماد: " + line)
    print("— مرحلة النشر (ledger_sync) —")
    if a.skip:
        orig = ledger_sync.plan
        ledger_sync.plan = lambda st, *r, **k: orig({c: v for c, v in st.items() if c not in a.skip}, *r, **k)
    orig_move = ledger.move  # ledger_sync لا يمرّر by؛ يسجّلها المضخّة باسم 0101 (مسجِّلٌ مسموح لـmerged/published)
    ledger.move = lambda *args, **kw: orig_move(*args, **{"by": SENDER, **kw})
    rc = ledger_sync.cycle(a.apply, 80)
    if a.apply:
        from datetime import datetime

        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} rc={rc}\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
