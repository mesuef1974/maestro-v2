#!/usr/bin/env python3
"""مضخّةُ التدفّق (تكليف المالك 2026-10-20: حلٌّ جذريّ لتأخّر حلقة الاعتماد←الدفع←الدمج←النشر؛ D-450م وD-451م وD-452م) — عرضٌ افتراضيّاً و`--apply` للتنفيذ.

تنقل البطاقاتِ آليّاً متى ثبت شرطُها **من المصدر** لا من رسائل الجلسات، بهذا الترتيب:
  1. اعتماد — ready_for_review ← approved: الرأسُ المعلَن (حقلُ ready_head المهيكل، D-452م؛ وإلا آخرُ مذكّرةٍ به) يثبت اعتمادُه
     (approval_check ✔ برمز 0). الدفترُ نفسُه يرفض ما لا يستوفي بوّاباتِه (أدلّة بصريّة، مواصفة) فيُبلَّغ ولا يُفرض.
  2. إعفاء — رأسٌ جديدٌ لبطاقةٍ معتمَدة (معلَنٌ، أو رأسُ طلبها المفتوح): `waive-head --kind auto` بتوقيع 0101 إن أثبت الكودُ
     أنه دمجُ main خالص أو إصلاحُ اختباراتٍ فقط أو سلسلتُهما (D-451م)؛ وما سواه يبقى اعتماداً جديداً للمالك.
  3. دفع — approved ← pushed بحرّاس push_approved كلّها، على فرعٍ claude/* أو w*، وبإيصال prepush ناجحٍ للرأس نفسه (D-450م).
  4. سطرُ الاعتماد — يُكتب أوّلَ وصف الطلب المفتوح على الرأس المعتمَد إن غاب أو لم يطابق (D-450م): قولُ المالك المباشر
     «اعتُمد من المالك مباشرةً بلا معاينة 8500 — …» أو تكليفُه «اعتُمد بتكليف المالك D-443م عبر 0101 — …»، والرأسُ يلي التاريخ.
  5. دمج — `gh pr merge --squash --auto --match-head-commit` لطلبٍ سطرُه سليم، فيدمجه GitHub عند خضرة CI (D-450م). يُستثنى
     ويُبلَّغ: المسودّة، والأساسُ غيرُ main، والهجراتُ (لـ0601، D-428م)، والطلبُ الواسع، والموسومُ أمنيّاً أو اللامسُ مساراتِ
     الأمن والصلاحيّات (محظوراتُ auto_merge_gate) بلا «أقرّ أمنياً» من المالك على الرأس أو سلفه المحمول بتنازلاتٍ مُعاد تحقّقُها.
  6. نشر — approved/pushed/merged ← published: ledger_sync (طلبٌ مدموج بالرأس نفسه).
لا ترسل رسائل: تُبلَّغ البطاقاتُ العالقة نصّاً مجمَّعاً بدل رسائلَ بين جلسات.

    python flow_pump.py               # عرض
    python flow_pump.py --apply       # ينفّذ ويطبع الإبلاغ
    python flow_pump.py --apply --skip W-20261001-006       # يستثني بطاقاتٍ من المراحل كلّها
    python flow_pump.py --apply --no-push --no-line --no-merge   # يعطّل مراحلَ بعينها
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import approval_check as ac  # noqa: E402
import ledger  # noqa: E402
import ledger_sync  # noqa: E402
import push_approved  # noqa: E402

HEAD_RE = re.compile(r"(?:(?:بالرأس|للرأس|الرأس)\s+|[@＠]\s*)([0-9a-f]{8,40})")
SENDER = "0101"
#: حالاتُ البطاقة التي يُقرأ لها طلبٌ مفتوح (إعفاءٌ برأسه، وسطرُ الاعتماد، والدمج)
PR_STATES = ("approved", "pushed")
PR_FIELDS = "number,headRefOid,headRefName,title,body,labels,files,changedFiles,baseRefName,isDraft,autoMergeRequest"
#: سطرا الاعتماد اللذان تكتبهما المضخّة (D-450م)؛ الرأسُ بعد التاريخ مباشرةً كما يقرؤه فحصُ المستودع، والرمزُ بعده (W-20261016-018)
DIRECT_LINE = "اعتُمد من المالك مباشرةً بلا معاينة 8500 — {date} — الرأس {head8} — {card}"
MANDATE_LINE = "اعتُمد بتكليف المالك D-443م عبر 0101 — {date} — الرأس {head8} — {card}"
#: صيغُ السطر التي يقرأ منها فحصُ المستودع (D:/shschool_mvp: scripts/pr_approval_head_check.py) الرأسَ
LINE_FORMS = re.compile(
    r"اعتُمد من المالك (?:على 8500|مباشرةً بلا معاينة 8500) — \d{4}-\d{2}-\d{2} — الرأس ([0-9a-f]{7,40})"
    r"|اعتُمد بتكليف المالك D-\d+م عبر (?:0101|0501) — \d{4}-\d{2}-\d{2} — الرأس ([0-9a-f]{7,40})"
    r"|اعتُمد بتفويض (?:0101|0501) على الرأس ([0-9a-f]{8,40}) — \d{4}-\d{2}-\d{2}"
)
APPROVALISH = re.compile(r"^\s*(?:اعتُمد|اعتمد)")
SECURITY_LABEL = "مراجعة-أمنية-إلزامية"
#: مساراتُ الدمج الآليّ المحظورة في المستودع (scripts/auto_merge_gate.py FORBIDDEN_GLOBS، W-016) سوى الهجرات:
#: تُعامَل معاملةَ الوسم الأمنيّ — لا دمجَ آليّاً بلا «أقرّ أمنياً» من المالك
SENSITIVE_GLOBS = ("*/security/*", "security/*", "*permissions*", "*rbac*", "*roles*", "*role*")
#: طلبٌ بهذا العدد من الملفّات فأكثر لا يُدمج آليّاً (يُعرض)
MAX_FILES = 100
same_head = push_approved.same_head


def ready_head(item: dict) -> str | None:
    """الرأسُ المعلَن «جاهزاً»: الحقلُ المهيكل ready_head (D-452م) إن حضر — والفارغُ سحبٌ للإعلان — وإلا آخرُ رأسٍ في المذكّرات."""
    if "ready_head" in item:
        return (item.get("ready_head") or "")[:8] or None
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


def _sh(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    """مشغّلُ أوامر gh (قابلٌ للحقن في الاختبار): (الرمز، الخرج؛ ومعه الخطأ عند الفشل)."""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return p.returncode, (p.stdout or "") + (p.stderr if p.returncode else "")


def _tail(text: str, n: int = 160) -> str:
    return ((text or "").strip().splitlines()[-1:] or [""])[0][:n]


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


def open_prs(sh=None) -> list[dict] | None:
    """طلباتُ الدمج المفتوحة في مستودع المنصّة؛ None إن تعذّرت القراءة (فلا يُبنى على غياب)."""
    rc, out = (sh or _sh)(["gh", "pr", "list", "--state", "open", "--limit", "100", "--json", PR_FIELDS], ac.REPO_DIR)
    if rc:
        return None
    try:
        data = json.loads(out)
    except ValueError:
        return None
    return data if isinstance(data, list) else None


def card_prs(states: dict[str, dict], prs: list[dict]) -> tuple[dict[str, dict], list[str]]:
    """(بطاقة ← طلبُها المفتوح الوحيد، بلاغاتُ الالتباس) لبطاقات approved/pushed برأس اعتماد.
    البطاقةُ من الطلب بـapproval_check.pr_card (الفرع ثمّ العنوان ثمّ الوصف)؛ التعارضُ أو تعدّدُ الطلبات لا يُخمَّن."""
    def ours(cid: str | None) -> bool:
        item = states.get(cid or "")
        return bool(item and item.get("state") in PR_STATES and item.get("approved_head"))

    by_card: dict[str, list[dict]] = {}
    notes: list[str] = []
    for pr in prs:
        cid, conflict = ac.pr_card(pr)
        if conflict:
            if any(ours(c) for c in ac._CARD_IN_LINE.findall(conflict)):
                notes.append(f"#{pr.get('number')}: {conflict}")
            continue
        if ours(cid) and pr.get("headRefOid"):
            by_card.setdefault(cid, []).append(pr)
    pairs: dict[str, dict] = {}
    for cid, lst in sorted(by_card.items()):
        if len(lst) > 1:
            notes.append(f"{cid}: التباس — أكثرُ من طلبٍ مفتوح ({'، '.join('#' + str(p.get('number')) for p in lst)}) — لا تخمين")
        else:
            pairs[cid] = lst[0]
    return pairs, notes


def approved_prs(states: dict[str, dict], prs: list[dict]) -> list[tuple[str, dict, dict]]:
    """(البطاقة، الطلب، بندُها) لطلبٍ رأسُه رأسُ اعتماد البطاقة نفسُه."""
    pairs, _ = card_prs(states, prs)
    return [(cid, pr, states[cid]) for cid, pr in sorted(pairs.items())
            if same_head(states[cid]["approved_head"], pr["headRefOid"][:8])]


def waive_pass(states: dict[str, dict], apply: bool, prs: list[dict] | None = None) -> list[str]:
    """رأسٌ جديدٌ لبطاقةٍ معتمَدة — معلَنٌ «جاهزاً» أو رأسُ طلبها المفتوح — يوقَّع waive-head --kind auto بتوقيع 0101 إن أثبت
    الكودُ أنه دمجُ main خالصٌ أو إصلاحُ اختباراتٍ فقط أو سلسلتُهما (D-451م)؛ وما سواه يبقى للمالك."""
    cands: dict[str, tuple[str, str]] = {}
    for cid, item in sorted(states.items()):
        if item.get("state") not in ("approved", "ready_for_review") or not item.get("approved_head"):
            continue
        head = ready_head(item)
        if head and not same_head(item["approved_head"], head):
            cands[cid] = (head, "معلَن")
    pairs, _ = card_prs(states, prs or [])
    for cid, pr in pairs.items():
        head = pr["headRefOid"][:8]
        if cid not in cands and not same_head(states[cid]["approved_head"], head):
            cands[cid] = (head, f"رأسُ الطلب #{pr.get('number')}")
    out: list[str] = []
    for cid, (head, src) in sorted(cands.items()):
        if not apply:
            out.append(f"{cid}: رأس {head} ({src}) مرشّحٌ لإعفاء auto (عرض)")
            continue
        p = subprocess.run(
            [sys.executable, str(HERE / "ledger.py"), "waive-head", cid, "--head", head, "--by", SENDER,
             "--kind", "auto", "--reason", "إعفاءٌ آليّ من المضخّة بتحقّق الشجرة (قرار المالك 2026-10-20، D-451م)"],
            capture_output=True, encoding="utf-8", errors="replace",
        )
        tail = (p.stdout + p.stderr).strip().splitlines()[-1:] or [""]
        out.append(f"{cid}: رأس {head} ({src}) إعفاء: {'✔' if p.returncode == 0 else 'ليس إعفاءً آليّاً — ' + tail[0][:120]}")
    return out


PUSH_STATUS = {"pushed": "دُفع ✔", "dry": "يُدفع (عرض)", "refused": "✘ رُفض الدفع", "skipped": "تخطٍّ"}


def push_pass(states: dict[str, dict], apply: bool, repos: list[str] | None = None, path=None, git=None, approved=None) -> list[str]:
    """(D-450م) approved ← pushed عبر push_watch.scan بحرّاس push_approved كلّها، وفرعٍ claude/* أو w*، وإيصال prepush للرأس نفسه."""
    items = {k: v for k, v in states.items() if v.get("state") == "approved"}
    if not items:
        return []
    import push_watch  # noqa: PLC0415
    import ready_mark  # noqa: PLC0415

    kw = {k: v for k, v in (("git", git), ("approved", approved)) if v is not None}
    results = push_watch.scan(items, repos or ready_mark.candidate_repos(None), apply, path, by=SENDER,
                              branch_re=push_approved.PUMP_BRANCH_RE, require_receipt=True, **kw)
    out, quiet = [], 0
    for r in results:
        if r["status"] == "skipped" and push_watch.QUIET in r["reason"]:
            quiet += 1
            continue
        where = f" {r['branch']}" if r.get("branch") else ""
        out.append(f"{r['card']}:{where} {PUSH_STATUS.get(r['status'], r['status'])} — {r['reason'][:160]}")
    if quiet:
        out.append(f"{quiet} بطاقةً معتمَدة بلا شجرةٍ هنا على رأسها بفرعٍ مسموح — لا دفع")
    return out


def line_ok(body: str | None, head8: str, card: str) -> bool:
    """في الوصف سطرٌ بإحدى صيغ فحص المستودع يحمل هذا الرأس بعد التاريخ، ولا يخالف رمزَ البطاقة (line_card_problem)."""
    for ln in (body or "").splitlines():
        m = LINE_FORMS.search(ln)
        h = next((g for g in m.groups() if g), None) if m else None
        if h and same_head(h, head8) and ac.line_card_problem(ln, card) is None:
            return True
    return False


def approval_line(card: str, head8: str, item: dict) -> str | None:
    """سطرُ الاعتماد للرأس: مباشرٌ إن كان للمالك قولٌ مباشرٌ على الرأس أو سلفه المحمول، وإلا تكليفُ D-443م؛ None إن لا أصل."""
    found = ac.approval_base(card, head8)
    if not found:
        return None
    base, rows = found
    import pr_open_prep  # noqa: PLC0415

    date, _src = pr_open_prep.approval_date(item)
    line = (DIRECT_LINE if ac.owner_direct(rows) else MANDATE_LINE).format(date=date, head8=head8[:8], card=card)
    return line if same_head(base, head8) else f"{line} — موروثٌ من الرأس {base} (D-451م)"


def with_line(body: str | None, line: str) -> str:
    """السطرُ أوّلَ الوصف: يحلّ محلَّ أوّل سطرٍ إن كان سطرَ اعتماد (قديماً أو مخالفاً)، وإلا يُضاف قبله."""
    lines = (body or "").splitlines()
    if lines and APPROVALISH.match(lines[0]):
        return "\n".join([line, *lines[1:]])
    return "\n".join([line, "", *lines]) if lines else line


def write_body(num, body: str, sh) -> tuple[int, str]:
    fd, tmp = tempfile.mkstemp(prefix="pump_body_", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        return sh(["gh", "pr", "edit", str(num), "--body-file", tmp], ac.REPO_DIR)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def line_pass(states: dict[str, dict], prs: list[dict], apply: bool, sh=None) -> list[str]:
    """(D-450م) سطرُ الاعتماد في وصف الطلب المفتوح على الرأس المعتمَد: يُكتب إن غاب أو خالف، بعد approval_check ✔ للرأس."""
    sh = sh or _sh
    out: list[str] = []
    for cid, pr, item in approved_prs(states, prs):
        num, head = pr.get("number"), pr["headRefOid"][:8]
        if line_ok(pr.get("body"), head, cid):
            continue
        if not approval_ok(cid, head):
            out.append(f"{cid}: #{num} رأس {head} بلا اعتمادٍ ثابت — لا سطر")
            continue
        line = approval_line(cid, head, item)
        if line is None:
            out.append(f"{cid}: #{num} لا قولَ للمالك ولا تكليفَ مسجَّلاً على الرأس {head} أو سلفه المحمول — لا سطر")
            continue
        body = with_line(pr.get("body"), line)
        if not apply:
            pr["body"] = body  # نسخةُ هذه الدورة وحدَها: ليرى العرضُ مرحلةَ الدمج كما ستجري
            out.append(f"{cid}: #{num} يُكتب «{line}» (عرض)")
            continue
        rc, msg = write_body(num, body, sh)
        if rc == 0:
            pr["body"] = body
        out.append(f"{cid}: #{num} سطرُ الاعتماد: {'✔' if rc == 0 else '✘ ' + _tail(msg)}")
    return out


def merge_block(card: str, pr: dict) -> str | None:
    """سببُ ترك الطلب لغير الدمج الآليّ؛ None إن لا مانع."""
    if pr.get("isDraft"):
        return "مسودّة"
    if (pr.get("baseRefName") or "") != "main":
        return f"الأساسُ «{pr.get('baseRefName')}» لا main"
    paths = [str(f.get("path", "")) for f in pr.get("files") or []]
    if any("/migrations/" in "/" + p.replace("\\", "/") for p in paths):
        return "هجراتٌ: الدمجُ لـ0601 (D-428م)"
    if max(int(pr.get("changedFiles") or 0), len(paths)) >= MAX_FILES:
        return f"طلبٌ واسع (≥{MAX_FILES} ملفّ): يُعرض ولا يُدمج آليّاً"
    labels = {str(lb.get("name", "")) for lb in pr.get("labels") or []}
    sensitive = [p for p in paths if any(fnmatch.fnmatchcase(p.lower(), g) for g in SENSITIVE_GLOBS)]
    if (SECURITY_LABEL in labels or sensitive) and not ac.security_approved(card, pr["headRefOid"][:8]):
        why = f"وسمُ «{SECURITY_LABEL}»" if SECURITY_LABEL in labels else f"مساراتٌ أمنيّة ({'، '.join(sensitive[:3])})"
        return f"{why} بلا «أقرّ أمنياً» من المالك على الرأس أو سلفه المحمول"
    return None


def merge_pass(states: dict[str, dict], prs: list[dict], apply: bool, sh=None) -> list[str]:
    """(D-450م) دمجٌ آليّ عند خضرة CI لطلبٍ سطرُ اعتماده سليم: `--auto` مقيَّدٌ بالرأس (`--match-head-commit`) فلا يُدمج غيرُه."""
    sh = sh or _sh
    out: list[str] = []
    for cid, pr, _item in approved_prs(states, prs):
        num, full = pr.get("number"), pr["headRefOid"]
        head = full[:8]
        if pr.get("autoMergeRequest"):
            continue  # الدمجُ الآليّ مفعَّلٌ أصلاً على هذا الطلب
        if not line_ok(pr.get("body"), head, cid):
            out.append(f"{cid}: #{num} بلا سطر اعتمادٍ سليمٍ للرأس {head} — لا دمج")
            continue
        why = merge_block(cid, pr)
        if why:
            out.append(f"{cid}: #{num} لا دمجَ آليّاً — {why}")
            continue
        if not approval_ok(cid, head):
            out.append(f"{cid}: #{num} رأس {head} بلا اعتمادٍ ثابت — لا دمج")
            continue
        if not apply:
            out.append(f"{cid}: #{num} يُدمج آليّاً عند خضرة CI بالرأس {head} (عرض)")
            continue
        rc, msg = sh(["gh", "pr", "merge", str(num), "--squash", "--auto", "--match-head-commit", full], ac.REPO_DIR)
        out.append(f"{cid}: #{num} دمجٌ آليّ عند خضرة CI: {'✔' if rc == 0 else '✘ ' + _tail(msg)}")
    return out


RERUNS = HERE.parent / "ledger" / "ci_reruns.json"
#: فحصٌ معلَّق أطولَ من هذا (دقائق) يُبلَّغ مرّةً واحدة؛ والفاشل أو الملغى يُعاد مرّةً واحدةً لكلّ رأس
CI_STUCK_MIN = 30
RUN_ID = re.compile(r"/actions/runs/(\d+)")


def _reruns() -> dict:
    try:
        return json.loads(RERUNS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ci_pass(states: dict[str, dict], prs: list[dict], apply: bool, sh=None, now=None) -> list[str]:
    """(مرحلة CI العالق) لا رسائلَ بين الجلسات: فحصٌ فاشل/ملغى لطلبٍ معتمَد يُعاد مرّةً واحدة لكلّ رأس (`gh run rerun --failed`)،
    والمعلَّق أكثر من CI_STUCK_MIN دقيقة يُسجَّل ملاحظةً في الدفتر مرّةً واحدة؛ والمتكرّر فشلُه يُبلَّغ ولا يُعاد."""
    from datetime import datetime, timezone

    sh = sh or _sh
    now = now or datetime.now(timezone.utc)
    done, out = _reruns(), []
    for cid, pr, _item in approved_prs(states, prs):
        num, head = pr.get("number"), pr["headRefOid"][:8]
        rc, raw = sh(["gh", "pr", "checks", str(num), "--json", "name,bucket,startedAt,link"], ac.REPO_DIR)
        try:
            checks = json.loads(raw) if rc in (0, 8) else None
        except ValueError:
            checks = None
        if checks is None:
            continue
        key = f"{num}:{head}"
        bad = [c for c in checks if c.get("bucket") in ("fail", "cancel")]
        runs = sorted({m.group(1) for c in bad if (m := RUN_ID.search(c.get("link") or ""))})
        if bad and runs:
            if done.get(key):
                out.append(f"{cid}: #{num} فحصٌ فاشل بعد إعادةٍ سابقة للرأس {head} ({bad[0].get('name')}) — لا إعادة ثانية")
            elif not apply:
                out.append(f"{cid}: #{num} يُعاد {len(runs)} تشغيلٍ فاشل للرأس {head} (عرض)")
            else:
                oks = [sh(["gh", "run", "rerun", r, "--failed"], ac.REPO_DIR)[0] == 0 for r in runs]
                done[key] = 1
                RERUNS.write_text(json.dumps(done), encoding="utf-8")
                out.append(f"{cid}: #{num} إعادةُ {len(runs)} تشغيلٍ فاشل للرأس {head}: {'✔' if all(oks) else '✘'}")
            continue
        for c in checks:
            if c.get("bucket") != "pending" or not c.get("startedAt") or done.get(key + ":stuck"):
                continue
            age = (now - datetime.fromisoformat(c["startedAt"].replace("Z", "+00:00"))).total_seconds() / 60
            if age < CI_STUCK_MIN:
                continue
            if apply:
                ledger.add_note(cid, f"فحصٌ معلَّق منذ {int(age)} دقيقة على #{num} ({c.get('name')}) — رصد المضخّة", SENDER)
                done[key + ":stuck"] = 1
                RERUNS.write_text(json.dumps(done), encoding="utf-8")
            out.append(f"{cid}: #{num} فحصٌ معلَّق {int(age)} دقيقة ({c.get('name')})")
            break
    return out


LOCK = HERE.parent / "ledger" / "flow_pump.lock"
LOG = HERE.parent / "ledger" / "flow_pump.log"
#: مفتاحُ الإيقاف (الموجة 0.3، D-453م): وجودُ الملف يمنع الدورة من أيّ مشغِّل (الخطّاف، مهمّةٌ مجدولة، يدويّاً) لا الخطّافَ وحده
OFF = HERE.parent / "ledger" / "flow_pump.off"
#: مفتاحُ منع الدمج: وجودُ الملف يعطّل مرحلةَ الدمج وحدَها من أيّ مشغِّل (الخطّاف يطلق المضخّةَ بلا --no-merge)
NO_MERGE = HERE.parent / "ledger" / "flow_pump.nomerge"
STALE_LOCK_S = 900


def _lock() -> bool:
    """قفلٌ بملفّ: دورتان لا تتداخلان؛ القفلُ الأقدم من 15 دقيقة يُعدّ ميتاً."""
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
    if OFF.exists():
        print(f"مفتاحُ الإيقاف قائم ({OFF.name}) — لا دورة")
        return 0
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
    ap.add_argument("--skip", nargs="*", default=[], help="بطاقاتٌ تُستثنى من المراحل كلّها")
    ap.add_argument("--no-push", action="store_true", help="بلا مرحلة الدفع")
    ap.add_argument("--no-line", action="store_true", help="بلا كتابة سطر الاعتماد في الطلب")
    ap.add_argument("--no-merge", action="store_true", help="بلا الدمج الآليّ")
    ap.add_argument("--no-ci", action="store_true", help="بلا إعادة الفحوص العالقة")
    a = ap.parse_args(argv)

    def load() -> dict[str, dict]:
        return {k: v for k, v in ledger.reduce_state(ledger.load_events()).items() if k not in a.skip}

    def reload(states: dict[str, dict]) -> dict[str, dict]:
        return load() if a.apply else states  # ما نُقل يُقرأ من الدفتر قبل المرحلة التالية؛ والعرضُ لا ينقل شيئاً

    states = load()
    for line in approve_pass(states, a.apply):
        print("اعتماد: " + line)
    states = reload(states)
    prs: list[dict] = []
    if any(v.get("state") in PR_STATES and v.get("approved_head") for v in states.values()):
        got = open_prs()
        if got is None:
            print("طلبات: تعذّرت قراءةُ الطلبات المفتوحة (gh) — لا إعفاءَ برأس الطلب ولا سطرَ ولا دمج في هذه الدورة")
        prs = got or []
        for note in card_prs(states, prs)[1]:
            print("طلبات: " + note)
    for line in waive_pass(states, a.apply, prs):
        print("إعفاء: " + line)
    states = reload(states)
    if not a.no_push:
        for line in push_pass(states, a.apply):
            print("دفع: " + line)
        states = reload(states)
    if not a.no_line:
        for line in line_pass(states, prs, a.apply):
            print("سطر: " + line)
    if NO_MERGE.exists():
        print(f"دمج: معطَّل بمفتاح ({NO_MERGE.name})")
    elif not a.no_merge:
        for line in merge_pass(states, prs, a.apply):
            print("دمج: " + line)
    if not a.no_ci:
        for line in ci_pass(states, prs, a.apply):
            print("ci: " + line)
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
