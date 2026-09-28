# يُنشئ صفَّ كيمياء الثاني عشر تكنولوجي في الخطّة الدراسيّة — مطابقاً لصفّ 8500 حرفاً بحرف.
# متعادل: إعادةُ التشغيل لا تُنشئ صفّاً ثانياً (update_or_create على المفتاح الخماسيّ).
from academic_management.models import FROM_SCHOOL, CurriculumPlan
from core.models import CustomUser, School
from operations.models import Subject

school = School.objects.get(code="SHH001")
subject = Subject.objects.get(school=school, code="CHM")
actor = CustomUser.objects.filter(is_superuser=True).first()

row = CurriculumPlan(
    school=school,
    academic_year="2026-2027",
    grade="G12",
    track="technology",
    subject=subject,
    weekly_periods=2,
    source_kind=FROM_SCHOOL,
    source_reference="بديلٌ من قائمة دليل الخطط الدراسية 2025-2026 ص18–20 — اختيارُ المدرسة",
    elective_group="elective",
    is_active=True,
)
row.full_clean(validate_unique=False)

plan, created = CurriculumPlan.objects.update_or_create(
    school=school,
    academic_year="2026-2027",
    grade="G12",
    track="technology",
    subject=subject,
    defaults={
        "weekly_periods": 2,
        "source_kind": FROM_SCHOOL,
        "source_reference": row.source_reference,
        "elective_group": "elective",
        "is_active": True,
        "updated_by": actor,
    },
    create_defaults={
        "weekly_periods": 2,
        "source_kind": FROM_SCHOOL,
        "source_reference": row.source_reference,
        "elective_group": "elective",
        "is_active": True,
        "created_by": actor,
        "updated_by": actor,
    },
)
print("✓ أُنشئ:" if created else "✓ حُدِّث (كان موجوداً):", plan)
