---
name: maestro-load-check
description: |
  قبل توجيه أيّ مهمّةٍ لجلسة: يقيس حِملَ الجلسات ويختار المقعدَ المختصّ الأخفَّ بجدول التوجيه (routing.py)؛ وإن كانت كلُّ المقاعد مثقلةً يُعدّ بطاقةَ استحداثٍ داخل التبويب.
  استخدمها عند: «وجّه هذه المهمّة»، «من يأخذ…»، «هل الجلسة X مثقلة؟»، أو قبل أيّ إسنادٍ جديد. Trigger on: route task, assign, workload, WIP.
allowed-tools: Bash(python C:/Users/mesue/delivery_manager_v2_work/tools/routing.py:*), Bash(python C:/Users/mesue/delivery_manager_v2_work/tools/session_load_v2.py:*), Bash(python C:/Users/mesue/delivery_manager_v2_work/tools/flow_metrics.py:*), Read
---

# فحصُ الحِمل والتوجيه
1. حدّد نوعَ المشكلة (من `projects/schoolos/routing.json`) أو مرِّر مساراتِ الملفّات: `python C:/Users/mesue/delivery_manager_v2_work/tools/routing.py --paths <مسارات> --live` أو `python C:/Users/mesue/delivery_manager_v2_work/tools/routing.py <النوع> --live`.
2. النتيجةُ: `assign` (المقعدُ الأخفّ) | `request_spawn` (كلُّ مقاعد الاختصاص مثقلة) | `wake_or_spawn` (لا جلسةَ ظاهرة) | `file_owner` (المنفّذُ صاحبُ الملفّ).
3. `assign` ← اكتب رسالةَ الإسناد بمواصفةٍ من أربعة أسطر، أوّلُ سطرٍ مكتفٍ بنفسه ويبدأ بـ«الفلو vX.Y»؛ ثمّ `ledger.py move <id> routed`.
4. `request_spawn`/`wake_or_spawn` ← استخدم المهارة `maestro-spawn`.
5. أخرِج للمالك BLUF من سطرين: من وُجِّه إليه ولماذا وما حِملُه.

**حدود:** لا تُرسل الرسالةَ قبل عرض الاختيار إن كان تجاوزاً لمقعدٍ مثقلٍ أو إعادةَ تخصيصٍ بين مسارات (يُقترح على المالك). أسماءُ الجلسات كما في الشريط لا أرقامُ منافذ. لا أسماءَ أشخاصٍ ولا نصَّ رسائل مستخدمين في أيّ ملفّ.
