"""حساباتُ معاينةٍ **دائمةٌ** على 8500 المحلّيّة — مشغِّلُ المضيف (W-20261003-022، قرارُ المالك D-167م 2026-10-03: «الحسابات كلها على المحلي
ولا تحقن في الانتاج»). تشغّلها 0501 وحدَها بإذن المالك. المرجع: docs/preview_accounts_permanent_2026-10-03.md.

    python preview_accounts.py sync  [--dry-run]    # يبذر/يصحّح العشرةَ (متساوي الأثر) عبر أمر المنصّة preview_accounts --sync
    python preview_accounts.py check [--dry-run]    # يفحص: (أ) المنفذُ على 127.0.0.1 وحدَه — وإن فشل **عُطّلت الحساباتُ** والرمز 3 (ب) اسمُ القاعدة (ج) بقاءُ الحسابات فعّالةً بلا حسابٍ غيرِ معلَن
    python preview_accounts.py down  [--dry-run]    # حذفٌ صريحٌ للحسابات الموسومة (لا يجري تلقائياً، ولا يُمنع بفشل المنفذ)

**المنطقُ في كود المنصّة لا هنا**: `core/preview_accounts.py` (القائمةُ المغلقةُ العشرةُ والوسمُ المركَّب) و`manage.py preview_accounts` (الحارسُ والبذرُ
والفحص). فهذه الأداةُ مشغِّلٌ رقيقٌ يتحقّق من المنفذ على المضيف ثمّ يستدعي الأمرَ داخل الحاوية — فلا تتكرّر القائمةُ ولا الشروطُ في موضعين.

الكلمةُ **ليست في هذا الملفّ**: من `PREVIEW_ACCOUNTS_PASSWORD` في بيئة المضيف، وإلّا من الملفّ المحلّيّ غير المتتبَّع `tools/.preview_accounts.env`؛
وتُمرَّر إلى الحاوية بالاسم `-e PREVIEW_ACCOUNTS_PASSWORD` فتُقرأ من بيئة المضيف ولا تظهر في argv. ولا كلمةَ افتراضيّة (غيابُها رفضٌ).

لا إنذارَ بالتقادم: الحساباتُ دائمةٌ بقرار المالك (يُستبدل شرطُ 0104 السابع بالفحص أعلاه). والجدولةُ الدائمةُ لهذا الفحص لا تُفعَّل بلا إذن المالك.
يلزم أن يكون كودُ الفرع W-20261003-023 في الحاوية (مدموجاً في main أو مثبَّتاً) وإلّا فلا أمرَ `preview_accounts` وتفشل الأداةُ بوضوح.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

def _active_web_container() -> str:
    """حاويةُ الويب الجاريةُ لـ8500: المعاينةُ تتناوب بين `-a-web-1` و`-b-web-1` (لا اسمَ ثابتَ بعد 2026-10)؛ وغيابُها يُبقي الاسمَ القديمَ فيفشل الفحصُ صراحةً."""
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=20
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        out = []
    for name in out:
        if re.fullmatch(r"schoolos-main-preview(-[ab])?-web-1", name):
            return name
    return "schoolos-main-preview-web-1"


CONTAINER = os.environ.get("PREVIEW_CONTAINER") or _active_web_container()
HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_ENV = os.path.join(HERE, ".preview_accounts.env")
PASSWORD_VAR = "PREVIEW_ACCOUNTS_PASSWORD"  # اسمُ المتغيّر لا قيمتُه

# حذفٌ صريحٌ داخل الحاوية: الحارسُ نفسُه (إعدادُ معاينة وقاعدةٌ تحوي preview) ثمّ حذفُ الموسومين بالوسم المركَّب من كود المنصّة.
DOWN_SCRIPT = r'''
from django.db import transaction
from core import preview_accounts as pa
from core.management.commands.preview_accounts import environment_problems
from core.models import AuditLog, CustomUser, Membership

problems = environment_problems()
if problems:
    print("رُفض: " + "؛ ".join(problems)); raise SystemExit(3)
removed = deactivated = 0
for user in list(CustomUser.objects.filter(pa.preview_accounts_q())):
    account_id = user.pk
    Membership.objects.filter(user=user).delete()
    try:
        with transaction.atomic():
            user.delete()
        removed += 1
    except Exception:
        user.is_active = False
        user.set_unusable_password()
        user.save(update_fields=["is_active", "password"])
        deactivated += 1
    AuditLog.log(user=None, action="delete", model_name="other", object_id=account_id,
                 object_repr="حسابُ معاينةٍ دائم — حذفٌ صريح", changes={}, school=None)
print(f"حُذف {removed} وعُطّل {deactivated} من حسابات المعاينة الموسومة")
'''


# تعطيلٌ وقائيٌّ عند فشل شرط المنفذ (حكمُ 0104 P2): لا يحذف ولا يغيّر كلمةً — `is_active=False` للوسم المركَّب وحدَه، ويعمل بلا حارس بيئةٍ
# عمداً (التعطيلُ آمنٌ في أيّ قاعدة، وحاجتُه عند الخطر نفسِه).
DISABLE_SCRIPT = r'''
from core import preview_accounts as pa
from core.models import CustomUser

count = CustomUser.objects.filter(pa.preview_accounts_q(), is_active=True).update(is_active=False)
print(f"عُطّل {count} حساباً من حسابات المعاينة الموسومة")
'''


def verify_loopback(docker_port_output: str) -> bool:
    """كلُّ ربطٍ منشورٍ على 127.0.0.1 — وأيُّ 0.0.0.0 أو [::] أو عنوانٍ آخر أو فارغٍ يُرفض."""
    lines = [ln.strip() for ln in docker_port_output.splitlines() if ln.strip()]
    if not lines:
        return False
    for line in lines:
        match = re.search(r"->\s*([^\s]+):(\d+)\s*$", line)
        if not match or match.group(1) != "127.0.0.1":
            return False
    return True


def read_password() -> str | None:
    value = os.environ.get(PASSWORD_VAR)
    if value:
        return value
    if os.path.exists(LOCAL_ENV):
        with open(LOCAL_ENV, encoding="utf-8") as handle:
            for line in handle:
                key, _, rest = line.strip().partition("=")
                if key == PASSWORD_VAR and rest:
                    return rest
    return None


def _run(cmd: list[str], *, stdin: str | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, encoding="utf-8", env=env)


def _port_is_loopback(dry: bool) -> tuple[bool, str]:
    cmd = ["docker", "port", CONTAINER]
    if dry:
        print("DRY:", " ".join(cmd))
        return True, ""
    out = _run(cmd)
    return out.returncode == 0 and verify_loopback(out.stdout), f"{out.stdout}{out.stderr}"


def _check_port(dry: bool) -> None:
    """يرفض (الرمز 3) إن لم يكن المنفذُ على 127.0.0.1 وحدَه — للأوامر التي لا تعمل إلّا في وضعٍ سليم (`sync`)."""
    ok, detail = _port_is_loopback(dry)
    if not ok:
        print(f"رُفض: منفذُ الحاوية «{CONTAINER}» غيرُ مربوطٍ على 127.0.0.1 وحدَه (أو تعذّر التحقّق):\n{detail}")
        raise SystemExit(3)


def _manage(args: list[str], dry: bool, password: str | None = None, stdin: str | None = None) -> int:
    cmd = ["docker", "exec", "-i"]
    if password is not None:
        cmd += ["-e", PASSWORD_VAR]  # بالاسم: القيمةُ من بيئة المضيف لا من argv
    cmd += [CONTAINER, "python", "manage.py", *args]
    if dry:
        print("DRY:", " ".join(cmd))
        return 0
    env = dict(os.environ)
    if password is not None:
        env[PASSWORD_VAR] = password
    out = _run(cmd, stdin=stdin, env=env)
    sys.stdout.write(out.stdout)
    if out.returncode != 0:
        sys.stderr.write(out.stderr[-800:])
    return out.returncode


def cmd_sync(dry: bool) -> int:
    print(f"الحاوية: {CONTAINER}")
    password = read_password()
    if not password and not dry:
        print(f"رُفض: لا كلمةَ مرور — عيّن {PASSWORD_VAR} في بيئة المضيف أو tools/.preview_accounts.env")
        return 7
    _check_port(dry)
    return _manage(["preview_accounts", "--sync"], dry, password)


def cmd_check(dry: bool) -> int:
    """(أ) المنفذُ على 127.0.0.1 وحدَه [هنا]، (ب) اسمُ القاعدة و(ج) بقاءُ الحسابات فعّالةً بلا حسابٍ غيرِ معلَن [داخل الحاوية].

    **إن فشل (أ) تُعطَّل الحساباتُ فوراً** (`is_active=False` للوسم المركَّب) ثمّ يخرج بالرمز 3 برسالة «عُطّل» — فعند الخطر نفسِه
    (منفذٌ على 0.0.0.0) لا تبقى حساباتٌ بكلمةٍ ضعيفةٍ فعّالةً (حكمُ 0104 P2).
    """
    print(f"الحاوية: {CONTAINER}")
    ok, detail = _port_is_loopback(dry)
    if not ok:
        print(f"خطر: منفذُ الحاوية «{CONTAINER}» غيرُ مربوطٍ على 127.0.0.1 وحدَه (أو تعذّر التحقّق):\n{detail}")
        _manage(["shell"], dry, stdin=DISABLE_SCRIPT)
        print("عُطّلت حساباتُ المعاينة الموسومة احترازاً — أعِد الربطَ على 127.0.0.1 ثمّ شغّل sync لإعادة تفعيلها.")
        return 3
    code = _manage(["preview_accounts", "--check"], dry)
    return 2 if code else 0


def cmd_down(dry: bool) -> int:
    """الحذفُ الصريحُ **لا يُمنع** بفشل المنفذ (حكمُ 0104 P2) — يُحذَّر فقط ثمّ يُنفَّذ."""
    print(f"الحاوية: {CONTAINER}")
    ok, detail = _port_is_loopback(dry)
    if not ok:
        print(f"تحذير: المنفذُ ليس على 127.0.0.1 وحدَه (أو تعذّر التحقّق) — يُنفَّذ الحذفُ رغم ذلك:\n{detail}")
    if dry:
        print("DRY: docker exec -i", CONTAINER, "python manage.py shell  [stdin: DOWN_SCRIPT]")
        return 0
    return _manage(["shell"], dry, stdin=DOWN_SCRIPT)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser =argparse.ArgumentParser(prog="preview_accounts.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("sync", "check", "down"):
        sub.add_parser(name).add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return {"sync": cmd_sync, "check": cmd_check, "down": cmd_down}[args.cmd](args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
