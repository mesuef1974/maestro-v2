#!/usr/bin/env python3
"""مشغّلُ الدفع الآليّ بعد الاعتماد (W-20261019-016، أمر المالك 2026-10-19): p90 نحو 32 ساعةً بين الاعتماد والدفع.

يمسح بطاقاتِ `approved` في الدفتر، ولكلٍّ يبحث عن الشجرة التي HEAD فيها هو الرأسُ المعتمَد حرفيّاً على فرعٍ claude/* وفي إيداعاتِه رمزُ البطاقة،
ثمّ يستدعي `push_approved.push(..., apply=True)` الذي يحمل الحرّاسَ كلَّها (approval_check ✔ بالرأس، رأسٌ مطابق، شجرةٌ نظيفة، لا force، لا main).
لا يخفّف حارساً ولا يفتح طلبَ دمج ولا يدمج: يدفع فقط ويُسلّم البطاقةَ والفرعَ لـ0601 (سطرٌ بصيغة red_notify؛ الإرسالُ أداةُ SendMessage في جلسة Monitor).

    python push_watch.py --once [--dry-run]       دورةٌ واحدة (--dry-run: عرضٌ بلا دفع)
    python push_watch.py --loop [--interval 300]  للمراقبة بأداة Monitor

سطرُ الخرج (Tab):  إحالة <رقم المستلم> <معرّف الجلسة أو —> <النصّ>
عدمُ التكرار: ما دُفع صار pushed فخرج من المسح؛ ورفضٌ بالسبب نفسِه لنفس (بطاقة، رأس) يُعلَن مرّةً واحدةً في التشغيل.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ledger  # noqa: E402
import push_approved  # noqa: E402
import ready_mark  # noqa: E402

RECIPIENT = "0601"
# أسبابٌ عاديّةٌ لا تستحقّ إعلاناً: لا شجرةَ حاليّةً على الرأس (دُفعت بيدٍ أخرى أو في مستودعٍ آخر) فلا يُخمَّن.
QUIET = "لا شجرةَ"


def worktrees(repo: str, git=push_approved._git) -> list[dict]:
    """شجراتُ المستودع: [{path, head, branch}] من `git worktree list --porcelain`."""
    rc, out = git(repo, "worktree", "list", "--porcelain")
    if rc:
        return []
    entries: list[dict] = []
    cur: dict = {}
    for line in [*out.splitlines(), ""]:
        if not line.strip():
            if cur:
                entries.append(cur)
                cur = {}
        elif line.startswith("worktree "):
            cur["path"] = line[len("worktree "):]
        elif line.startswith("HEAD "):
            cur["head"] = line[len("HEAD "):]
        elif line.startswith("branch refs/heads/"):
            cur["branch"] = line[len("branch refs/heads/"):]
    return entries


def find_tree(card: str, want8: str, repos: list[str], git=push_approved._git) -> tuple[dict | None, str]:
    """(الشجرة، سبب الغياب): واحدةٌ فقط تطابق الرأسَ والفرعَ claude/* ورمزَ البطاقة؛ وإلا None."""
    seen: set[str] = set()
    found: list[dict] = []
    for repo in repos:
        for w in worktrees(repo, git):
            key = str(w.get("path", "")).replace("\\", "/").rstrip("/").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            branch = w.get("branch") or ""
            if not push_approved.BRANCH_RE.match(branch) or w.get("head", "")[:8] != want8:
                continue
            rc, log = git(w["path"], "log", "-1", "--format=%H", f"--grep={card}", w["head"], "^origin/main")
            if not rc and log.strip():
                found.append(w)
    if not found:
        return None, f"{QUIET} على الرأس {want8} بفرع claude/* يحمل رمز {card}"
    if len(found) > 1:
        return None, "التباس: أكثر من شجرةٍ على الرأس " + want8 + " (" + "، ".join(w["branch"] for w in found) + ")"
    return found[0], ""


def scan(items: dict, repos: list[str], apply: bool = True, path=None, git=push_approved._git,
         approved=push_approved.approval_ok, by: str = "0702") -> list[dict]:
    """نتيجةُ كلّ بطاقةٍ approved: {card, status: pushed|dry|refused|skipped, branch, head, reason, holder}."""
    out = []
    for card in sorted(items):
        item = items[card]
        if item.get("state") != "approved":
            continue
        want = (item.get("approved_head") or "")[:8]
        base = {"card": card, "head": want, "branch": "", "holder": item.get("held_by") or ""}
        if not want:
            out.append({**base, "status": "skipped", "reason": "لا رأسَ اعتمادٍ في الدفتر"})
            continue
        tree, why = find_tree(card, want, repos, git)
        if tree is None:
            out.append({**base, "status": "skipped", "reason": why})
            continue
        base["branch"] = tree["branch"]
        try:
            msg = push_approved.push(card, tree["branch"], tree["path"], apply, path=path, git=git, approved=approved, by=by)
        except (push_approved.PushRefused, ledger.LedgerError) as exc:
            out.append({**base, "status": "refused", "reason": str(exc)})
        else:
            out.append({**base, "status": "pushed" if apply else "dry", "reason": msg})
    return out


def messages(results: list[dict], directory: dict, announced: set) -> list[tuple[str, str, str]]:
    """رسائل (مستلم، معرّف، نصّ): تسليمٌ لـ0601 لكلّ دفع؛ ورفضٌ بسببه لحامل البطاقة مرّةً."""
    msgs = []
    for r in results:
        if r["status"] == "pushed":
            sid = (directory.get(RECIPIENT) or {}).get("id", "—")
            msgs.append((RECIPIENT, sid, f"{r['card']}: دُفع الفرع {r['branch']} بالرأس {r['head']} آلياً بعد approval_check ✔ (السجلّ هو الدفتر) — افتحي الطلب وادمجي؛ لا طلبَ ولا دمجَ من الدافع."))
        elif r["status"] == "refused" and (r["card"], r["head"], r["reason"]) not in announced:
            announced.add((r["card"], r["head"], r["reason"]))
            to = r["holder"] or "0101"
            sid = (directory.get(to) or {}).get("id", "—")
            msgs.append((to, sid, f"{r['card']}: رُفض الدفعُ الآليّ — {r['reason'][:180]}"))
    return msgs


def emit(msgs: list[tuple[str, str, str]]) -> None:
    for to, sid, text in msgs:
        print(f"إحالة\t{to}\t{sid}\t{text}", flush=True)


def cycle(apply: bool, announced: set, repos: list[str] | None = None, path=None, by: str = "0702") -> list[dict]:
    items = ledger.reduce_state(ledger.load_events(path))
    try:
        import session_directory  # noqa: PLC0415

        directory = session_directory.entries()
    except Exception:  # noqa: BLE001 — الدليلُ مساعدٌ لا شرط
        directory = {}
    results = scan(items, repos or ready_mark.candidate_repos(None), apply, path, by=by)
    emit(messages(results, directory, announced))
    return results


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true", help="عرضٌ بلا دفع")
    ap.add_argument("--by", default="0702", help="رقمُ الجلسة المشغِّلة (للدفتر)")
    a = ap.parse_args(argv)
    if not (a.once or a.loop):
        ap.error("اختر --once أو --loop")
    announced: set = set()
    while True:
        try:
            for r in cycle(not a.dry_run, announced, by=a.by):
                if a.once or r["status"] != "skipped":
                    print(f"# {r['card']} {r['status']}: {r['reason'][:120]}", file=sys.stderr, flush=True)
        except Exception as exc:  # noqa: BLE001 — المراقبةُ لا تسقط من عطلٍ عابر
            print(f"# فشلت الدورة: {exc}", file=sys.stderr, flush=True)
        if a.once:
            return 0
        time.sleep(a.interval)


if __name__ == "__main__":
    raise SystemExit(main())
