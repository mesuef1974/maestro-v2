"""بذرٌ محدودٌ ومُعلَن لمعاينة W-20261002-020 (رصدُ المعلّم الفعليّ واعتمادُه) على 8500.

يُشغَّل داخل حاوية الويب بـ`manage.py shell` (stdin) ومتغيّر بيئة `W020_ACTION`:

    up   : حصّةٌ واحدةٌ (scheduled) بتاريخ اليوم بتوقيت الدوحة لشعبةٍ **في جناحٍ** وفيها طلبةٌ نشطون، بمعلّمها الحاليّ،
           من 05:00 إلى 23:30 كي لا يتوقّف نجاحُ المعاينة على ساعةِ فتحها؛ وتُوسَم في `notes` بـ«[معاينة W-020]».
           ثمّ يطبع الروابطَ والأدوار اللازمةَ للمعاينة (معرّفاتٌ وأدوارٌ فقط، بلا أسماء).
    accounts : (أمرُ المالك 2026-10-03) حساباتٌ **وهميّةٌ موسومةٌ** للأدوار الثلاثة (معلّم، حاملُ جناح admin_supervisor، نائب vice_admin)
           على قاعدة هذه الحاوية وحدَها: رقمُ دخولٍ اصطناعيٌّ بنمط الحارس واسمٌ بوسم «[وهميّ W-020]»، وكلمةُ مرورٍ واحدةٌ لكلّها بتحديد المالك
           (`FAKE_PASSWORD`). يُسنَد المعلّمُ للحصّة والحاملُ لجناح شعبتها (والسابقُ يُحفظ في notes) والنائبُ بعضويّةٍ في المدرسة.
    who  : قراءةٌ فقط: يطبع حساباتِ المعاينة الموجودةَ بالأدوار الصحيحة.
    down : يمحو **إدخالاتِ ما وُسم وقراراتِه وصفوفَ حضورِه** ثمّ الحصّةَ الموسومة — والمحوُ عبر `erase_attendance_ledger`
           (المسارُ الوحيد المسموح له بحذف السجلّ الملحق فقط) لطلبة الحصّة الموسومة وحدَهم. سطورُ التدقيق تبقى.
           **الحساباتُ الوهميّةُ تبقى** (الشرط السابع، W-20261003-022): تبقى ما بقيت قاعدةُ المعاينة وتُحذف بإعادة بذرها.

لا يمسّ أيَّ بيانٍ آخر. والتشغيلُ ثانيةً لـup بلا تغيير (متساوي الأثر).
"""

import datetime as dt
import os
import re

from django.db import transaction
from django.utils import timezone

from core.models import ClassGroup, Membership, StudentEnrollment
from operations.attendance_entries import erase_attendance_ledger
from operations.models import AttendanceEntry, Session, StudentAttendance

MARK = "[معاينة W-020]"
ACTION = os.environ.get("W020_ACTION", "")
BASE = "http://localhost:8500"


def _marked():
    return Session.objects.filter(notes__contains=MARK)


def _teacher_of(group):
    last = (
        Session.objects.filter(class_group=group, teacher__isnull=False)
        .order_by("-date", "-start_time")
        .select_related("teacher")
        .first()
    )
    if last is not None:
        return last.teacher
    membership = (
        Membership.objects.filter(school=group.school, is_active=True, role__name="teacher")
        .select_related("user")
        .order_by("joined_at", "id")
        .first()
    )
    return membership.user if membership is not None else None


def _role_of(user, school):
    return (
        Membership.objects.filter(school=school, is_active=True, user=user)
        .values_list("role__name", flat=True)
        .first()
    )


