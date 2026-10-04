---
name: maestro-project-switch
description: |
  Use when the maestro must work on a project other than SchoolOS, or create/inspect a project profile under C:/Users/mesue/delivery_manager_work/projects/<name>/ (tabs.json, routing.json, thresholds.json, session_names.json, pr_owner_overrides.json, ignored_trees.json, sessions_snapshot.json): which tools honour --project, which are hard-wired to D:/shschool_mvp, how to build a minimal valid profile and verify it with validate_registry.py. Trigger on: switch project, new project profile, --project, «المشروع الحاليّ صار …»، «أنشئ ملفّ مشروع»، «أدِر جلسات مشروع آخر»، session_names.json, «أشجارٌ بلا اسم».
  استخدمها قبل إدارة جلساتٍ أو قياس حِملٍ أو توجيه عملٍ خارجَ مشروع المدرسة، وعند إنشاء ملفّ مشروعٍ جديد.
  ليست لـ: تبويباتِ SchoolOS ونقلِ جلساتها (maestro-tabs)، ولا فتحِ الجلسات (maestro-spawn)، ولا أرشفتِها (maestro-archive-check)، ولا منطقِ منصّة المدرسة (schoolos-platform)، ولا شركةِ أذكياء (azkia).
allowed-tools: Read, Write, Edit, mcp__ccd_session_mgmt__list_sessions, Bash(ls C:/Users/mesue/delivery_manager_work/projects:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/validate_registry.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/session_load_v2.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/routing.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/watch_once.py:*)
---

# ملفُّ المشروع وتبديلُه

الغرض: أن يعرف المايسترو أيَّ مشروعٍ يقيس حين يشغّل أداةً، وألّا يُدير جلساتِ مشروعٍ آخر بلا أمر، وأن يبني ملفَّ مشروعٍ جديدٍ صالحاً من أوّل مرّة.
الواقعُ يومَ 09-28: مشروعٌ واحدٌ فقط `projects/schoolos/`، و**لا «مشروعَ حاليّاً» محفوظاً في أيّ مكان**: كلُّ أداةٍ افتراضُها `schoolos`، والتبديلُ هو `--project <اسم>` في كلّ استدعاء — حيث تقبله الأداة.

## متى
- أمرٌ من المالك باسم مشروعٍ آخر («أدِر جلسات …»، «أنشئ ملفّ مشروع لـ…»).
- ظهورُ جلساتٍ من مشاريع أخرى في الشريط أو في «أشجارٌ بلا اسم».
- تعديلُ `session_names.json` أو `pr_owner_overrides.json` أو `ignored_trees.json` أو `thresholds.json` أو `routing.json` لـSchoolOS نفسِه (ملفّاتُ المشروع غيرُ التبويبات).

## الإجراء
1. **هل عندك أمر؟** مشروعٌ غيرُ SchoolOS لا يُدار ولا تُؤرشف جلساتُه ولا تُنقل إلّا بأمرٍ من المالك باسمه، ولا يُنقل عملٌ بين المشاريع. المصدر: `tabs.json` → `parked_other_projects.note`؛ الذاكرة `feedback_never_archive_without_order.md`. بلا أمرٍ: توقّف وأبلغ.
2. **ما الموجود؟** `ls C:/Users/mesue/delivery_manager_work/projects` — الاسمُ الذي ستمرّره يطابق مجلّداً حرفيّاً (انظر الفخّ الثاني).
3. **اعرف حدودَ كلّ أداة** قبل تصديق مخرجها (الجدولُ الكامل في `references/00-project-profile.md`):
   - تحترم `--project` في ملفّاتها: `validate_registry.py`، `routing.py`، `session_load_v2.py`، `watch_once.py` (العتبات والأسماء)، `archive_check.py` (النواة من `tabs.json`).
   - **مربوطةٌ بمستودع المدرسة `D:/shschool_mvp` في الشيفرة:** `archive_check.py`، `watch_once.py` (gh والأشجار)، `flow_metrics.py`، `evidence_pack.py`، `owner_load_study.py`. وحده `session_load_v2.py` يقبل `--repo`.
   - مربوطةٌ بملفّات `schoolos`: `review_window.py` (العتبات)، و`render_charters.py` يكتب `docs/tab_charters.md` أيّاً كان المشروع.
4. **مشروعٌ قائم:** مرّر `--project <اسم>` لكلّ أداةٍ تقبله، و`--repo <مسار المستودع>` لـ`session_load_v2.py`؛ وما كان مربوطاً بمستودع المدرسة لا تستعمله لمشروعٍ في مستودعٍ آخر — اكتب «غيرُ مقيس» بدل رقمٍ مضلِّل.
5. **مشروعٌ جديد:** ابنِ `projects/<اسمٌ-صغيرٌ-بشرطات>/` بالهيكل الأدنى في `references/01-new-project.md` — لا بنسخ `schoolos` كاملاً (نواتُه ومواثيقُه وتوجيهُه لجلسات المدرسة وقراراتها). ثمّ:
   `python C:/Users/mesue/delivery_manager_work/tools/validate_registry.py --project <اسم>` حتى «السجلُّ متّسق» (رمزُ خروج 0)، وبعد فتح جلساته: `--sessions <ملفّ JSON بعناوينها الحيّة>`.
