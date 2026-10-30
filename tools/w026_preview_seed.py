"""بذرٌ محدودٌ ومُعلَن لمعاينة W-20261002-026 على 8500 — حصّةٌ واحدةٌ لشعبة 07/ESE بتاريخ اليوم، وعكسُها.

يُشغَّل داخل حاوية الويب بـ`manage.py shell` (stdin) ومتغيّراتِ بيئة:

    up   : إنشاءُ حصّةٍ واحدةٍ (scheduled) بتاريخ اليوم بتوقيت الدوحة لشعبة ESE **أيِّ صفٍّ** بلا جناحٍ وفيها طلبةٌ
           نشطون (الأحدثُ عاماً أوّلاً)، بمعلّمها الحاليّ (معلّمِ أحدثِ حصّةٍ لها، وإلّا مُسنَدِها، وإلّا خانةِ جدولها)، من 05:00 إلى 23:30 كي لا
           يتوقّف نجاحُ المعاينة على ساعةِ فتحها.
           وتُوسَم في `notes` بـ«[معاينة W-026]» فيُعرف ويُعكَس. ثمّ يطبع ما يلزم للمعاينة.
    down : حذفُ الحصص الموسومة وصفوفِ حضورها فقط (لا غير). سطورُ التدقيق تبقى (لا تُمحى بحكم PDPPL م.19).

لا يمسّ أيَّ بيانٍ آخر. ولا يطبع أسماءً (معرّفاتٌ وأدوارٌ فقط). والتشغيلُ ثانيةً لـup بلا تغيير (متساوي الأثر).
"""

import datetime as dt
import os

from django.utils import timezone

from core.models import ClassGroup, Membership, StudentEnrollment
from operations.models import ScheduleSlot, Session, StudentAttendance, SubjectClassAssignment

MARK = "[معاينة W-026]"
ACTION = os.environ.get("W026_ACTION", "")
BASE = "http://localhost:8500"


def _marked():
    return Session.objects.filter(notes__contains=MARK)


def _teacher_of(group):
    """معلّمُ الشعبة الحاليّ: معلّمُ أحدثِ حصّةٍ لها، وإلّا مُسنَدُها، وإلّا معلّمُ خانةٍ في جدولها."""
    last = (
        Session.objects.filter(class_group=group, teacher__isnull=False)
        .order_by("-date", "-start_time")
        .select_related("teacher")
        .first()
    )
    if last is not None:
        return last.teacher
    for model in (SubjectClassAssignment, ScheduleSlot):
        row = (
            model.objects.filter(class_group=group, teacher__isnull=False)
            .select_related("teacher")
            .first()
        )
        if row is not None:
            return row.teacher
    return None


def _fallback_teacher(group):
    """شعبةٌ بلا معلّمٍ يُعرف: أحدُ معلّمي ESE النشطين في المدرسة، وإلّا أيُّ معلّمٍ نشط — ويُصرَّح بذلك."""
    for role in ("ese_teacher", "teacher"):
        membership = (
            Membership.objects.filter(school=group.school, is_active=True, role__name=role)
            .select_related("user")
            .order_by("joined_at", "id")
            .first()
        )
        if membership is not None:
            return membership.user
    return None


def up():
    today = timezone.localdate()
    existing = _marked().filter(date=today).first()
    if existing is None:
        candidates = (
            ClassGroup.objects.filter(
                section__iendswith="ESE",
                wing__isnull=True,
                is_active=True,
                enrollments__is_active=True,  # شعبةٌ فيها طلبةٌ فعلاً، وإلّا فارغةٌ لا تُعاين
            )
            .distinct()
            .order_by("-academic_year", "grade", "section")
        )
        group = candidates.first()
        if group is None:
            print("لا شعبةَ ESE بلا جناحٍ فيها طلبةٌ نشطون — لم يُنشأ شيء")
            return
        teacher = _teacher_of(group)
        if teacher is None:
            teacher = _fallback_teacher(group)
            if teacher is None:
                print("لا معلّمَ نشطاً في المدرسة يُسند إليه — لم يُنشأ شيء")
                return
            print("تنبيه: الشعبةُ بلا معلّمٍ معروف (لا حصّةَ ولا إسنادَ ولا خانةَ جدول)؛ اختير معلّمٌ نشطٌ من المدرسة.")
        existing = Session.objects.create(
            school=group.school,
            class_group=group,
            teacher=teacher,
            date=today,
            start_time=dt.time(5, 0),
            end_time=dt.time(23, 30),
            status="scheduled",
            notes=f"{MARK} حصّةُ معاينةٍ تُحذف بـdown",
        )
        print("أُنشئت حصّةُ المعاينة.")
    else:
        print("حصّةُ المعاينة قائمةٌ لليوم — لا تغيير.")

    group = existing.class_group
    student_id = (
        StudentEnrollment.objects.filter(class_group=group, is_active=True)
        .values_list("student_id", flat=True)
        .first()
    )
    other = (
        Membership.objects.filter(
            school=existing.school,
            is_active=True,
            role__name__in=("teacher", "ese_teacher", "coordinator"),
        )
        .exclude(user_id=existing.teacher_id)
        .values_list("user_id", flat=True)
        .first()
    )
    owner_role = (
        Membership.objects.filter(school=existing.school, is_active=True, user=existing.teacher)
        .values_list("role__name", flat=True)
        .first()
    )
    print(f"SESSION_ID        = {existing.id}")
    print(f"الشعبة            = {group.short_label} — {group.academic_year} (جناح: لا)")
    print(f"التاريخ والنافذة  = {existing.date} {existing.start_time:%H:%M}–{existing.end_time:%H:%M}")
    print(f"الصفحة            = {BASE}/teacher/attendance/{existing.id}/")
    print(f"معلّمُ الحصّة     = user_id {existing.teacher_id} (الدور: {owner_role})")
    print(f"طالبٌ للتجربة     = user_id {student_id}")
    print(f"معلّمٌ آخر للرفض  = user_id {other}")
    print("المتوقَّع: معلّمُ الحصّة يضغط «حاضر» فيُسجَّل 200 وسطرُ تدقيقٍ بالقيمتين؛ معلّمٌ آخر → 403.")
    print("تنبيه: لا تجرّب «غائب» — يستدعي فحصَ عتبات الغياب وقد يُنشئ تنبيهاً وإشعاراً.")


def down():
    sessions = list(_marked())
    ids = [s.id for s in sessions]
    rows = StudentAttendance.objects.filter(session_id__in=ids)
    removed_rows = rows.count()
    rows.delete()
    for session in sessions:
        session.delete()
    print(f"حُذفت {len(sessions)} حصّةٌ موسومةٌ و{removed_rows} صفُّ حضورٍ تابعٌ لها. غيرُ ذلك لم يُمسّ.")


if ACTION == "up":
    up()
elif ACTION == "down":
    down()
else:
    print("حدّد W026_ACTION=up أو down")
