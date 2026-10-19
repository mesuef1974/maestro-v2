#!/usr/bin/env python3
"""حقائقُ من المصدر بأمرٍ واحد — يمنع نقلَ حالةٍ من مرجعٍ محلّيٍّ قديمٍ أو تخمينِ مسار (D-107م).

كلُّ أمرٍ قراءةٌ فقط. القاعدةُ: لا أذكر حالةَ طلبٍ أو فرعٍ أو تنبيهٍ أو رابطٍ قبل أن أشغّل هذه الأداة عليه.

    python ground_truth.py pr 761
    python ground_truth.py branch claude/dev-messages-nav-tab
    python ground_truth.py alert 116
    python ground_truth.py url /wings/ [--base http://localhost:8500]
    python ground_truth.py card W-20260930-005
    python ground_truth.py spec W-20261019-011   # يفحص مراجعَ المواصفة (مساراتٌ وطلباتٌ) على المصدر؛ يخرج بـ1 إن غاب مرجع
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_DIR = "D:/shschool_mvp"
SLUG = "sh-school/shschool_mvp"
SLUGS = (SLUG, "mesuef1974/maestro-v2")  # طلباتُ المنصّة وطلباتُ أدوات المايسترو
_URL = re.compile(r"https?://\S+")
# ASCII فقط: حرفٌ عربيٌّ لاصقٌ بالمسار («وscripts/x.py») ليس منه
PATH_RE = re.compile(r"(?<![A-Za-z0-9_/.\-])((?:[A-Za-z0-9_.\-]+/)*[A-Za-z0-9_\-]+\.(?:py|yml|yaml|html|css|js|json|md|sh|txt))(?::\d+)?")
PR_RE = re.compile(r"(?<![\w&])#(\d{2,5})\b")


def source_line() -> str:
    """مسارُ owner_confirmations.md المقروء مطلقاً وتاريخُ آخر تعديل، ليُكشف الاستعمالُ الصامتُ لنسخةٍ قديمةٍ في شجرةٍ أخرى."""
    f = ROOT / "owner_confirmations.md"
    if not f.exists():
        return f"المصدر المقروء: {f} — غير موجود"
    import datetime  # noqa: PLC0415
    return f"المصدر المقروء: {f} — آخر تعديل {datetime.datetime.fromtimestamp(f.stat().st_mtime):%Y-%m-%d %H:%M}"


def run(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def gh_json(args: list[str]) -> object | None:
    code, out = run(["gh", *args], cwd=REPO_DIR)
    if code != 0:
        print(f"  تعذّر الاستعلام: {out.strip()[:200]}")
        return None
    return json.loads(out)


def cmd_pr(num: str) -> None:
    d = gh_json(["pr", "view", num, "--json",
                 "number,state,mergeable,mergedAt,headRefName,headRefOid,isDraft,autoMergeRequest,body,title"])
    if not d:
        return
    body = d.get("body") or ""
    approval = [ln.strip() for ln in body.splitlines() if "اعتُمد" in ln or "اعتمد المالك" in ln]
    print(f"#{d['number']} {d['title'][:70]}")
    print(f"  الحالة: {d['state']} | قابليّةُ الدمج: {d['mergeable']} | مسوّدة: {d['isDraft']}")
    print(f"  الفرع: {d['headRefName']} @ {d['headRefOid'][:8]}")
    if d["state"] == "OPEN":
        print(f"  دمجٌ آليّ مفعَّل: {'نعم' if d.get('autoMergeRequest') else 'لا'}  (قد يتأخّر العرضُ: لا يُعتدّ بالـnull وحده)")
    print(f"  سطرُ الاعتماد: {approval[0] if approval else '— غائب'}")
    if d.get("mergedAt"):
        print(f"  اندمج: {d['mergedAt']}")
    code, out = run(["gh", "pr", "checks", num], cwd=REPO_DIR)
    states: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            states[parts[1]] = states.get(parts[1], 0) + 1
    print(f"  فحوصُ CI: {states or 'لا شيء'}")
    failing = [ln.split("	")[0] for ln in out.splitlines() if "	" in ln and ln.split("	")[1] == "fail"]
    if failing:
        print(f"  >> أحمر: {', '.join(failing)} — الدمجُ الآليّ لن يتمّ حتى تُصلَح (أرفق هذا السطرَ بأيّ «فُتح/مفعَّل/اندمج»)")


def cmd_branch(name: str) -> None:
    name = name.removeprefix("origin/")
    code, local = run(["git", "rev-parse", "--verify", "--quiet", name], cwd=REPO_DIR)
    local = local.strip() if code == 0 else ""
    code, remote = run(["git", "ls-remote", "origin", f"refs/heads/{name}"], cwd=REPO_DIR)
    remote_sha = remote.split()[0] if remote.strip() else ""
    print(f"الفرع {name}")
    print(f"  محلّيّ: {local[:8] or '— غيرُ موجود'}")
    print(f"  على GitHub (ls-remote مباشر): {remote_sha[:8] or '— غيرُ مدفوع'}")
    if local and remote_sha:
        print(f"  متطابقان: {'نعم' if local == remote_sha else 'لا — يختلف محلّيّاً عن البعيد'}")
    prs = gh_json(["pr", "list", "--state", "all", "--head", name, "--json", "number,state,mergedAt"])
    print(f"  طلباتُ الدمج: {prs if prs else 'لا طلبَ قطّ'}")
    merged = [p for p in (prs or []) if p.get("state") == "MERGED"]
    opened = [p for p in (prs or []) if p.get("state") == "OPEN"]
    if remote_sha and not prs:
        verdict = "مدفوعٌ بلا أيّ طلب دمج"
    elif remote_sha and opened:
        verdict = f"مدفوعٌ وطلبُه #{opened[0]['number']} مفتوح"
    elif not remote_sha and merged:
        verdict = f"اندمج (#{merged[0]['number']}) وحُذف الفرعُ البعيد بعده — طبيعيّ"
    elif not remote_sha and local:
        verdict = "محلّيٌّ فقط لم يُدفع قطّ — GitHub لا يعرف عنه شيئاً"
    elif remote_sha:
        verdict = "مدفوع، وطلبُه مغلق"
    else:
        verdict = "غيرُ موجودٍ محلّيّاً ولا بعيداً"
    print(f"  >> الخلاصة: {verdict}")
    code, wt = run(["git", "worktree", "list", "--porcelain"], cwd=REPO_DIR)
    cur = None
    owner = "—"
    for line in wt.splitlines():
        if line.startswith("worktree "):
            cur = line.split(" ", 1)[1]
        elif line.startswith("branch ") and line.endswith("/" + name):
            owner = cur or "—"
    print(f"  الشجرةُ التي تحمله: {owner}")


def cmd_alert(num: str) -> None:
    d = gh_json(["api", f"repos/{SLUG}/code-scanning/alerts/{num}"])
    if not d:
        return
    loc = d.get("most_recent_instance", {}).get("location", {})
    print(f"تنبيهُ CodeQL #{d['number']} — {d['rule']['id']} ({d['rule'].get('security_severity_level')})")
    print(f"  الحالة: {d['state']} | استُبعد: {d.get('dismissed_reason')} | أُصلح: {d.get('fixed_at')}")
    print(f"  الموضع: {loc.get('path')}:{loc.get('start_line')}")


def cmd_url(path: str, base: str) -> None:
    # Git Bash يحوّل «/wings/» إلى «C:/Program Files/Git/wings/» قبل وصوله إلى بايثون (MSYS_NO_PATHCONV)
    path = re.sub(r"^[A-Za-z]:/Program Files/Git", "", path.replace("\\", "/"))
    path = "/" + path.lstrip("/")
    # curl وحده مضلِّل: غيرُ المسجَّل يُحال إلى الدخول (302) حتى لو كان المسارُ غيرَ موجود (404 بعد الدخول).
    # فالحكمُ من مُحلِّل المسارات في Django نفسِه داخل حاوية المعاينة المركزيّة.
    snippet = (
        "from django.urls import resolve, Resolver404\n"
        "try:\n"
        f"    r = resolve({path!r}); print('RESOLVED', r.view_name or r.func.__name__)\n"
        "except Resolver404:\n"
        "    print('NOT_FOUND')\n"
    )
    code, out = run(["docker", "exec", "schoolos-main-preview-web-1", "python", "manage.py", "shell", "-c", snippet])
    verdict = next((ln for ln in out.splitlines() if ln.startswith(("RESOLVED", "NOT_FOUND"))), None)
    print(f"{path}")
    if verdict is None:
        print(f"  تعذّر الحلُّ من Django (الحاويةُ متوقّفة؟): {out.strip()[:150]}")
    elif verdict.startswith("RESOLVED"):
        print(f"  >> المسارُ موجودٌ في urls: {verdict.split(' ', 1)[1]}")
    else:
        print("  >> المسارُ غيرُ موجودٍ في urls (سيعطي 404 بعد الدخول) — لا تذكره")
    code, out = run(["curl", "-s", "-o", "NUL", "-w", "%{http_code} %{redirect_url}", base.rstrip("/") + path])
    print(f"  curl (للعلم فقط): {out.strip() or 'لا ردّ'}")


def cmd_card(code_: str) -> None:
    code, out = run([sys.executable, str(ROOT / "tools" / "ledger.py"), "show", code_])
    try:
        d = json.loads(out)
    except json.JSONDecodeError:
        print(out.strip()[:300])
        return
    print(f"{d['id']} [{d['priority']}] الحالة: {d['state']} منذ {d.get('state_ts', d.get('created'))}")
    print(f"  {d['problem'][:150]}")
    for n in d.get("notes", [])[-3:]:
        print(f"  ملاحظة {n['ts'][:16]}: {n['text'][:140]}")


def spec_references(item: dict) -> list[tuple[str, str]]:
    """مراجعُ المواصفة القابلةُ للفحص: (نوع، قيمة) من ref.path وsource_of_truth فقط (ملفّات files_allowed قد تكون جديدةً فلا تُفحص)."""
    text = " ".join([str((item.get("ref") or {}).get("path", "")), str(item.get("source_of_truth", ""))])
    text = _URL.sub(" ", text)
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for kind, rx in (("path", PATH_RE), ("pr", PR_RE)):
        for m in rx.finditer(text):
            key = (kind, m.group(1))
            if key not in seen:
                seen.add(key)
                out.append(key)
    return out


def default_path_exists(path: str) -> bool:
    """موجودٌ في main للمنصّة (git) أو في مجلّد المايسترو."""
    if "/" not in path:  # اسمُ ملفٍّ بلا مجلّد: يكفي أن يوجد في أيّ مجلّد
        code, out = run(["git", "ls-tree", "-r", "--name-only", "origin/main"], cwd=REPO_DIR)
        if code == 0 and any(n == path or n.endswith("/" + path) for n in out.splitlines()):
            return True
        return any(ROOT.glob(f"**/{path}"))
    code, _ = run(["git", "cat-file", "-e", f"origin/main:{path}"], cwd=REPO_DIR)
    return code == 0 or (ROOT / path).exists()


def default_pr_state(num: str) -> str | None:
    """حالةُ الطلب في أحد المستودعين؛ None إن لم يوجد في أيٍّ منهما."""
    for slug in SLUGS:
        code, out = run(["gh", "pr", "view", num, "--repo", slug, "--json", "state", "--jq", ".state"])
        if code == 0 and out.strip():
            return f"{out.strip()} ({slug.split('/')[1]})"
    return None


def check_references(item: dict, path_exists=default_path_exists, pr_state=default_pr_state) -> list[tuple[str, str, bool, str]]:
    """(نوع، قيمة، سليم؟، تفصيل) لكلّ مرجعٍ في المواصفة؛ الفاحصان قابلان للحقن للاختبار."""
    rows = []
    for kind, value in spec_references(item):
        if kind == "path":
            ok = bool(path_exists(value))
            rows.append((kind, value, ok, "موجود" if ok else "غيرُ موجود في main ولا في المايسترو"))
        else:
            state = pr_state(value)
            rows.append((kind, f"#{value}", state is not None, state or "لا طلبَ بهذا الرقم"))
    return rows


def cmd_spec(code_: str) -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    import ledger  # noqa: PLC0415

    item = ledger.reduce_state(ledger.load_events()).get(code_)
    if not item:
        print(f"بطاقةٌ غيرُ موجودة: {code_}")
        sys.exit(1)
    print(f"{code_}: " + ledger.spec_status(item))
    rows = check_references(item)
    if not rows:
        print("  لا مراجعَ قابلةً للفحص في ref.path وsource_of_truth")
    for kind, value, ok, detail in rows:
        print(f"  {'✔' if ok else '✘'} {kind}: {value} — {detail}")
    if any(not ok for _, _, ok, _ in rows):
        print("  >> مرجعٌ غائبٌ: لا تبنِ على هذه المواصفة قبل تصحيحه")
        sys.exit(1)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="kind", required=True)
    for k in ("pr", "branch", "alert", "card", "spec"):
        sub.add_parser(k).add_argument("target")
    u = sub.add_parser("url")
    u.add_argument("target")
    u.add_argument("--base", default="http://localhost:8500")
    a = ap.parse_args()
    print(source_line())
    {"pr": cmd_pr, "branch": cmd_branch, "alert": cmd_alert, "card": cmd_card, "spec": cmd_spec}.get(a.kind, lambda t: None)(a.target) \
        if a.kind != "url" else cmd_url(a.target, a.base)


if __name__ == "__main__":
    main()
