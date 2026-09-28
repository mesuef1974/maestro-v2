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
5. **الاسم:** `TTSS · <اسمٌ معبّرٌ قصير> (<الرمز>)` — TT رقمُ التبويب، وSS التالي من `session_policy.serial.per_tab_next` في tabs.json (ثمّ زِده بواحد، ولا يُعاد رقمٌ أُرشفت جلستُه)؛ الاسمُ ≤ 40 حرفاً ويعبّر عن المهمّة القائمة، ويُحدَّث متى تغيّرت ويبقى الرقم.
6. أنشئها، وانقلها **فوراً** إلى تبويبها (`move_sessions`) — لا جلسةَ خارج تبويب؛ ثمّ جدِّد `sessions_snapshot.json` و`session_names.json` وشغّل `validate_registry.py --sessions` (D-45م).

**حدود:** الجلساتُ عند الطلب (D-43م): تُفتح لمهمّةٍ وتُؤرشف (لا تُحذف) حين يُدمج عملُها ويُنشر؛ السقفُ 8 جلساتٍ حيّة وحدُّ التبويب `live_cap`؛ المهمّةُ الضخمةُ جلساتٌ متتالية «… 1 من 3».
