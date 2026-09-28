---
name: maestro-project-switch
description: |
  يبدّل المشروعَ الذي يديره المايسترو: يقرأ ملفَّ المشروع (تبويبات، توجيه، عتبات، أسماء الجلسات) ويبني ملفَّ مشروعٍ جديداً من القالب عند الحاجة.
  استخدمها عند: «المشروع الحاليّ صار X»، «أنشئ ملف مشروع»، أو قبل إدارة جلساتٍ خارجَ مشروع المدرسة. Trigger on: switch project, new project profile.
allowed-tools: Read, Write, Bash(python C:/Users/mesue/delivery_manager_v2_work/tools/validate_registry.py:*)
---

# مشروعٌ آخر
كلُّ مشروعٍ مجلّدٌ تحت `C:/Users/mesue/delivery_manager_v2_work/projects/<اسم>/`: `tabs.json` و`routing.json` و`thresholds.json` و`session_names.json` (و`ignored_trees.json`، `pr_owner_overrides.json`).
1. **تبديل:** مرِّر `--project <اسم>` لأدوات `session_load_v2` و`routing` و`watch_once` و`validate_registry` و`archive_check`؛ الافتراضيّ `schoolos`.
2. **مشروعٌ جديد:** انسخ مجلّدَ `schoolos` وعدّل: بادئةَ المجموعات (`group_prefix`)، التبويباتِ وأعضاءَها، جدولَ التوجيه، العتبات. ثمّ `validate_registry.py --project <اسم>`.
3. أخبر «الحوكمة» بأيّ تعديلٍ في التبويبات (هي تملك تعريفَها).
4. **لا يُدار مشروعٌ آخر بلا أمر المالك** ولا يُنقل عملٌ بين المشاريع.

**حدود:** أسماءُ الجلسات وعناوينُها كما في الشريط؛ ما خارجَ المشروع الحاليّ لا يُمسّ.