def up():
    today = timezone.localdate()
    existing = _marked().filter(date=today).first()
    if existing is None:
        group = (
            ClassGroup.objects.filter(
                wing__isnull=False,
                wing__is_active=True,
                wing__supervisor__isnull=False,
                is_active=True,
                enrollments__is_active=True,
            )
            .exclude(section__iendswith="ESE")
            .distinct()
            .order_by("-academic_year", "grade", "section")
            .first()
        )
        if group is None:
            print("لا شعبةَ في جناحٍ نشطٍ بمشرفٍ فيها طلبةٌ نشطون — لم يُنشأ شيء")
            return
        teacher = _teacher_of(group)
        if teacher is None:
            print("لا معلّمَ نشطاً في المدرسة يُسند إليه — لم يُنشأ شيء")
            return
        existing = Session.objects.create(
            school=group.school,
            class_group=group,
            teacher=teacher,
            date=today,
            start_time=dt.time(5, 0),
            end_time=dt.time(23, 30),
            status="scheduled",
            notes=f"{MARK} حصّةُ معاينةٍ تُمحى بـdown",
        )
        print("أُنشئت حصّةُ المعاينة.")
    else:
        print("حصّةُ المعاينة قائمةٌ لليوم — لا تغيير.")

    group = existing.class_group
    wing = group.wing
    holder = wing.current_supervisor(on_date=today)
    student_ids = list(
        StudentEnrollment.objects.filter(class_group=group, is_active=True).values_list(
            "student_id", flat=True
        )[:3]
    )
    print(f"SESSION_ID        = {existing.id}")
    print(f"الشعبة            = {group.short_label} — {group.academic_year} (جناح: {wing.code})")
    print(f"التاريخ والنافذة  = {existing.date} {existing.start_time:%H:%M}–{existing.end_time:%H:%M}")
    print(f"١) المعلّم يُدخل   = {BASE}/teacher/attendance/{existing.id}/  (user_id {existing.teacher_id}، الدور: {_role_of(existing.teacher, existing.school)})")
    print(f"٢) الحاملُ يعتمد   = {BASE}/teacher/attendance/approvals/  (user_id {holder.pk if holder else None}، الدور: {_role_of(holder, existing.school) if holder else None})")
    print(f"٣) النائب يقرأ     = {BASE}/teacher/attendance/unapproved/?hours=1  (دورٌ: vice_admin أو principal)")
    print(f"٤) تصحيحٌ دون معاينة = {BASE}/teacher/attendance/{existing.id}/correct/  (الحامل)")
    print(f"طلبةٌ للتجربة     = user_id {student_ids}")
    print("المتوقَّع: المعلّمُ يُدخل «غائب» لطالبٍ فيظهر «بانتظار الاعتماد» ولا يُحتسب غياباً؛ الحاملُ يرى الإدخالَ في طابوره فيعتمد أو يرفض بسبب؛")
    print("بعد الاعتماد يظهر الرصدُ المعتمَد؛ والمعلّمُ نفسُه لا يعتمد (403)؛ ومعلّمٌ آخر لا يدخل صفحةَ الحصّة (403).")
    print("تنبيه: «غائب» بعد الاعتماد يستدعي فحصَ عتبات الغياب وقد يُنشئ تنبيهاً — جرّب «حاضر» و«متأخّر» أوّلاً.")


#: حساباتٌ وهميّةٌ موسومةٌ بوضوح (أمرُ المالك 2026-10-03): رقمُ دخولٍ اصطناعيٌّ بنمط الحارس (خمسةُ أصفارٍ متتالية) واسمٌ يبدأ بالوسم.
FAKE_PREFIX = "[وهميّ W-020] "
FAKE_ACCOUNTS = {
    "teacher": ("29000009101", "معلّم المعاينة", "teacher", "المعلّم (يُدخل)"),
    "holder": ("29000009102", "حامل جناح المعاينة", "admin_supervisor", "الحامل (يعتمد ويصحّح)"),
    "vice": ("29000009103", "نائب المعاينة", "vice_admin", "النائب (التقرير)"),
}
#: كلمةُ المرور الواحدة لحساباتٍ وهميّةٍ على 8500 المحلّيّة وحدَها — بتحديد المالك صراحةً («كلها بكلمة سر واحدة 123»، 2026-10-03).
FAKE_PASSWORD = "123"
PREV_RE = re.compile(r"\[prev_supervisor=([0-9a-f-]+|none)\]")


