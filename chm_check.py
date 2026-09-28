# تحقّقٌ للقراءة فقط — لا يكتب شيئاً. كيمياءُ الثاني عشر تكنولوجي في الخطّة الدراسيّة على هذه القاعدة.
from academic_management.models import CurriculumPlan
from core.models import School
from operations.models import Subject

school = School.objects.get(code="SHH001")
subjects = list(Subject.objects.filter(school=school, code="CHM").values_list("code", "name_ar"))
print("مادّة CHM:", subjects)
print("الثاني عشر تكنولوجي 2026-2027 (المادّة، الحصص، مجموعة الاختيار، المصدر):")
for row in CurriculumPlan.objects.filter(
    school=school, academic_year="2026-2027", grade="G12", track="technology"
).select_related("subject"):
    print("  ", row.subject.code, row.weekly_periods, repr(row.elective_group), row.source_kind, "نشط" if row.is_active else "موقوف")
exists = CurriculumPlan.objects.filter(
    school=school, academic_year="2026-2027", grade="G12", track="technology", subject__code="CHM"
).exists()
print("صفُّ الكيمياء موجود؟", exists)
