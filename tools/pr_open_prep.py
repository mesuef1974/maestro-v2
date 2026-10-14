#!/usr/bin/env python3
"""تجهيزُ فتح طلب الدمج بفحوصٍ آليّة قبل `gh pr create` (أمر المالك «باشر» D-429م، بنودٌ 1 و2 و3).

    python pr_open_prep.py W-20261013-001 --repo D:/shschool_mvp/.claude/worktrees/w0702-chart-ready
    python pr_open_prep.py W-20261013-001 --line-only      # يطبع سطرَ الاعتماد وحدَه لإلصاقه في الوصف

ثلاثةُ فحوصٍ بهذا الترتيب، وأوّلُ فشلٍ يوقف الفتح:
  (٢) رأسُ الفرع المحلّيّ = رأسُ الفرع على GitHub (مدفوعٌ فعلاً) = رأسٌ ثابتٌ اعتمادُه بـ`approval_check.py card <بطاقة> --head <رأس>`
      (يشمل تنازلاتِ 0501 المسجَّلة في الدفتر)؛
  (٣) `git merge-tree --write-tree` بين الأساس (`origin/main` افتراضاً) والرأس: تعارضٌ يُسمّي الملفّاتِ ولا يُفتح الطلب؛
  (١) سطرُ الاعتماد الجاهز للوصف: «اعتُمد من المالك على 8500 — <التاريخ> — الرأس <sha8>» (الصيغةُ في docs/governance/flow.md البند 7).

رموز الخروج: 0 سليم، 3 اعتمادٌ غيرُ ثابتٍ على هذا الرأس، 4 الفرعُ غيرُ مدفوعٍ أو رأسُه يخالف المحلّيّ، 5 تعارضٌ مع الأساس، 2 خطأُ استعمال.
قراءةٌ فقط: لا يدفع ولا يفتح طلباً ولا يكتب في الدفتر. والتاريخُ من آخر اعتمادٍ أو تنازلٍ في الدفتر (بتوقيت الدوحة)، وإلا اليوم.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
DOHA = ZoneInfo("Asia/Qatar")
#: ما يدلّ في ملاحظة الدفتر على اعتمادٍ أو تنازلٍ بالرأس (يطابق ما يقرؤه approval_check).
APPROVAL_NOTE = re.compile(r"اعتمد|اعتماد")
WAIVER_NOTE = re.compile(r"^(\(\d{4}\)\s*)?استثناءُ رأس")
LINE_TEMPLATE = "اعتُمد من المالك على 8500 — {date} — الرأس {head8}"


def run(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "")


def ledger_card(card: str) -> dict:
    _code, out = run([sys.executable, str(TOOLS / "ledger.py"), "show", card])
    try:
        data, _ = json.JSONDecoder().raw_decode(out.lstrip())
    except ValueError:
        return {}
    return data


def approval_date(card: dict, today: datetime | None = None) -> tuple[str, str]:
    """(التاريخ بالدوحة، مصدرُه). الأحدثُ بين أحداث الاعتماد وملاحظاتِ الاعتماد؛ وإلا اليوم.

    التنازلاتُ (`استثناءُ رأس…` بتوقيع 0501) لا تحدّد التاريخَ: السطرُ يقول «اعتُمد من المالك» فتاريخُه تاريخُ الاعتماد لا تاريخُ نقله إلى رأسٍ تافه.
    """
    stamps = [str(a.get("ts", "")) for a in card.get("approvals", []) if a.get("ts")]
    for note in card.get("notes", []):
        text = str(note.get("note", note.get("text", "")))
        if note.get("ts") and APPROVAL_NOTE.search(text) and not WAIVER_NOTE.search(text):
            stamps.append(str(note["ts"]))
    parsed = []
    for s in stamps:
        try:
            parsed.append(datetime.fromisoformat(s).astimezone(DOHA))
        except ValueError:
            continue
    if parsed:
        return max(parsed).date().isoformat(), "آخر اعتمادٍ في الدفتر"
    now = (today or datetime.now(DOHA)).astimezone(DOHA)
    return now.date().isoformat(), "لا اعتمادَ مؤرَّخاً في الدفتر — تاريخُ اليوم"


def merge_conflicts(repo: str, base: str, head: str) -> tuple[bool, list[str], str]:
    """(نظيف؟، ملفّاتُ التعارض، رسالةُ خطأٍ إن فشل الأمرُ نفسُه). يستعمل git merge-tree (لا يمسّ الشجرة ولا الفهرس)."""
    proc = subprocess.run(
        ["git", "merge-tree", "--write-tree", "--name-only", "--no-messages", base, head],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode == 0:
        return True, [], ""
    if proc.returncode == 1 and proc.stdout.strip():  # التعارضُ يطبع شجرةً أولاً؛ ورمز 1 بلا خرجٍ خطأُ مرجع
        lines = [ln.strip() for ln in proc.stdout.splitlines()[1:] if ln.strip()]
        return False, lines, ""
    return False, [], (proc.stderr or proc.stdout or f"رمز الخروج {proc.returncode}").strip()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("card", help="رمز البطاقة W-YYYYMMDD-NNN")
    ap.add_argument("--repo", default=".", help="مجلّد شجرة العمل (الافتراضيّ الحاليّ)")
    ap.add_argument("--branch", help="اسمُ الفرع البعيد (الافتراضيّ فرعُ الشجرة الحاليّ)")
    ap.add_argument("--base", default="origin/main", help="الأساس للمقارنة بـmerge-tree")
    ap.add_argument("--no-fetch", action="store_true", help="لا تجلب الأساس قبل الفحص")
    ap.add_argument("--line-only", action="store_true", help="اطبع سطرَ الاعتماد وحدَه عند النجاح")
    a = ap.parse_args()
    repo = a.repo

    code, head = run(["git", "rev-parse", "HEAD"], cwd=repo)
    if code != 0:
        print("✘ ليس مجلّدَ git:", repo)
        return 2
    head = head.strip()
    h8 = head[:8]
    branch = a.branch or run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)[1].strip()

    # تحذيرُ تسمية الفرع برمز البطاقة (R5، W-20261014-008): لا يحجب شيئاً
    try:
        sys.path.insert(0, str(TOOLS))
        import branch_name_check

        warn = branch_name_check.warning_for(branch, a.card, branch_name_check.load_cards())
        if warn:
            print(warn)
    except Exception:  # التحذيرُ لا يُسقط الفتح
        pass

    # (٢) المدفوعُ هو المحلّيّ، والاعتمادُ على هذا الرأس
    _c, remote_out = run(["git", "ls-remote", "origin", f"refs/heads/{branch}"], cwd=repo)
    remote = remote_out.split()[0] if remote_out.strip() else ""
    if not remote:
        print(f"✘ الفرع {branch} غيرُ مدفوعٍ إلى GitHub.")
        return 4
    if remote != head:
        print(f"✘ رأسُ الفرع على GitHub {remote[:8]} يخالف رأسَ الشجرة المحلّيّة {h8}: ادفع، أو أنت على فرعٍ آخر.")
        return 4
    code, out = run([sys.executable, str(TOOLS / "approval_check.py"), "card", a.card, "--head", h8])
    if code != 0:
        print(f"✘ الاعتمادُ غيرُ ثابتٍ للرأس {h8} (رمز approval_check {code}):")
        print(out.strip())
        return 3

    # (٣) التعارضُ مع الأساس
    if not a.no_fetch and "/" in a.base:
        remote_name, ref = a.base.split("/", 1)
        run(["git", "fetch", remote_name, ref], cwd=repo)
    clean, files, err = merge_conflicts(repo, a.base, head)
    if err:
        print("✘ فشل git merge-tree:", err)
        return 2
    if not clean:
        print(f"✘ تعارضٌ بين {h8} و{a.base} في {len(files)} ملفّاً — أعِد الأساسَ قبل فتح الطلب:")
        for f in files:
            print("  -", f)
        return 5

    card = ledger_card(a.card)
    date, source = approval_date(card)
    line = LINE_TEMPLATE.format(date=date, head8=h8)
    if a.line_only:
        print(line)
        return 0
    print(f"✔ الفرعُ {branch} مدفوعٌ على {h8}، والاعتمادُ ثابتٌ له، ولا تعارضَ مع {a.base}.")
    print("سطرُ الاعتماد للوصف:")
    print(line)
    print(f"(التاريخ من: {source})")
    waivers = [n for n in card.get("notes", []) if WAIVER_NOTE.search(str(n.get("note", n.get("text", ""))))]
    if waivers:
        print(f"تنبيه: الرأسُ وصل بـ{len(waivers)} تنازلٍ بتوقيع 0501 — ذكرُه في الوصف أمانةٌ، ولا يغيّر السطرَ.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
