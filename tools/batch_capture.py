#!/usr/bin/env python3
"""التقاطُ الأدلّة البصريّة للدفعة آلياً من خادم المعاينة المتكامل (W-20261015-012، بند 3، قرار المالك 10-18) — بلا تثبيتٍ يدويّ.

كان 0502 ينتظر أن تثبّت 0501 كلَّ بطاقةٍ على 8500 كي يلتقط لها؛ والخادمُ المتكامل (`preview.sh integrate`) يعرض أصلاً رؤوسَ الدفعة
مجتمعةً. فهذه الأداةُ تقرأ جدولَ الدفعة (`batch_preview.plan`)، وتأخذ لكلّ بطاقةٍ رأسَها ورابطَها ودورَها، وتلتقط بـ`visual_gate.run`
من الخادم نفسِه — لكن **فقط** إن كان رأسُ البطاقة داخل ما يخدمه الخادمُ فعلاً (`/health/` يعلن commit المتكامل، ويُفحص بـ
`git merge-base --is-ancestor`)؛ فلا تُلتقط صفحةٌ لرأسٍ لا يُعرض عليها، ولا تُنسب أدلّةٌ إلى رأسٍ لم يُلتقط.

لا تعتمد ولا تثبّت ولا تدفع ولا تراسل ولا تغيّر تسلسلَ اعتماد المالك: تكتب `evidence/<بطاقة>/<رأس8>/` فحسب، ويبقى
`approval_check` (عبر `visual_gate.evidence_status`) يرفض اعتمادَ رأسٍ بلا أدلّةٍ له.

    python batch_capture.py [--repo D:/shschool_mvp] [--base-url http://localhost:8500] [--max-age-h 48] [--cards W-1 W-2] [--run]

بلا `--run` تُطبع الخطّةُ فقط (قراءةٌ بحتة).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import batch_preview  # noqa: E402
import ledger  # noqa: E402
import visual_gate  # noqa: E402

COMMIT_RE = re.compile(r'"commit"\s*:\s*"([0-9a-f]{7,40})"')
DEFAULT_REPO = "D:/shschool_mvp"
DEFAULT_URL = "http://localhost:8500"

CAPTURED = "captured"  # أدلّةٌ كاملةٌ لهذا الرأس موجودة
CAPTURE = "capture"  # يُلتقط الآن
NOT_SERVED = "not_served"  # رأسُها ليس فيما يخدمه الخادم
NO_PAGE = "no_page"  # لا مسارَ في رابط البطاقة


def served_commit(base_url: str, opener=urllib.request.urlopen) -> str:
    """commit الذي يعلنه `/health/` — فارغٌ إن تعذّر (غير مقيس لا صفر)."""
    try:
        with opener(base_url.rstrip("/") + "/health/", timeout=8) as resp:
            body = resp.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — خادمٌ مطفأٌ أو بلا شبكة
        return ""
    m = COMMIT_RE.search(body)
    return m.group(1) if m else ""


def head_is_served(repo: str, head: str, served: str) -> bool:
    """هل رأسُ البطاقة سلفٌ لما يخدمه الخادم. بلا commit معلَنٍ أو غيرِ موجودٍ في المخزن: لا (غير مقيس لا نعم)."""
    if not served or not head:
        return False
    code = subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", head, served], capture_output=True, check=False).returncode  # noqa: S603,S607
    return code == 0


def entries_for(row: dict) -> list[dict]:
    """صفحاتُ الالتقاط من رابط البطاقة: مسارُه ودورُها. بلا رابطٍ أو مسار: قائمةٌ فارغةٌ فتُرفض بدل أن تُختَلق."""
    link = row.get("link") or ""
    if not link.startswith("http"):
        return []
    path = urlparse(link).path or "/"
    role = row.get("role") or ""
    return [{"path": path, "role": role if role and role != "—" else "anonymous"}]


def plan_capture(batch: dict, repo: str, served: str, evidence_dir: Path | None = None) -> list[dict]:
    """لكلّ بطاقةٍ في الدفعة: ماذا يُفعل بها ولِمَ. قراءةٌ فقط."""
    out = []
    for row in batch["included"]:
        head8 = row["head"][:8]
        ok, _msg = visual_gate.evidence_status(row["id"], head8, evidence_dir)
        entries = entries_for(row)
        if ok:
            status, why = CAPTURED, f"أدلّةٌ كاملةٌ للرأس {head8}"
        elif not entries:
            status, why = NO_PAGE, "لا مسارَ في رابط البطاقة — يُعلن المنفِّذُ الصفحاتِ ولا تُختلق"
        elif not head_is_served(repo, row["head"], served):
            status, why = NOT_SERVED, f"رأسُها {head8} ليس فيما يخدمه الخادمُ (commit={served or 'غير مقيس'}) — ينتظر تكاملَ الخادم"
        else:
            status, why = CAPTURE, f"يُلتقط {len(entries)} صفحةً للرأس {head8}"
        out.append({"id": row["id"], "head": head8, "status": status, "why": why, "entries": entries})
    return out


def render(steps: list[dict], served: str) -> str:
    lines = [f"الخادمُ يعلن commit: {served or 'غير مقيس'}"]
    lines += [f"{'✔' if s['status'] in (CAPTURED, CAPTURE) else '✗'} {s['id']} [{s['head']}] — {s['why']}" for s in steps]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--base-url", default=DEFAULT_URL)
    ap.add_argument("--max-age-h", type=int, default=48)
    ap.add_argument("--cards", nargs="*")
    ap.add_argument("--run", action="store_true", help="يلتقط فعلاً؛ بدونه خطّةٌ فقط")
    args = ap.parse_args(argv)
    path = ledger.ledger_path()
    if not path.is_file():
        print(f"✗ لا دفترَ في {path}", file=sys.stderr)
        return 2
    items = ledger.reduce_state(ledger.load_events(path))
    batch = batch_preview.plan(items, args.repo, args.base, args.max_age_h, only=args.cards)
    served = served_commit(args.base_url)
    steps = plan_capture(batch, args.repo, served)
    print(render(steps, served))
    if not args.run:
        return 0
    failed = 0
    for step in steps:
        if step["status"] != CAPTURE:
            continue
        manifest = visual_gate.run(step["id"], step["head"], args.base_url, step["entries"])
        print(f"التُقطت {step['id']}: {len(manifest.get('pages', []))} صفحة")
        ok, msg = visual_gate.evidence_status(step["id"], step["head"])
        print(("✔ " if ok else "✗ ") + msg)
        failed += not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