def guard_problems(bind, expected_db, actual_db):
    """الشرطُ السابع (تعديل 0105 أ): لا بذرَ إلّا بربطٍ على 127.0.0.1 وفي قاعدة المعاينة بفحصٍ إيجابيّ؛ يعيد قائمةَ المشكلات (فارغةٌ = سليم)."""
    problems = []
    if bind != "127.0.0.1":
        problems.append("PREVIEW_BIND ليس 127.0.0.1")
    if not expected_db:
        problems.append("PREVIEW_DB_NAME غيرُ مضبوط")
    elif actual_db != expected_db:
        problems.append("اسمُ القاعدة لا يساوي PREVIEW_DB_NAME")
    if "preview" not in (actual_db or "").lower():
        problems.append("اسمُ القاعدة لا يحوي preview")
    return problems


def _fake_users():
    from core.models import CustomUser

    return CustomUser.objects.filter(
        national_id__in=[v[0] for v in FAKE_ACCOUNTS.values()], full_name__startswith=FAKE_PREFIX
    )


def accounts():
    """ينشئ حساباتٍ وهميّةً موسومةً للأدوار الثلاثة على حصّة المعاينة (على قاعدة هذه الحاوية وحدَها) ويُسند إليها دورَها:

    المعلّمُ الوهميّ معلّمٌ فعليٌّ لحصّة المعاينة، والحاملُ الوهميّ مشرفُ جناح شعبتها (يُحفظ المشرفُ السابقُ في `notes` ليعيده down)،
    والنائبُ الوهميّ بعضويّةٍ في المدرسة نفسِها. كلمةُ المرور `FAKE_PASSWORD` لكلّها بأمر المالك. متساوي الأثر: حسابٌ قائمٌ لا يُنشأ ثانيةً.
    """
    from core.models import CustomUser, Role
    from django.conf import settings

    problems = guard_problems(
        os.environ.get("PREVIEW_BIND", ""),
        os.environ.get("PREVIEW_DB_NAME", ""),
        settings.DATABASES["default"]["NAME"],
    )
    if problems:
        disabled = _fake_users().filter(is_active=True).update(is_active=False)
        print(f"رُفض البذر: {'؛ '.join(problems)} — عُطّل {disabled} حسابٌ وهميٌّ قائم")
        raise SystemExit(3)
    session = _marked().order_by("-date").first()
    if session is None:
        print("لا حصّةَ معاينةٍ موسومة — شغّل W020_ACTION=up أوّلاً")
        return
    school = session.school
    wing = session.class_group.wing
    created = {}
    with transaction.atomic():
        for key, (national_id, name, role_name, _label) in FAKE_ACCOUNTS.items():
            user = CustomUser.objects.filter(national_id=national_id).first()
            if user is None:
                user = CustomUser(
                    national_id=national_id,
                    full_name=f"{FAKE_PREFIX}{name}",
                    email=f"w020.{key}@preview.invalid",
                    is_active=True,
                    must_change_password=False,
                )
                user.set_password(FAKE_PASSWORD)
                user.save()
            elif not user.full_name.startswith(FAKE_PREFIX):
                print(f"رقمُ الدخول {national_id} لحسابٍ غيرِ وهميّ — توقّف بلا تغيير")
                raise SystemExit(1)
            role, _ = Role.objects.get_or_create(school=school, name=role_name)
            Membership.objects.get_or_create(
                user=user, school=school, role=role, defaults={"is_active": True}
            )
            Membership.objects.filter(user=user, school=school, role=role).update(is_active=True)
            created[key] = user

        if session.teacher_id != created["teacher"].id:
            session.original_teacher_id = session.original_teacher_id or session.teacher_id
            session.teacher = created["teacher"]
        if wing.supervisor_id != created["holder"].id:
            previous = str(wing.supervisor_id) if wing.supervisor_id else "none"
            if not PREV_RE.search(session.notes):
                session.notes = f"{session.notes} [prev_supervisor={previous}]"
            wing.supervisor = created["holder"]
            wing.save(update_fields=["supervisor"])
        session.save(update_fields=["teacher", "original_teacher", "notes"])

    for key, (national_id, _name, role_name, label) in FAKE_ACCOUNTS.items():
        print(f"{label:<26} رقمُ الدخول = {national_id} · الدور = {role_name} · كلمةُ المرور = {FAKE_PASSWORD}")
    print(f"SESSION_ID = {session.id}")
    print(f"روابط: المعلّم {BASE}/teacher/attendance/{session.id}/ · الحامل {BASE}/teacher/attendance/approvals/ · النائب {BASE}/teacher/attendance/unapproved/?hours=1")


