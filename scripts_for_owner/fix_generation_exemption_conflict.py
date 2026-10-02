"""سكربتُ معاينةٍ ثمّ تطبيقٍ — تعارضُ حصّةٍ مع تفريغ «لتوليد الجدول».

المشكلة: بعد D-61م (تصليب تفريغ التوليد)، صار كلُّ تفريغ يمنع — فحصّةٌ قائمةٌ
في خانة تفريغٍ مصدرُه «لتوليد الجدول» ظاهرةٌ الآن كتعارض، رغم أنّها لم تكن
مشكلةً قبل D-61م (كان هذا المصدر يُوسَم ولا يمنع).

لا يُصلح شيئاً بنفسه افتراضيّاً — يعرض فقط، ولا يُطبّق إلّا بعلمٍ صريح.

الاستعمال (داخل الحاوية على railway ssh):
    python manage.py shell < fix_generation_exemption_conflict.py            # معاينةٌ فقط
    APPLY=delete-exemption python manage.py shell < fix_generation_exemption_conflict.py   # يحذف تفريغَ «التوليد» المتعارض (الحصّةُ تبقى كما هي)

لا خيارَ لنقل الحصّة تلقائيّاً — هذا قرارٌ جدوليٌّ يحتاج اختيار خانةٍ بديلةٍ يدويّاً من شاشة الجدول.
"""

import os

from core.models import CustomUser
from operations.models import ScheduleSlot, TeacherExemption

DAY_NAMES = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس"]
APPLY = os.environ.get("APPLY", "")

teacher = CustomUser.objects.get(full_name__icontains="محمد العرامين")
print(f"=== {teacher.full_name} ({teacher.pk}) — وضعُ التشغيل: {APPLY or 'معاينةٌ فقط'} ===")

exemptions = TeacherExemption.objects.filter(teacher=teacher, is_active=True)
exempt_slots = {}
for ex in exemptions:
    periods = range(1, 8) if ex.exemption_type == "full_day" else [ex.period_number]
    for p in periods:
        exempt_slots[(ex.day_of_week, p, ex.academic_year)] = ex

slots = ScheduleSlot.objects.filter(teacher=teacher).select_related("class_group", "subject")
conflicts = []
for slot in slots:
    key = (slot.day_of_week, slot.period_number, slot.academic_year)
    if key in exempt_slots:
        conflicts.append((slot, exempt_slots[key]))

print(f"\nتعارضاتٌ (نفس العام الدراسيّ): {len(conflicts)}")
for slot, ex in conflicts:
    print(
        f"  {DAY_NAMES[slot.day_of_week]} حصّة {slot.period_number} — "
        f"{slot.class_group} / {slot.subject} — تفريغٌ id={ex.pk} مصدره={ex.source} "
        f"سببه={ex.reason!r}"
    )

if not conflicts:
    print("\nلا تعارضَ الآن — لا شيءَ يُفعل.")
elif APPLY == "delete-exemption":
    for slot, ex in conflicts:
        if ex.source != "generation":
            print(f"  تخطٍّ: تفريغ id={ex.pk} مصدره {ex.source} (ليس «لتوليد الجدول») — لا يُحذف تلقائيّاً.")
            continue
        print(f"  حذفُ التفريغ id={ex.pk} ({DAY_NAMES[slot.day_of_week]} حصّة {slot.period_number})")
        ex.delete()
    print("\nتمّ. الحصصُ بقيت كما هي؛ التفريغاتُ المتعارضةُ من مصدر «التوليد» وحدها حُذفت.")
else:
    print(
        "\nمعاينةٌ فقط — لم يُطبَّق شيء. لتطبيق حذف التفريغات المتعارضة (لا الحصص):\n"
        "  APPLY=delete-exemption python manage.py shell < fix_generation_exemption_conflict.py"
    )
