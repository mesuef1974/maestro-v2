# إنشاءُ ملفّ مشروعٍ جديد
متى تقرأ هذا الملفّ: حين أمر المالكُ بإدارة مشروعٍ جديدٍ باسمه، وقبل كتابة أيّ ملفٍّ في `projects/<اسم>/`.

## قبل الكتابة
1. أمرُ المالك باسم المشروع مسجَّلٌ في `decisions.md` (قرارٌ جديد بالرقم التالي — `maestro-handover`).
2. اسمُ المجلّد صغيرٌ بشرطاتٍ بلا مسافات (مثالٌ مختلَق: `research-notes`)؛ وهو ما يُمرَّر لـ`--project`.
3. اعرف مستودعَه: إن لم يكن `D:/shschool_mvp` فاقرأ جدولَ الأدوات في `00-project-profile.md` واكتب للمالك ما لن يُقاس.

## الهيكلُ الأدنى (جُرّب بـ`validate_registry.validate` يوم 09-28 فأعطى «السجلُّ متّسق»)
`tabs.json`:
```json
{
  "project": "research-notes",
  "group_prefix": "",
  "principle": "<مبدأُ تقسيم التبويبات في سطر>",
  "owner_touchpoints": ["<لمسةُ المالك الأولى>", "<الثانية>"],
  "tabs": [
    {"id": "command", "number": "01", "name": "إدارة المشروع", "order": 0, "layer": "إدارة",
     "purpose": "…", "goals": ["…"], "kpis": ["…"], "inputs": ["…"], "outputs": ["…"],
     "skills": ["maestro-handover"], "permissions": "قراءةٌ ومراسلة", "lifecycle": "ثابتة",
     "live_cap": 2, "members": ["0101 · المايسترو"]},
    {"id": "execute", "number": "02", "name": "التنفيذ", "order": 1, "layer": "تنفيذ",
     "purpose": "…", "goals": ["…"], "kpis": ["…"], "inputs": ["…"], "outputs": ["…"],
     "skills": ["…"], "permissions": "…", "lifecycle": "عند الطلب", "live_cap": 5, "members": []}
  ],
  "pending_archive": [],
  "archived_log": [],
  "parked_other_projects": {"note": "…", "suggested_group": "…"},
  "scheduled_task_title_prefixes": [],
  "session_policy": {
    "core_sessions": ["0101 · المايسترو"],
    "serial": {"format": "TTSS", "per_tab_next": {"01": 2, "02": 1}, "max_title_len": 40, "carried_from": {}},
    "archive_when": "<شرطُ الأرشفة لهذا المشروع>"
  }
}
```
`routing.json`: `{"default_wip_limit": 3, "problem_types": {"<نوع>": {"label": "…", "tab": "execute", "executors": [], "owners": [], "path_globs": ["<مساراتُ هذا المستودع>"]}}}`
`thresholds.json`: انسخه من `schoolos` ثمّ اجعل `_note` يقول إنّها قيمٌ أوّليّةٌ تُعايَر (العتباتُ خاصّةٌ بالجهاز لا بالمشروع، فالذاكرةُ نفسُها).
`session_names.json` = `{}`، `pr_owner_overrides.json` = `{}`، `ignored_trees.json` = `{"trees": []}`، `sessions_snapshot.json` = `[]`.

ملاحظات:
- `parked_other_projects` مطلوبٌ لـ`render_charters.py` (يقرؤه بلا شرط) — لكن لا تشغّل تلك الأداة لغير `schoolos` (تكتب فوق مواثيق المدرسة).
- `principle` و`owner_touchpoints` يقرؤهما `render_charters.py` أيضاً؛ ولا يفحصهما `validate_registry`.
- `per_tab_next` يبدأ بالرقم التالي لما فُتح: الرقمُ لا يُعاد لجلسةٍ أُرشفت (D-45م).

## ما لا يُنسخ من `schoolos`
- `session_policy.core_sessions` و`charters` و`core_note` و`open_when` و`naming` و`stage_moves`: تسمّي جلساتِ المدرسة وقراراتِها (D-43م..D-56م).
- `specialties` (`exec_ui`، `exec_schedule`، `exec_admin`) ومساراتُ `routing.json` (`templates/**`، `static/**`…): لمستودع المدرسة.
- `archived_log`: تاريخُ المدرسة.

## التحقّق
```
python C:/Users/mesue/delivery_manager_work/tools/validate_registry.py --project <اسم>
```
«السجلُّ متّسق» ورمزُ 0، وإلّا أصلح كلَّ سطرٍ يطبعه. وبعد فتح جلساته (بموافقة المالك في التطبيق، `maestro-spawn`): اكتب عناوينها في `sessions_snapshot.json` وأعِد بـ`--sessions`.
ثمّ `python …/tools/session_load_v2.py --project <اسم> --repo <مستودعه> --no-fetch` — و«أشجارٌ بلا اسم» تُملأ في `session_names.json`.

## أنماطٌ مضادّة
- `cp -r projects/schoolos projects/<جديد>` ثمّ تعديلُ الاسم وحده.
- اسمُ مجلّدٍ بمسافاتٍ أو حروفٍ عربيّة (يُمرَّر في سطر الأوامر ويُقارن حرفيّاً).
- أسماءُ جلساتٍ لا تتبع `TTSS · <اسم>` «لأنّه مشروعٌ آخر» — يرفضها المدقّق.
- بدءُ إدارة المشروع قبل تسجيل أمر المالك.