6. **إن كان في مستودعٍ آخر:** الأدواتُ في الخطوة 3 تحتاج صيانةً (معاملُ `--repo`) قبل الاعتماد عليها — صيانةُ أدوات المايسترو داخل مجلّده مسموحةٌ (D-37م) وتتولّاها 0102 · التقييم والعصف: جودةُ المنظومة؛ اعرضها على المالك قراراً لا تنفّذها ضمناً.
7. **أبلغ:** 0103 · الحوكمة: حراسةُ القواعد بأيّ ملفِّ مشروعٍ جديدٍ أو تعديلٍ في `session_policy` (تحرس قواعدَ الجلسات، وتبويباتُ المدرسة لـ`maestro-tabs`)؛ وسجّل أمرَ المالك في `decisions.md` (`maestro-handover`).

## قواعدٌ وسببُها
- **التسميةُ الرباعيّة مفروضةٌ على كلّ مشروع:** `validate_registry.name_problems` يرفض أيَّ عضوٍ لا يبدأ بـ`TTSS · ` أو يتجاوز `serial.max_title_len` (40 افتراضاً) — فجلساتُ المشروع الجديد تُسمّى بالنظام نفسِه أو يفشل التدقيق (D-45م).
- **ملفّاتٌ ناقصةٌ تمرّ صامتةً في `session_load_v2.py`:** `load_json` يُرجع `{}` لملفٍّ غير موجود؛ فاسمُ مشروعٍ خاطئ يعطي جدولاً «سليماً» كلُّ أشجاره «بلا اسم». أمّا `validate_registry` و`archive_check` و`routing` فيفشلان بصوتٍ (`FileNotFoundError`).
- **`group_prefix` لم يعد بادئة:** قيمتُه اليوم فارغة، واسمُ المجموعة «<رقمُ المرحلة> · <اسمُها>» (`group_name_format`، D-46م). لا تبنِ أسماءَ المجموعات منه.
- **اختباراتُ الحزمة لـ`schoolos` وحده** (`tools/test_package.py` يقرأ ملفّاته صراحةً): مشروعٌ جديدٌ لا تحرسه الاختبارات؛ `validate_registry` هو حارسُه الوحيد.

## فخاخٌ وقعت أو ثبتت بالتشغيل
- خطأ: «مرِّر `--project` لـ`archive_check` و`watch_once`» (النسخةُ السابقة من هذه المهارة) على أنّه تبديلٌ كامل.
  الصواب: `--project` يبدّل الملفّات لا المستودع؛ الأداتان تقرآن `D:/shschool_mvp` في الشيفرة (`archive_check.gather`، `watch_once.orphan_alerts`).
- خطأ:ٌ إملائيٌّ في `--project` مع `session_load_v2.py` يمرّ بلا خطأ.
  الصواب: `ls projects` أوّلاً، و`validate_registry --project <اسم>` قبل أيّ قياس (يفشل بصوتٍ إن لم يوجد المجلّد — جُرّب 09-28).
- خطأ: `render_charters.py <مشروعٌ آخر>` «لتوليد مواثيقه»: يكتب فوق `docs/tab_charters.md` الخاصّ بالمدرسة.
  الصواب: لا تشغّله لغير `schoolos` قبل أن يُصان ليكتب ملفّاً باسم المشروع. و`render_charters.py --help` يعامل `--help` اسمَ مشروع فيفشل — لا واجهةَ أوامر له.
- خطأ: نسخُ مجلّد `schoolos` كما هو: نواةٌ من ثلاث عشرة جلسةً ومواثيقُ وتوجيهٌ بمسارات `templates/**` و`static/**` لا وجودَ لها في المشروع الآخر.
  الصواب: الهيكلُ الأدنى المُجرَّب في `references/01-new-project.md`.
- خطأ: ترتيبُ الشريط بأرشفة جلسات المشاريع الأخرى «لأنّها خاملة» أو لتخفيف الذاكرة.
  الصواب: لا تُمسّ إلّا بأمرٍ باسمها؛ المقترحُ لها تبويبٌ واحد «مشاريع أخرى · أرشيف» للترتيب فقط، ونقلُها بـ`maestro-tabs` بموافقة التطبيق.

## ما ليس لهذه المهارة
تبويباتُ SchoolOS ومواثيقُها ونقلُ جلساتها (`maestro-tabs`)؛ فتحُ الجلسات (`maestro-spawn`)؛ أرشفتُها (`maestro-archive-check`)؛ صيانةُ شيفرة الأدوات (0102 بقرار)؛ أيُّ عملٍ في مستودع المشروع الآخر نفسِه.

## المراجع
| الملفّ | متى تقرأه |
|---|---|
| `references/00-project-profile.md` | قبل تشغيل أيّ أداةٍ بـ`--project` غير `schoolos`، أو عند تعديل أيّ ملفٍّ في `projects/<اسم>/` |
| `references/01-new-project.md` | عند إنشاء ملفّ مشروعٍ جديد |
| `references/99-test-cases.md` | عند تعديل هذه المهارة أو وصفها |
