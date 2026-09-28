---
name: maestro-tabs
description: |
  يدير تبويبات الشريط (مجموعات الجلسات) وفق سجلّ tabs.json: تدقيقُ الاتّساق، إنشاءُ المجموعات وتسميتُها ونقلُ الجلسات، وتوليدُ مواثيق التبويبات.
  استخدمها عند: «رتّب الشريط»، «انقل الجلسة إلى تبويب اختصاصها»، «عدّل التبويبات»، أو قبل أيّ استحداثٍ لتحديد التبويب. Trigger on: sidebar, groups, tabs, move session.
disable-model-invocation: true
allowed-tools: Bash(python C:/Users/mesue/delivery_manager_work/tools/validate_registry.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/render_charters.py:*), Read, Write, Edit
---

# التبويبات
المرجعُ: `projects/<المشروع>/tabs.json` (المصدر) و`docs/sidebar_migration_plan.md` (خطّةُ الانتقال الحاليّة). المجموعةُ في التطبيق اسمٌ فقط؛ الميثاقُ في السجلّ.
1. **دقّق قبل أيّ نقل:** `python …/validate_registry.py --sessions <عناوين الجلسات الحيّة من list_sessions>` ← «السجلُّ متّسق».
2. **نفّذ بأدوات الشريط** (`list_groups` ثمّ `create_group` / `rename_group` / `move_sessions`)، كلُّ استدعاءٍ بموافقة التطبيق؛ اعرض الخطّةَ على المالك قبل الاستدعاء الأوّل.
3. **تحقّق بعده:** `list_groups` (أعدادُ الأعضاء تطابق `tabs.json`) وأعِد `validate_registry`.
4. **تعديلُ تبويب** (هدف/مهارة/حدّ): عدّل `tabs.json` ثمّ `render_charters.py`؛ الحوكمةُ تملك تعريفَ التبويبات (ذاكرة المشروع) — أبلغها بالتعديل.
5. **الاستحداث بحسب الاختصاص:** التبويبُ يُحدَّد من `routing.json` ثمّ تُطبَّق `templates/spawn_card_template.md` (مهارة `maestro-spawn`).

**حدود:** لا تنقل ولا تسمِّ بلا موافقةٍ في التطبيق؛ لا حذفَ لمجموعة؛ ما خارجَ مشروع المدرسة لا يُمسّ إلا بأمرٍ باسمه.
