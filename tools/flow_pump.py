#!/usr/bin/env python3
"""مضخّةُ التدفّق (تكليف المالك 2026-10-20: حلٌّ جذريّ لتأخّر حلقة الاعتماد←الدفع←الدمج←النشر؛ D-450م وD-451م وD-452م) — عرضٌ افتراضيّاً و`--apply` للتنفيذ.

تنقل البطاقاتِ آليّاً متى ثبت شرطُها **من المصدر** لا من رسائل الجلسات، بهذا الترتيب:
  1. اعتماد — ready_for_review ← approved: الرأسُ المعلَن (حقلُ ready_head المهيكل، D-452م؛ وإلا آخرُ مذكّرةٍ به) يثبت اعتمادُه
     (approval_check ✔ برمز 0). الدفترُ نفسُه يرفض ما لا يستوفي بوّاباتِه (أدلّة بصريّة، مواصفة) فيُبلَّغ ولا يُفرض.
  2. إعفاء — رأسٌ جديدٌ لبطاقةٍ معتمَدة (معلَنٌ، أو رأسُ طلبها المفتوح): `waive-head --kind auto` بتوقيع 0101 إن أثبت الكودُ
     أنه دمجُ main خالص أو إصلاحُ اختباراتٍ فقط أو سلسلتُهما (D-451م)؛ وما سواه يبقى اعتماداً جديداً للمالك.
  2أ. شجرة — بطاقةٌ معتمَدة لها فرعٌ مسموحٌ محلّيٌّ على رأسها بالضبط في مستودع المنصّة ولا شجرةَ عليه: تُنشأ شجرةٌ
     `.claude/worktrees/pump-<البطاقة>` على الفرع نفسه (لا تُعدَّل شجرةٌ قائمة)، فتتولّاها مرحلتا prepush والدفع؛ بطاقتان في الدورة (W-20261023-016).
  2ب. إيصال prepush — لبطاقةٍ معتمَدة سيرفضها الدفعُ لغياب الإيصال: scripts/prepush_check.py للمنصّة داخل صورة Docker
     (tools/prepush_image)، ويُكتب الإيصالُ من المضيف بعد خروجٍ بـ0 (كلُّ الحرّاس قيست ونجحت) وحدَه؛ بطاقةٌ واحدة في الدورة (W-20261023-016).
  3. دفع — approved ← pushed بحرّاس push_approved كلّها، على فرعٍ claude/* أو w*، وبإيصال prepush ناجحٍ للرأس نفسه (D-450م).
  3ب. فتحُ الطلب — بطاقةٌ pushed بلا طلبٍ (مفتوحٍ أو مدموج) على فرعها: `gh pr create` إلى المنصّة بعنوانٍ ووصفٍ من حقول البطاقة وسطرِ الاعتماد،
     شرطَ مطابقة الرأس البعيد لرأس الاعتماد وثباتِ الاعتماد وخلوِّ المسارات من الهجرات والأمن؛ ويُسجَّل رقمُه ملاحظةً على البطاقة؛ لا دمج (W-20261023-016).
  4. سطرُ الاعتماد — يُكتب أوّلَ وصف الطلب المفتوح على الرأس المعتمَد إن غاب أو لم يطابق (D-450م): قولُ المالك المباشر
     «اعتُمد من المالك مباشرةً بلا معاينة 8500 — …» أو تكليفُه «اعتُمد بتكليف المالك D-443م عبر 0101 — …»، والرأسُ يلي التاريخ.
  5. دمج — `gh pr merge --squash --auto --match-head-commit` لطلبٍ سطرُه سليم، فيدمجه GitHub عند خضرة CI (D-450م). يُستثنى
     ويُبلَّغ: المسودّة، والأساسُ غيرُ main، والهجراتُ (لـ0601، D-428م)، والطلبُ الواسع، والموسومُ أمنيّاً أو اللامسُ مساراتِ
     الأمن والصلاحيّات (محظوراتُ auto_merge_gate) بلا «أقرّ أمنياً» من المالك على الرأس أو سلفه المحمول بتنازلاتٍ مُعاد تحقّقُها.
  6. نشر — approved/pushed/merged ← published: ledger_sync (طلبٌ مدموج بالرأس نفسه).
لا ترسل رسائلَ بين جلسات التطبيق: تُبلَّغ البطاقاتُ العالقة نصّاً مجمَّعاً، وتُنسب إلى مالكها بملفّ صندوقه (inbox.send، W-20261027-006) فيلتقطها مراقبُه.

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
import pump_health  # noqa: E402
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


#: (W-20261024-007) جدولٌ ثابتٌ شرطٌ عالقٌ ← مالكُ حلّه. «holder» = حاملُ البطاقة في الدفتر. الرمزُ حروفٌ لاتينيّةٌ صغيرة لأنّه يدخل حمولةَ الإيقاظ (PAYLOAD_OK).
OWNER_BY_COND = {
    "visual_evidence": "0502",   # دليلٌ بصريّ ناقص
    "head_unapproved": "0101",   # رأسٌ بلا اعتمادٍ ثابت
    "migrations": "0601",        # هجراتٌ/أمنٌ تمنع الآليّ: الدمجُ والنشر لـ0601
    "pushed_no_pr": "holder",    # pushed بلا طلبٍ يُفتح: صاحبُ البطاقة
    "prepush": "holder",         # prepush أحمرُ على الرأس: عيبٌ في شيفرة البطاقة يصلحه حاملُها (لا 0501 التي لا تكتب شيفرة)
    "prepush_env": "0701",       # prepush لم يُقَس لعلّةٍ في البيئة (مهلة، أداةٌ غائبة، WinError): الأتمتة
}
PUMP_FROM = "0000"  # مرسِلُ المضخّة في الصندوق (W-20261027-006)؛ رقمٌ صالحٌ لـinbox.NUM لا يخصّ جلسة
ROUTER = "0101"  # حاملٌ بلا مراقبٍ حيّ لا يقرأ صندوقه: تُحال رسالتُه إلى التوجيه لإعادة التكليف
PENDING_DEDUPE_H = 6


def owner_of(cond: str, item: dict) -> str:
    who = OWNER_BY_COND[cond]
    return str(item.get("held_by") or "") if who == "holder" else who


COND_TEXT = {
    "visual_evidence": "ينقصها دليلٌ بصريّ للرأس",
    "head_unapproved": "رأسها بلا اعتمادٍ ثابت",
    "migrations": "تمسّ هجراتٍ/أمناً فيمنع الآليُّ: الدمجُ والنشر لك",
    "pushed_no_pr": "مدفوعةٌ بلا طلب",
    "prepush": "إيصالُ prepush لا يُنتَج: فحصٌ أحمر على رأسها",
    "prepush_env": "إيصالُ prepush لا يُنتَج لعلّةٍ في البيئة لا في الشيفرة",
}

#: علاماتُ الفشل البيئيّ في مخرَج prepush: لا عيبَ في شيفرة البطاقة، فمالكُه الأتمتة لا الحامل
ENV_FAIL_MARKS = ("WinError", "The handle is invalid", "غير مقيس", "غير متاح")


def failure_cond(code: int, log: str) -> str:
    """شرطُ الإحالة لفشل prepush: «prepush_env» لمهلةٍ (124) أو أداةٍ غائبة (3، 127) أو حين يحمل كلُّ سطرِ فشلٍ علامةَ بيئة
    (WinError 6 في كلّ FAILED)؛ وسطرُ فشلٍ واحدٌ بلا علامةٍ يجعله «prepush»: فحصٌ أحمر في الشيفرة يصلحه الحامل."""
    if code in (3, 124, 127):
        return "prepush_env"
    text = log or ""
    bad = [x for x in text.splitlines() if x.lstrip().startswith(("✘", "FAILED", "ERROR"))]
    if bad:
        return "prepush_env" if all(any(m in x for m in ENV_FAIL_MARKS) for x in bad) else "prepush"
    return "prepush_env" if any(m in text for m in ENV_FAIL_MARKS) else "prepush"


def hand_off(cid: str, cond: str, item: dict, apply: bool, root: Path | None = None, now=None, *, detail: str = "",
             alive=None) -> str:
    """يُنسب الشرطُ العالقُ إلى مالكه: يُلحَق بصندوقه رسالةٌ بـinbox.send (لا pending_wakes) فيلتقطها مراقبُه فوراً، ويعيد وسمَ «[مالك=XXXX]» للسطر.
    في العرض (apply=False) لا كتابة. لا تتكرّر رسالةُ (بطاقة، شرط، حالة) خلال PENDING_DEDUPE_H ساعات. بلا مالكٍ معروفٍ يُوسَم «[مالك=؟]».
    `detail` (السببُ وموضعُ السجلّ) يُلحق بالنصّ ليعمل المالكُ بلا تشخيص. مالكٌ مشتقٌّ من الحامل بلا مراقبٍ حيّ (`alive`، الافتراضيّ
    inbox.watcher_alive) يُحال إلى ROUTER: الجلسةُ المؤرشفة أو الخاملة بلا مراقب لا تقرأ صندوقها فتعلق البطاقة صامتة (035 عند 0420، 10-28)."""
    owner = owner_of(cond, item)
    if not re.match(r"^\d{4}", owner):
        return "[مالك=؟]"
    if OWNER_BY_COND[cond] == "holder" and owner != ROUTER:
        import inbox  # noqa: PLC0415

        if not (alive or inbox.watcher_alive)(owner, root):
            detail = (detail + " — " if detail else "") + f"الحامل {owner} بلا مراقبٍ حيّ: أعيدي تكليفها"
            owner = ROUTER
    if not apply:
        return f"[مالك={owner}]"
    from datetime import datetime, timedelta  # noqa: PLC0415

    import inbox  # noqa: PLC0415

    now = now or datetime.now().astimezone()
    state = str(item.get("state") or "")
    tag = f"[مضخّة:{cid}:{cond}:{state}]"
    try:
        for r in inbox._rows(owner, root):
            if r["k"] == "msg" and r["text"].startswith(tag) and now - datetime.fromisoformat(r["ts"]) < timedelta(hours=PENDING_DEDUPE_H):
                return f"[مالك={owner}]"
        text = f"{tag} {cid}: {COND_TEXT.get(cond, cond)}" + (f" — {detail}" if detail else "") + " — أنت مالكُ حلّه (من المضخّة)."
        inbox.send(owner, PUMP_FROM, text, root, ts=now.isoformat(timespec="seconds"))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return f"[مالك={owner}]"


def approval_why(card: str, head: str) -> str:
    """نصُّ approval_check لرأسٍ بلا اعتماد، ليُفرَّق الدليلُ البصريّ (0502) عن غياب الاعتماد (0101)؛ تعذّرُه = غيابُ اعتماد."""
    try:
        p = subprocess.run([sys.executable, str(HERE / "approval_check.py"), "card", card, "--head", head],
                           capture_output=True, encoding="utf-8", errors="replace", timeout=60)
        return (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _sh(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    """مشغّلُ أوامر gh (قابلٌ للحقن في الاختبار): (الرمز، الخرج؛ ومعه الخطأ عند الفشل)."""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return p.returncode, (p.stdout or "") + (p.stderr if p.returncode else "")


ROOT_DIR = Path(__file__).resolve().parent.parent


def root_follow_pass(apply: bool, run=None, root: str | None = None) -> list[str]:
    """(W-20261027-003) الجذرُ الحيّ يتبع main: بعد كلّ دمجٍ يتقدّم ff-only إن لم يتباعد ولم يتقاطع معدَّلُه غيرُ المودَع مع ملفّات الفرق، وإلا إنذارٌ بسببه؛ ولا شيءَ إن كان على main.
    السجلّاتُ (ledger/*.jsonl وowner_confirmations.md...) تُكتب حيّةً فالجذرُ متّسخٌ دائماً: المعيارُ تقاطعُ المعدَّل مع ما يغيّره HEAD..origin/main لا مجرّدُ وجود تعديل.
    تعذّرُ fetch = غيرُ مقيس ولا تقدّم. لا يلمس ملفّاً غيرَ متتبَّعٍ."""
    sh = run or _sh
    cwd = root or str(ROOT_DIR)
    rc, out = sh(["git", "fetch", "-q", "origin", "main"], cwd)
    if rc:
        return [f"الجذر: تعذّر fetch (غير مقيس، لا تقدّم): {_tail(out)}"]
    rc1, behind = sh(["git", "rev-list", "--count", "HEAD..origin/main"], cwd)
    rc2, ahead = sh(["git", "rev-list", "--count", "origin/main..HEAD"], cwd)
    if rc1 or rc2 or not behind.strip().isdigit() or not ahead.strip().isdigit():
        return ["الجذر: تعذّر حسابُ التباعد (غير مقيس)"]
    b, a = int(behind), int(ahead)
    if b == 0:
        return []
    if a:
        return [f"الجذر متباعد عن main: خلفه {b} وأمامه {a} — لا fast-forward؛ مزامنةٌ يدويّةٌ بشجرةٍ مستقلّة (root-sync) ثم ff-only"]
    _, dirty = sh(["git", "status", "--porcelain", "--untracked-files=no"], cwd)
    modified = {ln[3:].strip().strip('"').replace("\\", "/") for ln in dirty.splitlines() if len(ln) > 3}
    rc3, incoming = sh(["git", "diff", "--name-only", "HEAD", "origin/main"], cwd)
    if rc3:
        return ["الجذر: تعذّر حسابُ ملفّات الفرق (غير مقيس)"]
    clash = sorted(modified & {ln.strip().replace("\\", "/") for ln in incoming.splitlines() if ln.strip()})
    if clash:
        return [f"الجذر خلف main بـ{b} ويتقاطع معدَّلُه غيرُ المودَع مع الفرق في {len(clash)} ملفٍّ ({'، '.join(clash[:4])}) — لا تقدّم آليّ؛ أودِعها أو أزِلها"]
    if not apply:
        return [f"الجذر خلف main بـ{b} ويُقدَّم ff-only (عرض)"]
    rc, out = sh(["git", "merge", "--ff-only", "origin/main"], cwd)
    if rc:
        return [f"الجذر: رُفض fast-forward ({b} خلف): {_tail(out)}"]
    return [f"الجذر تقدّم ff-only بـ{b} إيداعاً إلى origin/main"]


def _tail(text: str, n: int = 160) -> str:
    return ((text or "").strip().splitlines()[-1:] or [""])[0][:n]


def owner_list(states: dict[str, dict], git=None, platform: str | None = None) -> list[str]:
    """(W-20261023-016) قائمةُ اعتمادٍ واحدةٌ للمالك: كلُّ بطاقةٍ ready_for_review لها رأسٌ (معلَنٌ أو مشتقّ) بلا اعتمادٍ ثابت.
    تُقرأ من المصدر فلا حاجةَ لرسالةٍ من جلسةٍ؛ وما فيها ينتظر المالكَ وحدَه."""
    rows = []
    for cid, item in sorted(states.items()):
        if item.get("state") != "ready_for_review":
            continue
        head = ready_head(item) or derive_head(cid, git, platform)[0]
        if head and not approval_ok(cid, head):
            rows.append(f"{cid} @ {head}")
    return rows


def derive_head(cid: str, git=None, platform: str | None = None) -> tuple[str | None, str]:
    """(W-20261023-016، مرحلة ready_derive) الرأسُ المشتقّ من الفرع: الفرعُ المحلّيّ المسموح (claude/* أو w*) في مستودع المنصّة الذي في
    إيداعاته رمزُ البطاقة ولم يُدمج في origin/main. فرعٌ وحيدٌ ← رأسُه (8 خانات)؛ لا فرعَ أو أكثرُ من فرعٍ ← لا اشتقاق مع السبب.
    الاشتقاقُ لا يعتمد شيئاً: الاعتمادُ يبقى لـapproval_check على هذا الرأس بعينه، فرأسٌ مشتقٌّ بلا اعتمادٍ ينتظر."""
    git = git or push_approved._git
    platform = platform or PLATFORM_DIR
    if not _is_platform(platform, git):
        return None, "ليست بطاقةَ منصّة"
    cands = []
    for name, sha in _local_branches(platform, git):
        if not push_approved.PUMP_BRANCH_RE.match(name):
            continue
        rc, log = git(platform, "log", "-1", "--format=%H", f"--grep={cid}", name, "^origin/main")
        if not rc and log.strip():
            cands.append((name, sha))
    if not cands:
        return None, "لا فرعَ محلّيّاً بإيداعٍ يحمل رمزَها"
    if len(cands) > 1:
        return None, "التباس — أكثرُ من فرع: " + "، ".join(n for n, _ in cands)
    return cands[0][1][:8], cands[0][0]


def approve_pass(states: dict[str, dict], apply: bool, git=None, platform: str | None = None) -> list[str]:
    out: list[str] = []
    for cid, item in sorted(states.items()):
        if item.get("state") != "ready_for_review":
            continue
        head = ready_head(item)
        derived = False
        if not head:
            head, why = derive_head(cid, git, platform)
            derived = bool(head)
            if not head:
                out.append(f"{cid}: بلا رأسٍ معلَن ولا مشتقّ ({why}) — لا نقل")
                continue
        if not approval_ok(cid, head):
            cond = "visual_evidence" if "بصري" in approval_why(cid, head) else "head_unapproved"
            src = " (مشتقّ من الفرع)" if derived else ""
            out.append(f"{cid}: رأس {head}{src} بلا اعتمادٍ ثابت (أو ينقصه دليلٌ بصريّ) — {hand_off(cid, cond, item, apply)}")
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


MAX_IN_CI = 2  # أمر المالك 2026-10-22: طلبان فقط قيد الفحص معاً في المنصّة (لا تكدّس مشغّلات ولا إعادة فحوص)
PLATFORM_MARK = "shschool_mvp"  # مستودعُ المنصّة: مستودعاتُ الأدوات (maestro) لا فحوصَ ثقيلةً فيها فلا تُقيَّد


def _entry_pending(entry: dict) -> bool:
    """مدخلُ statusCheckRollup لم يكتمل: CheckRun بحالةٍ غير COMPLETED، أو StatusContext بحالة PENDING/EXPECTED."""
    if "status" in entry:
        return str(entry.get("status") or "").upper() != "COMPLETED"
    return str(entry.get("state") or "").upper() in ("PENDING", "EXPECTED")


def ci_in_flight(sh=None) -> int | None:
    """عددُ الطلباتِ المفتوحة غيرِ المسوّدة التي فحوصُها لم تكتمل؛ None إن تعذّرت القراءة (فيُؤجَّل الدفعُ ولا يُبنى على غياب)."""
    rc, out = (sh or _sh)(["gh", "pr", "list", "--state", "open", "--limit", "100", "--json", "number,isDraft,statusCheckRollup"], ac.REPO_DIR)
    if rc:
        return None
    try:
        data = json.loads(out)
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    return sum(
        1
        for pr in data
        if isinstance(pr, dict) and not pr.get("isDraft")
        and any(_entry_pending(e) for e in (pr.get("statusCheckRollup") or []) if isinstance(e, dict))
    )


def _is_platform(path: str, git) -> bool:
    rc, out = git(path, "remote", "get-url", "origin")
    return not rc and PLATFORM_MARK in out


def _log_once(text: str) -> None:
    """سطرُ سببِ التأجيل في flow_pump.log مرّةً لا في كلّ دورةٍ (idempotent): يُتخطّى إن كان آخرُ سطرٍ هو نفسُه."""
    try:
        last = LOG.read_text(encoding="utf-8").splitlines()[-1:] if LOG.exists() else []
        if last and last[0].endswith(text):
            return
        from datetime import datetime

        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {text}\n")
    except OSError:
        pass


PUSH_STATUS = {"pushed": "دُفع ✔", "dry": "يُدفع (عرض)", "refused": "✘ رُفض الدفع", "skipped": "تخطٍّ"}


def guard_passes(cid: str, tree: dict, items: dict[str, dict], git, approved=None) -> bool:
    """هل يقبل حارسُ الدفع (بشروط المضخّة: فرعٌ مسموح وإيصالُ prepush للرأس) هذه البطاقةَ الآن؟"""
    try:
        push_approved.guard(cid, tree["branch"], tree["path"], items, git, approved or push_approved.approval_ok,
                            push_approved.PUMP_BRANCH_RE, require_receipt=True)
    except (push_approved.PushRefused, ledger.LedgerError, OSError, KeyError):
        return False
    return True


def defer_for_ci(items: dict[str, dict], repos: list[str], git, busy_fn, *, ready=None,
                 approved=None) -> tuple[dict[str, dict], list[str]]:
    """(W-20261022-019) بطاقاتُ المنصّة لا تُدفع وفي المنصّة طلبان قيد الفحص: (ما يُدفع، أسطرُ التأجيل بسببه).
    السقفُ يشمل ما يُدفع في هذه الدورة نفسِها (المفتوحُ قيدَ الفحص + المدفوعُ الآن ≤ MAX_IN_CI)؛ ولا يُعاد فحصٌ آليّاً.
    الخانةُ تُحجز لما يقبله حارسُ الدفع وحدَه (`ready(cid, tree)`، الافتراضيّ guard_passes): بطاقةٌ سيرفضها الحارس (بلا إيصال مثلاً)
    تمرّ إلى المسح ليظهر سببُ رفضها ولا تأخذ خانةً، فلا تُجوِّع بطاقةً جاهزةً بعدها في الترتيب (W-20261027-031، 10-28)."""
    import push_watch  # noqa: PLC0415

    ready = ready or (lambda cid, tree: guard_passes(cid, tree, items, git, approved))
    keep: dict[str, dict] = {}
    lines: list[str] = []
    busy: int | None = None
    asked = False
    taken = 0
    for cid in sorted(items):
        want = (items[cid].get("approved_head") or "").strip()
        tree, _why = push_watch.find_tree(cid, want, repos, git, push_approved.PUMP_BRANCH_RE) if want else (None, "")
        if tree is None or not _is_platform(tree["path"], git):
            keep[cid] = items[cid]
            continue
        if not asked:
            busy, asked = busy_fn(), True
        if busy is None:
            why = "تعذّرت قراءةُ حالة الفحوص (gh)"
        elif busy + taken >= MAX_IN_CI:
            why = f"{busy} طلباً قيد الفحص" + (f" و{taken} يُدفع الآن" if taken else "") + f" (السقف {MAX_IN_CI})"
        else:
            keep[cid] = items[cid]
            taken += 1 if ready(cid, tree) else 0
            continue
        lines.append(f"{cid}: ⏸ يُؤجَّل الدفع — {why}")
    return keep, lines


def push_pass(states: dict[str, dict], apply: bool, repos: list[str] | None = None, path=None, git=None, approved=None, busy_fn=None) -> list[str]:
    """(D-450م) approved ← pushed عبر push_watch.scan بحرّاس push_approved كلّها، وفرعٍ claude/* أو w*، وإيصال prepush للرأس نفسه.
    busy_fn (W-20261022-019): دالّةٌ تعيد عددَ الطلبات قيد الفحص؛ معها تُؤجَّل بطاقاتُ المنصّة عند بلوغ السقف ويُسجَّل السبب."""
    items = {k: v for k, v in states.items() if v.get("state") == "approved"}
    if not items:
        return []
    import push_watch  # noqa: PLC0415
    import ready_mark  # noqa: PLC0415

    kw = {k: v for k, v in (("git", git), ("approved", approved)) if v is not None}
    where_repos = repos or ready_mark.candidate_repos(None)
    deferred: list[str] = []
    if busy_fn is not None:
        items, deferred = defer_for_ci(items, where_repos, git or push_approved._git, busy_fn, approved=approved)
        if apply:
            for line in deferred:
                _log_once("دفع: " + line)
    results = push_watch.scan(items, where_repos, apply, path, by=SENDER,
                              branch_re=push_approved.PUMP_BRANCH_RE, require_receipt=True, exempt_no_prepush=False, **kw) if items else []
    out, quiet = list(deferred), 0
    for r in results:
        if r["status"] == "skipped" and push_watch.QUIET in r["reason"]:
            quiet += 1
            continue
        where = f" {r['branch']}" if r.get("branch") else ""
        out.append(f"{r['card']}:{where} {PUSH_STATUS.get(r['status'], r['status'])} — {r['reason'][:160]}")
    if quiet:
        out.append(f"{quiet} بطاقةً معتمَدة بلا شجرةٍ هنا على رأسها بفرعٍ مسموح — لا دفع")
    return out


#: (W-20261023-016) إيصالُ prepush الآليّ: صورةُ Docker المشتقّة (tools/prepush_image/Dockerfile) تشغّل scripts/prepush_check.py للمنصّة
#: على نسخةٍ مركّبةٍ للقراءة، والمضخّةُ تكتب الإيصالَ من المضيف بعد رمز خروج 0 وحدَه (لا «غير مقيس» ولا فشل).
PREPUSH_IMAGE = "maestro-prepush:1"
#: بطاقةٌ واحدةٌ في الدورة: التشغيلُ يستغرق دقائق والقفلُ يُعدّ ميتاً بعد STALE_LOCK_S (900 ثانية)
PREPUSH_MAX = 1
PREPUSH_TIMEOUT_S = 780
GOV_PYTEST_TIMEOUT_S = 900  # إيصال الحوكمة البديل: pytest tools/ كاملاً (نحو ثلاث دقائق محلّياً)
PREPUSH_DB_IMAGE = "postgres:16-alpine"  # كـCI (native-postgres: postgres 16)؛ بيانات اعتماد اختبارٍ فقط، لا منفذَ على المضيف
PREPUSH_DB_WAIT = 40
PREPUSH_OK_LINE = "الفحوصُ السريعةُ ناجحة"
PREPUSH_ATTEMPTS = HERE.parent / "ledger" / "prepush_attempts.json"
#: مفتاحُ إيقاف المرحلة وحدَها: وجودُ الملف يعطّلها من أيّ مشغِّل
NO_PREPUSH = HERE.parent / "ledger" / "flow_pump.noprepush"


def _docker(cmd: list[str], timeout: int) -> tuple[int, str]:
    """(رمز الخروج، المخرَج)؛ عند المهلة تُقتل الحاويةُ باسمها ويعاد 124."""
    try:
        p = subprocess.run(["docker", *cmd], stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        if "--name" in cmd:
            subprocess.run(["docker", "rm", "-f", cmd[cmd.index("--name") + 1]], capture_output=True, timeout=60)
        return 124, "تجاوز المهلة"
    except OSError as exc:
        return 127, f"docker غير متاح: {exc}"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _image_present(docker) -> bool:
    rc, _ = docker(["image", "inspect", "--format", "ok", PREPUSH_IMAGE], 60)
    return rc == 0


def prepush_command(tree: str, gitdir: str, common: str, name: str, net: str) -> list[str]:
    """أمرُ docker run: الشجرةُ و.git الرئيس للقراءة فقط، على شبكةٍ داخليّةٍ لا خارجَ لها (فيها قاعدةُ الاختبار وحدَها)؛ GIT_DIR نسبةً إلى
    المركَّب. الإيصالُ لا يُكتب من الحاوية."""
    rel = os.path.relpath(gitdir, common).replace("\\", "/")
    git_dir = "/gitmain" if rel == "." else f"/gitmain/{rel}"
    runner = str(HERE / "prepush_image")
    return [
        "run", "--rm", "--name", name, "--network", net, "-e", "TEST_DB_HOST=db",
        "-e", "DJANGO_ALLOW_ASYNC_UNSAFE=1",  # كما في وظيفة axe-a11y في CI (quality-gate.yml): Playwright يستعمل حلقة greenlet تُخطئ حارسَ Django
        "-v", f"{tree}:/src:ro", "-v", f"{common}:/gitmain:ro", "-v", f"{runner}:/runner:ro",
        "-e", f"PREPUSH_GIT_DIR={git_dir}", "-e", "GIT_OPTIONAL_LOCKS=0", "-e", "HOME=/tmp",
        "-e", "GIT_CONFIG_COUNT=1", "-e", "GIT_CONFIG_KEY_0=safe.directory", "-e", "GIT_CONFIG_VALUE_0=*",
        PREPUSH_IMAGE, "sh", "/runner/entry.sh",
    ]


def run_with_db(docker, cmd_for, name: str, timeout: int, sleep=None) -> tuple[int, str]:
    """يشغّل أمرَ الفحص بقاعدة postgres:16 مؤقّتةٍ (كـCI) على شبكةٍ داخليّة بلا خروج؛ ويزيلهما دائماً. تعذّرُ القاعدة = فشلٌ لا نجاح."""
    import time  # noqa: PLC0415

    sleep = sleep or time.sleep
    net, pg = f"{name}-net", f"{name}-pg"
    docker(["rm", "-f", name, pg], 60)  # بقايا دورةٍ انقطعت (باسمنا نحن فقط)
    docker(["network", "rm", net], 60)
    try:
        rc, out = docker(["network", "create", "--internal", net], 60)
        if rc:
            return 1, "تعذّر إنشاءُ الشبكة الداخلية: " + out.strip()[-120:]
        rc, out = docker(["run", "-d", "--rm", "--name", pg, "--network", net, "--network-alias", "db", "--tmpfs", "/var/lib/postgresql/data",
                          "-e", "POSTGRES_USER=test_user", "-e", "POSTGRES_PASSWORD=test_pass", PREPUSH_DB_IMAGE], 120)
        if rc:
            return 1, "تعذّر تشغيلُ قاعدة الاختبار: " + out.strip()[-120:]
        for _ in range(PREPUSH_DB_WAIT):
            if docker(["exec", pg, "pg_isready", "-U", "test_user"], 30)[0] == 0:
                break
            sleep(1.5)
        else:
            return 1, "قاعدةُ الاختبار لم تجهز"
        return docker(cmd_for(net), timeout)
    finally:
        docker(["rm", "-f", pg], 60)
        docker(["network", "rm", net], 60)


def _attempts() -> dict:
    try:
        return json.loads(PREPUSH_ATTEMPTS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


#: (10-28) نسخةُ مشغّل prepush. محاولاتٌ سُجّلت بالصيغة القديمة (نصٌّ مجرّد) أو بمشغّلٍ أقدم تُعاد مرّةً: كانت المضخّةُ تُطلَق
#: بـDETACHED_PROCESS فيحمرّ pytest tools/ كلُّه بـWinError 6، ثمّ يُحجب الرأسُ «فاشلاً» للأبد بلا عيبٍ في شيفرته.
RUNNER_V = 2
#: فشلٌ بيئيّ (prepush_env) يُعاد بعد هذه الساعات ولو لم يتغيّر الرأس: علّةُ البيئة تزول بلا إيداع؛ والفحصُ الأحمر لا يُعاد حتى يتغيّر الرأس
ENV_RETRY_H = 2


def record_failure(tried: dict, key: str, why: str, cond: str, now=None) -> dict:
    from datetime import datetime  # noqa: PLC0415

    rec = {"why": why, "cond": cond, "v": RUNNER_V, "ts": (now or datetime.now().astimezone()).isoformat(timespec="seconds")}
    tried[key] = rec
    return rec


def standing_failure(rec, now=None) -> dict | None:
    """محاولةٌ فاشلةٌ تحجب الإعادةَ للرأس نفسه، أو None فيُعاد الفحص: الصيغةُ القديمة ونسخةُ مشغّلٍ أخرى تُعادان، والفشلُ البيئيّ
    يُعاد بعد ENV_RETRY_H، والفحصُ الأحمر في الشيفرة يحجب حتى يتغيّر الرأس."""
    from datetime import datetime, timedelta  # noqa: PLC0415

    if not isinstance(rec, dict) or rec.get("v") != RUNNER_V:
        return None
    if rec.get("cond") == "prepush_env":
        try:
            age = (now or datetime.now().astimezone()) - datetime.fromisoformat(str(rec.get("ts")))
        except (TypeError, ValueError):
            return None
        if age >= timedelta(hours=ENV_RETRY_H):
            return None
    return rec


def failure_detail(rec: dict, cid: str, head: str) -> str:
    """السببُ وموضعُ السجلّ في رسالة الإحالة: يعمل المالكُ بلا تشخيصٍ ولا سؤال."""
    return f"{rec.get('why', '')} — السجلّ ledger/prepush_{cid}_{head[:8]}.log"


def _pytest_run(path: str, timeout: int) -> tuple[int, str]:
    """(رمز الخروج، المخرَج) لـ pytest tools/ في شجرة الحوكمة؛ المهلةُ 124 وتعذّرُ التشغيل 127.
    stdin=DEVNULL صراحةً: دخلٌ موروثٌ باطل يُسقط كلَّ subprocess في الاختبارات بـWinError 6 فيحمرّ الفحصُ بلا عيبٍ في الشيفرة (10-28)."""
    try:
        p = subprocess.run([sys.executable, "-m", "pytest", "tools", "-q", "-p", "no:cacheprovider"], cwd=path,  # noqa: S603
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "تجاوز المهلة"
    except OSError as exc:
        return 127, f"pytest غير متاح: {exc}"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def governance_receipt(cid: str, path: str, head: str, git, tried: dict, pytest_run=None, timeout: int = GOV_PYTEST_TIMEOUT_S) -> str:
    """(W-20261026-018) مستودعُ الحوكمة بلا scripts/prepush_check.py: الإيصالُ البديل pytest tools/ أخضرَ للرأس نفسه في الشجرة النظيفة.
    لا يُكتب إلا برمز خروج 0 وبقاءِ الرأس ونظافةِ الشجرة بعد التشغيل؛ والفشلُ يُسجَّل لرأسه بشرطه (record_failure).
    يعيد سطرَ النتيجة المطبوع."""
    rc, gitdir = git(path, "rev-parse", "--absolute-git-dir")
    if rc or not gitdir.strip():
        return f"{cid}: ✘ تعذّرت قراءةُ مجلّد git للشجرة — لا إيصال بديل"
    code, log = (pytest_run or _pytest_run)(path, timeout)
    _, head_after = git(path, "rev-parse", "HEAD")
    _, dirty_after = git(path, "status", "--porcelain", "--untracked-files=no")
    if code == 0 and head_after.strip() == head and not dirty_after.strip():
        (Path(gitdir.strip()) / ledger.RECEIPT_NAME).write_text(
            json.dumps({"head": head[:8], "ok": True, "kind": push_approved.GOV_RECEIPT_KIND}), encoding="utf-8")
        _log_once(f"prepush-حوكمة: {cid} {head[:8]} ✔")
        return f"{cid}: ✔ pytest tools/ أخضر للرأس {head[:8]} — كُتب الإيصال البديل (حوكمة)"
    why = ("الرأس أو الشجرة تغيّر أثناء الفحص" if code == 0 else "تجاوز المهلة" if code == 124 else f"رمز الخروج {code}")
    tail = " | ".join((log or "").strip().splitlines()[-3:])[:300]
    record_failure(tried, f"{cid}:{head[:8]}", why, "prepush_env" if code == 0 else failure_cond(code, log))
    try:
        PREPUSH_ATTEMPTS.write_text(json.dumps(tried), encoding="utf-8")
        (PREPUSH_ATTEMPTS.parent / f"prepush_{cid}_{head[:8]}.log").write_text(log or "", encoding="utf-8")
    except OSError:
        pass
    _log_once(f"prepush-حوكمة: {cid} {head[:8]} ✘ {why}")
    return f"{cid}: ✘ pytest tools/ لم يُنتج إيصالاً بديلاً للرأس {head[:8]} — {why}: {tail}"


def prepush_pass(states: dict[str, dict], apply: bool, repos: list[str] | None = None, git=None, docker=None,
                 limit: int = PREPUSH_MAX, timeout: int = PREPUSH_TIMEOUT_S, pytest_run=None) -> list[str]:
    """(W-20261023-016) بطاقةٌ approved سيرفضها حارسُ الدفع لغياب إيصال prepush: يُشغَّل prepush_check في الحاوية، وإن خرج بـ0
    (كلُّ الحرّاس قيست ونجحت) كُتب الإيصالُ للرأس نفسه في مجلّد git للشجرة. غيرُ ذلك لا إيصال: الفشلُ وغيرُ المقيس يبقيان ظاهرَين.
    رأسٌ احمرّ فحصُه لا يُعاد حتى يتغيّر الرأس، والفشلُ البيئيّ يُعاد بعد ENV_RETRY_H (standing_failure، prepush_attempts.json).
    الفشلُ يُحال بسببه وسجلّه: فحصٌ أحمر إلى حامل البطاقة، وعلّةُ البيئة إلى الأتمتة (failure_cond). حدٌّ أقصى `limit` بطاقةً في الدورة."""
    import push_watch  # noqa: PLC0415
    import ready_mark  # noqa: PLC0415

    items = {k: v for k, v in states.items() if v.get("state") == "approved" and (v.get("approved_head") or "").strip()}
    if not items:
        return []
    git = git or push_approved._git
    docker = docker or _docker
    where_repos = repos or ready_mark.candidate_repos(None)
    tried, out, ran = _attempts(), [], 0
    for cid in sorted(items):
        want = items[cid]["approved_head"].strip()
        tree, _why = push_watch.find_tree(cid, want, where_repos, git, push_approved.PUMP_BRANCH_RE)
        if tree is None:
            out.append(f"{cid}: ⏭ لا شجرةَ على الرأس المعتمَد {want[:8]} لبطاقةٍ معتمَدة — لا إيصال ({_why})")
            continue
        path = tree["path"]
        rc, head = git(path, "rev-parse", "HEAD")
        head = head.strip()
        rc2, dirty = git(path, "status", "--porcelain", "--untracked-files=no")
        if rc or rc2 or not head or dirty.strip() or not same_head(head, want):
            out.append(f"{cid}: ⏭ الشجرةُ ليست على الرأس المعتمَد {want[:8]} نظيفةً — لا إيصال (حارسُ الدفع يرفضها بسببه)")
            continue
        if push_approved.receipt_problem(path, head, git) is None:
            continue  # الإيصالُ قائم
        key = f"{cid}:{head[:8]}"
        rec = standing_failure(tried.get(key))
        if rec:
            when = f"يُعاد بعد {ENV_RETRY_H} ساعة" if rec["cond"] == "prepush_env" else "يُعاد حين يتغيّر الرأس"
            owner = hand_off(cid, rec["cond"], items[cid], apply, detail=failure_detail(rec, cid, head))
            out.append(f"{cid}: prepush لم يُعَد للرأس {head[:8]} — {rec['why']} ({when}) {owner}")
            continue
        if ran >= limit:
            out.append(f"{cid}: ⏸ prepush في الدورة التالية (الحدّ {limit} في الدورة)")
            continue
        if not push_approved.has_prepush_tool(path):
            ran += 1
            if not apply:
                out.append(f"{cid}: يُشغَّل pytest tools/ إيصالاً بديلاً (حوكمة) للرأس {head[:8]} (عرض)")
                continue
            line = governance_receipt(cid, path, head, git, tried, pytest_run)
            rec = standing_failure(tried.get(key))
            if rec:
                line += " " + hand_off(cid, rec["cond"], items[cid], apply, detail=failure_detail(rec, cid, head))
            out.append(line)
            continue
        if not apply:
            out.append(f"{cid}: يُشغَّل prepush في الحاوية للرأس {head[:8]} (عرض)")
            ran += 1
            continue
        if not _image_present(docker):
            _log_once(f"prepush: الصورة {PREPUSH_IMAGE} غائبة — docker build -t {PREPUSH_IMAGE} tools/prepush_image")
            out.append(f"{cid}: ✘ صورة {PREPUSH_IMAGE} غائبة — docker build -t {PREPUSH_IMAGE} tools/prepush_image")
            break
        rc, gitdir = git(path, "rev-parse", "--absolute-git-dir")
        rc3, common = git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if rc or rc3 or not gitdir.strip() or not common.strip():
            out.append(f"{cid}: ✘ تعذّرت قراءةُ مجلّد git للشجرة — لا prepush")
            continue
        ran += 1
        name = f"prepush-{cid.lower()}-{head[:8]}"
        code, log = run_with_db(docker, lambda net: prepush_command(path, gitdir.strip(), common.strip(), name, net), name, timeout)
        # شرطُ الإيصال: رمز 0، وسطرُ النجاح الكامل، وخلوُّ المخرَج من «غير مقيس»، وبقاءُ الرأس ونظافةُ الشجرة بعد التشغيل
        _, head_after = git(path, "rev-parse", "HEAD")
        _, dirty_after = git(path, "status", "--porcelain", "--untracked-files=no")
        sound = code == 0 and PREPUSH_OK_LINE in log and "غير مقيس" not in log
        if sound and head_after.strip() == head and not dirty_after.strip():
            (Path(gitdir.strip()) / ledger.RECEIPT_NAME).write_text(json.dumps({"head": head[:8], "ok": True}), encoding="utf-8")
            out.append(f"{cid}: ✔ prepush نجح كاملاً للرأس {head[:8]} — كُتب الإيصال")
            _log_once(f"prepush: {cid} {head[:8]} ✔")
            continue
        why = "الرأس أو الشجرة تغيّر أثناء الفحص" if sound else (
            "تجاوز المهلة" if code == 124 else "غير مقيس (أداةٌ غائبة)" if code == 3 else f"رمز الخروج {code}")
        bad = [x.strip() for x in (log or "").splitlines() if x.lstrip().startswith(("✘", "؟"))]
        tail = (" | ".join(bad) or " | ".join((log or "").strip().splitlines()[-3:]))[:300]
        try:
            (PREPUSH_ATTEMPTS.parent / f"prepush_{cid}_{head[:8]}.log").write_text(log or "", encoding="utf-8")
        except OSError:
            pass
        rec = record_failure(tried, key, why, "prepush_env" if sound else failure_cond(code, log))
        PREPUSH_ATTEMPTS.write_text(json.dumps(tried), encoding="utf-8")
        owner = hand_off(cid, rec["cond"], items[cid], apply, detail=failure_detail(rec, cid, head))
        out.append(f"{cid}: ✘ prepush لم يُنتج إيصالاً للرأس {head[:8]} — {why}: {tail} {owner}")
        _log_once(f"prepush: {cid} {head[:8]} ✘ {why}")
    return out



#: (W-20261023-016) مرحلة الشجرة: بطاقةٌ معتمَدة بلا شجرةٍ على رأسها وفرعُها المحلّيّ موجود، فتُنشأ شجرةٌ عليه تحت مستودع المنصّة
PLATFORM_DIR = ac.REPO_DIR
TREE_MAX = 2
#: مفتاحُ إيقاف المرحلة وحدَها
NO_TREE = HERE.parent / "ledger" / "flow_pump.notree"


def _local_branches(repo: str, git) -> list[tuple[str, str]]:
    """[(الفرع المحلّيّ، رأسه الكامل)] لمستودع المنصّة."""
    rc, out = git(repo, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads")
    if rc:
        return []
    rows = []
    for ln in out.splitlines():
        parts = ln.split()
        if len(parts) == 2:
            rows.append((parts[0], parts[1]))
    return rows


def tree_pass(states: dict[str, dict], apply: bool, repos: list[str] | None = None, git=None, platform: str | None = None,
              limit: int = TREE_MAX) -> list[str]:
    """(W-20261023-016) بطاقةٌ approved بلا شجرةٍ هنا على رأسها: إن وُجد في مستودع المنصّة فرعٌ مسموحٌ (claude/* أو w*) رأسُه الرأسُ المعتمَد
    بالضبط وفي إيداعاته رمزُ البطاقة ولم يُدمج، أُنشئت عليه شجرةٌ `.claude/worktrees/pump-<البطاقة>` (git worktree add بلا -b ولا تعديلٍ
    لشجرةٍ قائمة) فتتولّاها مرحلتا prepush والدفع. لا فرعَ محلّيّاً على الرأس = تبليغٌ فقط. حدٌّ أقصى `limit` بطاقةً في الدورة، ولا رسائل."""
    import push_watch  # noqa: PLC0415
    import ready_mark  # noqa: PLC0415

    items = {k: v for k, v in states.items() if v.get("state") == "approved" and (v.get("approved_head") or "").strip()}
    if not items:
        return []
    git = git or push_approved._git
    platform = platform or PLATFORM_DIR
    if not _is_platform(platform, git):
        return []
    where_repos = repos or ready_mark.candidate_repos(None)
    branches: list[tuple[str, str]] | None = None
    out: list[str] = []
    absent: list[str] = []
    made = 0
    for cid in sorted(items):
        want = items[cid]["approved_head"].strip()
        tree, why = push_watch.find_tree(cid, want, where_repos, git, push_approved.PUMP_BRANCH_RE)
        if tree is not None or push_watch.QUIET not in why:
            continue  # لها شجرةٌ أو التباسٌ يبلّغه حارسُ الدفع
        if branches is None:
            branches = _local_branches(platform, git)
        cands = []
        for name, sha in branches:
            if not push_approved.PUMP_BRANCH_RE.match(name) or not push_approved.same_head(sha, want):
                continue
            rc, log = git(platform, "log", "-1", "--format=%H", f"--grep={cid}", name, "^origin/main")
            if not rc and log.strip():
                cands.append(name)
        if not cands:
            absent.append(cid)
            continue
        if len(cands) > 1:
            out.append(f"{cid}: التباس — أكثرُ من فرعٍ محلّيٍّ على الرأس {want[:8]} ({'، '.join(cands)}) — لا شجرة")
            continue
        dest = Path(platform) / ".claude" / "worktrees" / f"pump-{cid}"
        if dest.exists():
            out.append(f"{cid}: المسار {dest.as_posix()} موجودٌ — لا لمس")
            continue
        if made >= limit:
            out.append(f"{cid}: ⏸ الشجرة في الدورة التالية (الحدّ {limit} في الدورة)")
            continue
        made += 1
        if not apply:
            out.append(f"{cid}: تُنشأ شجرةٌ {dest.as_posix()} على الفرع {cands[0]} بالرأس {want[:8]} (عرض)")
            continue
        rc, msg = git(platform, "worktree", "add", str(dest), cands[0])
        out.append(f"{cid}: شجرةٌ على {cands[0]} بالرأس {want[:8]}: {'✔' if rc == 0 else '✘ ' + _tail(msg)}")
        _log_once(f"شجرة: {cid} {want[:8]} {'✔' if rc == 0 else '✘'}")
    if absent:
        out.append(f"{len(absent)} بطاقةً معتمَدة لا فرعَ محلّيّاً على رأسها في المنصّة — تبليغ فقط ({'، '.join(absent)})")
    return out


#: (W-20261023-016) مرحلة فتح الطلب: بطاقةٌ pushed بلا طلبٍ على فرعها
PLATFORM_SLUG = "sh-school/shschool_mvp"
OPENPR_MAX = 2
#: مفتاحُ إيقاف المرحلة وحدَها
NO_OPENPR = HERE.parent / "ledger" / "flow_pump.noopenpr"
BODY_MAX = 1500


def _remote_branches(repo: str, git) -> list[tuple[str, str]] | None:
    """[(الفرع البعيد، رأسه الكامل)] من origin؛ None إن تعذّرت القراءة."""
    rc, out = git(repo, "ls-remote", "--heads", "origin")
    if rc:
        return None
    rows = []
    for ln in out.splitlines():
        parts = ln.split()
        if len(parts) == 2 and parts[1].startswith("refs/heads/"):
            rows.append((parts[1][len("refs/heads/"):], parts[0]))
    return rows


def _pr_body(line: str, cid: str, item: dict) -> str:
    parts = [line, "", f"البطاقة: {cid}"]
    for label, key in (("المشكلة", "problem"), ("القبول", "accept")):
        text = " ".join(str(item.get(key) or "").split())
        if text:
            parts += ["", f"{label}: {text}"]
    parts += ["", "فُتح آلياً من مضخّة التدفّق بعد approval_check ✔ للرأس نفسه."]
    return "\n".join(parts)[:BODY_MAX]


def openpr_block(cid: str, head_full: str, files: list[str]) -> str | None:
    """سببُ منع فتح الطلب آليّاً (الفئاتُ الممنوعة: هجرات، أمن، طلبٌ واسع)؛ None إن لا مانع. يعيد استعمالَ merge_block ومحظوراتِه."""
    from risk_tier import classify_paths  # noqa: PLC0415

    why = merge_block(cid, {"files": [{"path": f} for f in files], "labels": [], "baseRefName": "main", "isDraft": False,
                            "changedFiles": len(files), "headRefOid": head_full})
    if why:
        return why
    if files and classify_paths(files)["category"] == "security" and not ac.security_approved(cid, head_full[:8]):
        return "مسارٌ أمنيّ بلا «أقرّ أمنياً» من المالك على الرأس"
    return None


def openpr_pass(states: dict[str, dict], prs: list[dict], apply: bool, git=None, sh=None, platform: str | None = None,
                limit: int = OPENPR_MAX) -> list[str]:
    """(W-20261023-016) بطاقةٌ pushed بلا طلبٍ مفتوحٍ أو مدموج: يُفتح طلبٌ إلى المنصّة من فرعها بعنوانٍ ووصفٍ من حقول البطاقة بالعربية
    وسطرِ الاعتماد، بشرط: رأسُ الفرع البعيد = رأسُ الاعتماد، approval_check ✔، والمساراتُ بلا هجراتٍ أو أمنٍ أو اتّساع. لا دمج ولا --auto
    (تتولّاه مرحلةُ الدمج بعد سطر الاعتماد وخضرة CI). يُسجَّل رقمُ الطلب ملاحظةً على البطاقة (ledger_sync يربط بالرأس). حدٌّ أقصى `limit` في الدورة."""
    import open_pr  # noqa: PLC0415

    items = {k: v for k, v in states.items() if v.get("state") == "pushed" and (v.get("approved_head") or "").strip()}
    if not items:
        return []
    git, sh = git or push_approved._git, sh or _sh
    platform = platform or PLATFORM_DIR
    pairs, _ = card_prs(states, prs)
    remote: list[tuple[str, str]] | None = None
    out: list[str] = []
    done = 0
    for cid in sorted(items):
        item, want = items[cid], items[cid]["approved_head"].strip()
        if cid in pairs:
            continue  # لها طلبٌ مفتوح
        if remote is None:
            remote = _remote_branches(platform, git)
            if remote is None:
                return out + ["تعذّرت قراءةُ فروع origin — لا فتحَ طلبات في هذه الدورة"]
        cands = [(n, sha) for n, sha in remote if push_approved.PUMP_BRANCH_RE.match(n) and push_approved.same_head(sha, want)]
        if len(cands) != 1:
            rmap = dict(remote)
            if len(cands) > 1:
                out.append(f"{cid}: التباس — أكثرُ من فرعٍ بعيدٍ على الرأس {want[:8]} ({'، '.join(n for n, _ in cands)}) — لا طلب")
            elif item.get("branch") and item["branch"] in rmap:
                out.append(f"{cid}: رأسُ الفرع البعيد {item['branch']} {rmap[item['branch']][:8]} يخالف رأسَ الاعتماد {want[:8]} — لا طلب")
            else:
                out.append(f"{cid}: لا فرعَ بعيداً مسموحاً على الرأس {want[:8]} — لا طلب {hand_off(cid, 'pushed_no_pr', item, apply)}")
            continue
        branch, full = cands[0]
        if any(p.get("headRefName") == branch or str(p.get("headRefOid") or "")[:8] == full[:8] for p in prs):
            continue
        rc, text = sh(["gh", "pr", "list", "--repo", PLATFORM_SLUG, "--head", branch, "--state", "all", "--json", "number,state,headRefOid"], platform)
        try:
            known = json.loads(text) if rc == 0 else None
        except ValueError:
            known = None
        if known is None:
            out.append(f"{cid}: تعذّرت قراءةُ طلبات الفرع {branch} (gh) — لا فتح")
            continue
        if any(same_head(str(p.get("headRefOid") or ""), want) or p.get("state") in ("OPEN", "MERGED") for p in known):
            continue  # لها طلبٌ مفتوحٌ أو مدموج (ledger_sync يتولّاه)
        if not approval_ok(cid, want[:8]):
            out.append(f"{cid}: رأس {want[:8]} بلا اعتمادٍ ثابت — لا طلب")
            continue
        rc, listing = sh(["gh", "api", f"repos/{PLATFORM_SLUG}/compare/main...{full}", "--paginate", "--jq", ".files[].filename"], platform)
        files = [f for f in listing.splitlines() if f.strip()] if rc == 0 else None
        if not files:
            out.append(f"{cid}: تعذّر قياسُ مسارات الفرع {branch} أو لا فرقَ عن main — لا طلب")
            continue
        why = openpr_block(cid, full, files)
        if why:
            out.append(f"{cid}: {branch} لا يُفتح آلياً — {why} {hand_off(cid, 'migrations', item, apply)}")
            continue
        line = approval_line(cid, want[:8], item)
        if line is None:
            out.append(f"{cid}: لا قولَ للمالك ولا تكليفَ مسجَّلاً على الرأس {want[:8]} — لا طلب")
            continue
        if done >= limit:
            out.append(f"{cid}: ⏸ فتحُ الطلب في الدورة التالية (الحدّ {limit} في الدورة)")
            continue
        done += 1
        title = open_pr.make_title(item, cid, None).strip()
        if not apply:
            out.append(f"{cid}: يُفتح طلبٌ من {branch} بالرأس {want[:8]} بعنوان «{title}» (عرض)")
            continue
        fd, tmp = tempfile.mkstemp(prefix="pump_pr_", suffix=".md")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(_pr_body(line, cid, item))
            rc, msg = sh(["gh", "pr", "create", "--repo", PLATFORM_SLUG, "--base", "main", "--head", branch, "--title", title, "--body-file", tmp], platform)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        m = re.search(r"/pull/(\d+)", msg or "")
        if rc != 0 or not m:
            out.append(f"{cid}: فتحُ الطلب من {branch}: ✘ {_tail(msg)}")
            continue
        try:
            ledger.add_note(cid, f"فُتح الطلب #{m.group(1)} آلياً من الفرع {branch} بالرأس {want[:8]} (مضخّة التدفّق؛ ledger_sync يربطه بالرأس)", SENDER)
        except ledger.LedgerError as exc:
            out.append(f"{cid}: #{m.group(1)} فُتح ✔ لكنّ تسجيلَه في الدفتر ✘ {str(exc)[:100]}")
            continue
        out.append(f"{cid}: #{m.group(1)} فُتح من {branch} بالرأس {want[:8]} ✔")
        _log_once(f"طلب: {cid} #{m.group(1)} ✔")
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


MAIN_RUN_EVENTS = ("push", "merge_group")  # تشغيلاتُ ما بعد الدمج: فحصُ main ونشرُه وطابورُ الدمج (لا تعليقاتُ الطلبات)


def main_runs_in_flight(sh=None) -> int | None:
    """عددُ تشغيلات main الجاريةِ أو المنتظِرة (دمجٌ في الطابور أو فحصٌ أو نشرٌ بعد دمج)؛ None إن تعذّرت القراءة."""
    rc, out = (sh or _sh)(["gh", "run", "list", "--limit", "40", "--json", "status,event,headBranch"], ac.REPO_DIR)
    if rc:
        return None
    try:
        data = json.loads(out)
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    return sum(
        1
        for r in data
        if isinstance(r, dict)
        and r.get("event") in MAIN_RUN_EVENTS
        and str(r.get("status") or "").lower() in ("queued", "in_progress", "waiting", "pending", "requested")
        and (r.get("headBranch") == "main" or str(r.get("headBranch") or "").startswith("gh-readonly-queue/main"))
    )


def serial_block(num, prs: list[dict], armed_now: list, sh) -> str | None:
    """(W-20261022-020، «طلبٌ واحد لكلّ نشر») سببُ عدم تفعيل --auto الآن: طلبٌ آخر فُعِّل عليه الدمجُ التلقائيّ (في الطابور)،
    أو فُعِّل في هذه الدورة، أو تشغيلٌ جارٍ على main (فحصٌ أو نشر). تعذّرُ القراءة يمنع ولا يخمّن."""
    if armed_now:
        return f"فُعِّل الدمجُ الآليّ على #{armed_now[0]} في هذه الدورة — طلبٌ واحدٌ لكلّ نشر"
    for other in prs:
        if other.get("number") != num and not other.get("isDraft") and other.get("autoMergeRequest"):
            return f"#{other.get('number')} في الطابور (دمجٌ آليٌّ مفعَّل) — طلبٌ واحدٌ لكلّ نشر"
    busy = main_runs_in_flight(sh)
    if busy is None:
        return "تعذّرت قراءةُ تشغيلات main (gh) — لا تفعيلَ بلا علم"
    if busy:
        return f"{busy} تشغيلاً جارياً على main (طابورٌ أو فحصٌ أو نشر) — طلبٌ واحدٌ لكلّ نشر"
    return None


def merge_pass(states: dict[str, dict], prs: list[dict], apply: bool, sh=None) -> list[str]:
    """(D-450م) دمجٌ آليّ عند خضرة CI لطلبٍ سطرُ اعتماده سليم: `--auto` مقيَّدٌ بالرأس (`--match-head-commit`) فلا يُدمج غيرُه.
    (W-20261022-020) وطلبٌ واحدٌ فقط لكلّ نشر: لا تفعيلَ والطابورُ أو main مشغولان (serial_block)."""
    sh = sh or _sh
    out: list[str] = []
    armed_now: list = []
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
        wait = serial_block(num, prs, armed_now, sh)
        if wait:
            out.append(f"{cid}: #{num} ⏸ يؤجَّل الدمجُ الآليّ — {wait}")
            continue
        if not apply:
            out.append(f"{cid}: #{num} يُدمج آليّاً عند خضرة CI بالرأس {head} (عرض)")
            armed_now.append(num)  # يحجب غيرَه في العرض أيضاً ليطابق ما سيجري
            continue
        rc, msg = sh(["gh", "pr", "merge", str(num), "--squash", "--auto", "--match-head-commit", full], ac.REPO_DIR)
        if rc != 0:
            out.append(f"{cid}: #{num} دمجٌ آليّ عند خضرة CI: ✘ {_tail(msg)}")
        elif auto_merge_armed(num, sh):
            armed_now.append(num)
            out.append(f"{cid}: #{num} دمجٌ آليّ عند خضرة CI: ✔")
        else:
            out.append(f"{cid}: #{num} نجح الأمرُ لكنّ الدمجَ الآليّ غيرُ مفعَّلٍ على GitHub (autoMergeRequest فارغ) — لا تأشير")
    return out


def auto_merge_armed(num, sh) -> bool:
    """W-20261022-009: نجاحُ `gh pr merge --auto` وحدَه لا يكفي (سجّلت المضخّةُ ✔ لطلباتٍ بلا autoMergeRequest)؛ تُقرأ حالةُ الطلب بعدها:
    ✔ فقط إن كان الدمجُ الآليّ مفعَّلاً فعلاً أو الطلبُ مدموجاً. قراءةٌ فاشلةٌ أو غيرُ مفهومةٍ = غيرُ مفعَّل."""
    rc, text = sh(["gh", "pr", "view", str(num), "--json", "autoMergeRequest,state"], ac.REPO_DIR)
    if rc != 0:
        return False
    try:
        data = json.loads(text)
    except ValueError:
        return False
    return bool(data.get("autoMergeRequest")) or data.get("state") == "MERGED"


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
    ap.add_argument("--no-tree", action="store_true", help="بلا إنشاء شجرةٍ للبطاقات المعتمَدة بلا شجرة")
    ap.add_argument("--no-open-pr", action="store_true", help="بلا فتح طلبٍ لبطاقات pushed بلا طلب")
    ap.add_argument("--no-prepush", action="store_true", help="بلا إنتاج إيصال prepush آليّاً في الحاوية")
    ap.add_argument("--no-line", action="store_true", help="بلا كتابة سطر الاعتماد في الطلب")
    ap.add_argument("--no-merge", action="store_true", help="بلا الدمج الآليّ")
    ap.add_argument("--no-ci", action="store_true", help="بلا إعادة الفحوص العالقة")
    ap.add_argument("--no-root-follow", action="store_true", help="بلا تقديم الجذر إلى main بعد الدمج")
    a = ap.parse_args(argv)

    def load() -> dict[str, dict]:
        return {k: v for k, v in ledger.reduce_state(ledger.load_events()).items() if k not in a.skip}

    def reload(states: dict[str, dict]) -> dict[str, dict]:
        return load() if a.apply else states  # ما نُقل يُقرأ من الدفتر قبل المرحلة التالية؛ والعرضُ لا ينقل شيئاً

    states = load()
    for line in approve_pass(states, a.apply):
        print("اعتماد: " + line)
    waiting = owner_list(states)
    if waiting:
        print(f"قائمة اعتماد المالك ({len(waiting)}): " + "؛ ".join(waiting))
    states = reload(states)
    prs: list[dict] = []
    prs_ok = True
    if any(v.get("state") in PR_STATES and v.get("approved_head") for v in states.values()):
        got = open_prs()
        if got is None:
            print("طلبات: تعذّرت قراءةُ الطلبات المفتوحة (gh) — لا إعفاءَ برأس الطلب ولا سطرَ ولا دمج في هذه الدورة")
        prs_ok = got is not None
        prs = got or []
        for note in card_prs(states, prs)[1]:
            print("طلبات: " + note)
    for line in waive_pass(states, a.apply, prs):
        print("إعفاء: " + line)
    states = reload(states)
    if NO_TREE.exists():
        print(f"شجرة: معطَّلة بمفتاح ({NO_TREE.name})")
    elif not a.no_tree and not a.no_push:
        for line in tree_pass(states, a.apply):
            print("شجرة: " + line)
    if NO_PREPUSH.exists():
        print(f"prepush: معطَّل بمفتاح ({NO_PREPUSH.name})")
    elif not a.no_prepush and not a.no_push:
        for line in prepush_pass(states, a.apply):
            print("prepush: " + line)
    if not a.no_push:
        for line in push_pass(states, a.apply, busy_fn=ci_in_flight):
            print("دفع: " + line)
        states = reload(states)
    if NO_OPENPR.exists():
        print(f"طلب: معطَّل بمفتاح ({NO_OPENPR.name})")
    elif not a.no_open_pr and prs_ok:
        for line in openpr_pass(states, prs, a.apply):
            print("طلب: " + line)
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
    if not a.no_root_follow:
        for line in root_follow_pass(a.apply):
            print("جذر: " + line)
    print("— مرحلة النشر (ledger_sync) —")
    if a.skip:
        orig = ledger_sync.plan
        ledger_sync.plan = lambda st, *r, **k: orig({c: v for c, v in st.items() if c not in a.skip}, *r, **k)
    orig_move = ledger.move  # ledger_sync لا يمرّر by؛ يسجّلها المضخّة باسم 0101 (مسجِّلٌ مسموح لـmerged/published)
    ledger.move = lambda *args, **kw: orig_move(*args, **{"by": SENDER, **kw})
    rc = ledger_sync.cycle(a.apply, 80)
    print("— صحة المضخّة (تصعيد الركود) —")
    try:
        evs = ledger.load_events()
        st = ledger.reduce_state(evs)
        for line in pump_health.escalation_pass({c: v for c, v in st.items() if c not in a.skip}, a.apply):
            print("تصعيد: " + line)
        if a.apply and pump_health.write_daily(st, evs):
            print("صحة: كُتبت لقطةُ اليوم")
    except Exception as exc:  # الرصدُ لا يُسقط الدورة
        print(f"صحة المضخّة: تعذّر ({exc})")
    if a.apply:
        from datetime import datetime

        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} rc={rc}\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
