---
name: maestro-spawn
description: |
  يقرّر بين توجيهٍ لمقعدٍ قائمٍ أو إعادةِ فتحٍ أو استحداثِ جلسةٍ جديدةٍ داخل تبويب الاختصاص، ويعدّ بطاقةَ الاستحداث BLUF بعد فحص الذاكرة.
  استخدمها عند: نتيجةُ التوجيه request_spawn أو wake_or_spawn، أو «أنشئ جلسة لـ…». Trigger on: new session, spawn, wake session.
disable-model-invocation: true
allowed-tools: Bash(python C:/Users/mesue/delivery_manager_work/tools/routing.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/watch_once.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/session_load_v2.py:*), Read, Write
---

# الاستحداث
القالبُ وقاعدةُ القرار: `C:/Users/mesue/delivery_manager_work/templates/spawn_card_template.md`.
1. `routing.py` ← إن كان `assign` فوجّه ولا تستحدث.
2. مقعدٌ خاملٌ/مؤرشفٌ في الاختصاص ← أعِد فتحَه (`unarchive_session`) قبل الإنشاء.
3. `python …/watch_once.py --no-live` ← الذاكرةُ أحمر/حرج ⇒ **لا استحداث**.
4. أعِدَّ البطاقةَ (تبويبُ الاختصاص، لماذا لا يكفي التوجيه، السعة، المهمّةُ بأربعة أسطر، المهاراتُ من `tabs.json`، شرطُ الأرشفة، الرسالةُ الأولى بـ«الفلو vX.Y»).
5. اعرضها على المالك؛ الإنشاءُ بموافقته في التطبيق، ثمّ انقل الجلسةَ لتبويبها (`maestro-tabs`).

**حدود:** جلسةٌ جديدةٌ ≈ ذاكرةٌ إضافيّةٌ (الجلسةُ الخاملةُ نحو 150MB بحسب قياس 09-26)؛ لا تُنشأ جلسةٌ لكلّ بند — مقاعدُ مُعاد استعمالُها.