def _restore_wing_supervisors(sessions):
    """يعيد مشرفَ الجناح الذي كان قبل الإسناد الوهميّ — فقط إن كان الحاليُّ حساباً وهميّاً."""
    fake_ids = set(_fake_users().values_list("id", flat=True))
    for session in sessions:
        wing = session.class_group.wing
        match = PREV_RE.search(session.notes)
        if wing is None or match is None or wing.supervisor_id not in fake_ids:
            continue
        wing.supervisor_id = None if match.group(1) == "none" else match.group(1)
        wing.save(update_fields=["supervisor"])


@transaction.atomic
def down():
    sessions = list(_marked())
    _restore_wing_supervisors(sessions)
    ids = [s.id for s in sessions]
    students = {
        entry.student
        for entry in AttendanceEntry.objects.filter(session_id__in=ids).select_related("student", "school")
    }
    erased = 0
    for student in students:
        school = AttendanceEntry.objects.filter(student=student, session_id__in=ids).first().school
        summary = erase_attendance_ledger(student, actor=None, school=school)
        erased += sum(v for v in summary.values() if isinstance(v, int))
    removed_rows = StudentAttendance.objects.filter(session_id__in=ids).delete()[0]
    for session in sessions:
        session.delete()
    print(
        f"حُذفت {len(sessions)} حصّةٌ موسومةٌ و{removed_rows} صفُّ حضورٍ ومُحي من السجلّ الملحق {erased} صفّاً لطلبتها؛ "
        "وأُعيد مشرفُ الجناح؛ والحساباتُ الوهميّةُ باقيةٌ (تُحذف بإعادة بذر قاعدة المعاينة). غيرُ ذلك لم يُمسّ."
    )


def who():
    """يطبع حساباتِ المعاينة الموجودةَ بالأدوار الصحيحة لحصّة المعاينة — بلا إنشاءِ حسابٍ ولا كلمة مرور.

    المعلّمُ الفعليّ للحصّة، وحاملُ جناح شعبتها اليوم، ونائبٌ/مديرٌ في المدرسة. يبدّل المالكُ بينها بتسجيل الخروج ثمّ الدخولِ بالحساب،
    ويضبط كلمةَ مرور الحساب الذي يريده بنفسه داخل الحاوية: `manage.py changepassword <رقمُ الدخول>`. (حساباتُ المعاينة مزروعةٌ لا حقيقيّة.)
    """
    session = _marked().order_by("-date").first()
    if session is None:
        print("لا حصّةَ معاينةٍ موسومة — شغّل W020_ACTION=up أوّلاً")
        return
    holder = session.class_group.wing.current_supervisor(on_date=session.date)
    vice = (
        Membership.objects.filter(
            school=session.school, is_active=True, role__name__in=("vice_admin", "principal")
        )
        .select_related("user", "role")
        .order_by("role__name", "joined_at")
        .first()
    )
    rows = [
        ("المعلّم (يُدخل)", session.teacher, _role_of(session.teacher, session.school)),
        ("الحامل (يعتمد ويصحّح)", holder, _role_of(holder, session.school) if holder else None),
        ("النائب/المدير (التقرير)", vice.user if vice else None, vice.role.name if vice else None),
    ]
    for label, user, role in rows:
        login = getattr(user, "national_id", None) if user else None
        print(f"{label:<26} رقمُ الدخول = {login} · الدور = {role}")
    print("الخطوات: سجّل الخروج من حساب المطوّر (محجوبٌ عمداً: D-128م) ← manage.py changepassword <رقمُ الدخول> داخل الحاوية ← ادخل بالحساب.")


if ACTION == "up":
    up()
elif ACTION == "who":
    who()
elif ACTION == "accounts":
    accounts()
elif ACTION == "down":
    down()
else:
    print("حدّد W020_ACTION=up أو accounts أو who أو down")
