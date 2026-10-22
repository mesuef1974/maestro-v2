#!/usr/bin/env python3
"""فحصُ سلامة الدفتر — قراءةٌ فقط: يقارن الدفترَ (ledger) وowner_confirmations.md وgit.

    python ledger_integrity_check.py [--all] [--json] [--repo D:/shschool_mvp] [--no-git]

الكشوف (كلٌّ برمزٍ ثابت):
  NO_HEAD         بطاقةٌ approved/pushed بلا approved_head في الدفتر
  NO_CONFIRM      بطاقةٌ approved/pushed لا يذكرها أيُّ سطرٍ في owner_confirmations.md ولا اعتمادَ مسجَّلاً في أحداثها
  UNMERGED_CONFIRM (معلومة، لا تُفشل الفحص) البطاقةُ لا سطرَ لها في ملف هذه الشجرة لكنّ لها سطراً في الشجرة الحيّة (--live-confirmations) لم يدخل main بعد
  CONFIRM_HEAD    سطورُ التأكيد تذكر رؤوساً ليس بينها رأسُ الدفتر
  PUSHED_NO_APPR  بطاقةٌ pushed (أو تالية) لم تمرّ قطّ بـapproved في أحداثها ولا اعتمادَ لها
  BRANCH_MISSING  بطاقةٌ pushed فرعُها المسجَّل غيرُ موجودٍ على البعيد
  HEAD_MISMATCH   رأسُ الدفتر لا يطابق رأسَ الفرع على البعيد
افتراضاً تُفحص البطاقاتُ الحيّة (approved وpushed)؛ `--all` يضيف merged/published/closed
(بطاقاتُ ما قبل v2.23 بلا رأسٍ مشروعاً، فتتوقّع ضجيجاً تاريخيّاً). يخرج 0 نظيفاً و1 عند أيّ كشف.
لا يكتب شيئاً ولا يجلب (fetch)؛ يقرأ البعيد بـgit ls-remote.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LIVE = {"approved", "pushed"}
HISTORIC = {"merged", "published", "closed"}
AFTER_APPROVAL = {"pushed"} | HISTORIC
_CARD = re.compile(r"W-\d{8}-\d{3}")
_HEAD = re.compile(r"(?:@|الرأس\s*)([0-9a-f]{7,40})")


def parse_confirmations(text: str) -> dict[str, set[str]]:
    """بطاقة -> رؤوسُ الأسطر التي تذكرها (مجموعةٌ فارغةٌ = ذُكرت بلا رأس). صفوفُ الجدول فقط."""
    out: dict[str, set[str]] = {}
    for ln in text.splitlines():
        if not ln.startswith("|"):
            continue
        heads = {h.lower() for h in _HEAD.findall(ln)}
        for card in _CARD.findall(ln):
            out.setdefault(card, set()).update(heads)
    return out


def ever_approved(events: list[dict]) -> set[str]:
    return {e["id"] for e in events if e.get("kind") == "state" and (e.get("data") or {}).get("state") == "approved"}


def _same(a: str, b: str) -> bool:
    a, b = a.lower(), b.lower()
    return bool(a and b) and (a.startswith(b) or b.startswith(a))


def remote_head(branch: str, repo: str | None) -> str | None:
    p = subprocess.run(["git", "ls-remote", "origin", f"refs/heads/{branch}"], cwd=repo, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise OSError(p.stderr.strip()[:120] or "git ls-remote فشل")
    return p.stdout.split()[0] if p.stdout.strip() else None


def check(events: list[dict], confirmations: dict[str, set[str]], lookup=None, include_history: bool = False,
          live_confirmations: dict[str, set[str]] | None = None) -> list[dict]:
    items = ledger.reduce_state(events)
    approved_once = ever_approved(events)
    scope = LIVE | (HISTORIC if include_history else set())
    found: list[dict] = []

    def add(code: str, item: dict, msg: str) -> None:
        found.append({"code": code, "id": item["id"], "state": item["state"], "message": msg})

    for item in sorted(items.values(), key=lambda i: i["id"]):
        st, cid = item["state"], item["id"]
        if st not in scope:
            continue
        head = (item.get("approved_head") or "").strip()
        has_appr = bool(item.get("approvals"))
        passed_approved = has_appr or cid in approved_once
        conf = confirmations.get(cid)
        if not head:
            add("NO_HEAD", item, "لا approved_head في الدفتر")
        if conf is None and cid in (live_confirmations or {}):
            add("UNMERGED_CONFIRM", item, "سطرُ التأكيد في الشجرة الحيّة وغيرُ مدفوعٍ إلى main بعد")
        elif conf is None and not has_appr:
            add("NO_CONFIRM", item, "لا سطرَ في owner_confirmations.md ولا اعتمادَ مسجَّلاً")
        elif conf and head and any(conf) and not any(_same(head, h) for h in conf):
            add("CONFIRM_HEAD", item, f"رأسُ الدفتر {head[:8]} ليس بين رؤوس التأكيد {sorted(h[:8] for h in conf)}")
        if st in AFTER_APPROVAL and not passed_approved:
            add("PUSHED_NO_APPR", item, f"حالة {st} بلا مرورٍ بـapproved ولا اعتماد")
        if st == "pushed" and lookup is not None and item.get("branch"):
            try:
                rh = lookup(item["branch"])
            except OSError as e:
                add("BRANCH_MISSING", item, f"تعذّر قراءةُ البعيد للفرع {item['branch']}: {e}")
                continue
            if rh is None:
                add("BRANCH_MISSING", item, f"الفرع {item['branch']} غيرُ موجودٍ على البعيد")
            elif head and not _same(head, rh):
                add("HEAD_MISMATCH", item, f"رأسُ الدفتر {head[:8]} ≠ رأس {item['branch']} على البعيد {rh[:8]}")
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--all", action="store_true", help="يشمل merged/published/closed")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--repo", default="D:/shschool_mvp", help="مستودعُ التنفيذ لقراءة البعيد")
    ap.add_argument("--no-git", action="store_true", help="بلا فحص البعيد")
    ap.add_argument("--live-confirmations", default="C:/Users/mesue/delivery_manager_work/owner_confirmations.md",
                    help="ملفُ الشجرة الحيّة لتمييز «غيرُ مدفوعٍ بعد» عن «غائب»")
    ap.add_argument("--confirmations", default=str(ROOT / "owner_confirmations.md"))
    a = ap.parse_args(argv)
    events = ledger.load_events()
    conf = parse_confirmations(Path(a.confirmations).read_text(encoding="utf-8"))
    live_p = Path(a.live_confirmations)
    live = parse_confirmations(live_p.read_text(encoding="utf-8")) if live_p.is_file() and live_p.resolve() != Path(a.confirmations).resolve() else None
    found = check(events, conf, None if a.no_git else (lambda b: remote_head(b, a.repo)), a.all, live)
    if a.json:
        print(json.dumps(found, ensure_ascii=False, indent=1))
    else:
        for f in found:
            print(f"{f['code']:<15} {f['id']} [{f['state']}] {f['message']}")
        print(f"— {len(found)} كشف" if found else "— الدفتر سليم")
    return 1 if any(f["code"] != "UNMERGED_CONFIRM" for f in found) else 0


if __name__ == "__main__":
    sys.exit(main())
