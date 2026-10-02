---
name: maestro-spawn
description: |
  Use when the maestro must open (or re-open) a flexible SchoolOS execution session: after maestro-load-check returns spawn (or routing.py says request_spawn / wake_or_spawn), to run the pre-flight (name 04SS · <tag>: <task> (<code>) ≤ 40 chars, next serial from per_tab_next["04"], 04 live cap 10, memory band as a warning only per D-51م), prepare the BLUF spawn card for the owner's in-app approval, place the session in "04 · التنفيذ والمعالجة", send its self-contained first message, and update the registry. Trigger on: open a session, new session, spawn, wake/unarchive a session, request_spawn, wake_or_spawn, "0405", big task in slices "1 من 3".
  استخدمها عند: «افتح جلسة لـ…»، «نحتاج جلسة جديدة»، «أعِد فتح الجلسة المؤرشفة»، «سمِّ الجلسة وافتحها»، «قسّم المهمّة جلسات».
  ليست لـ: اختيار جلسةٍ قائمة (maestro-load-check)، أرشفة جلسة (maestro-archive-check)، نقل المجموعات وتسميتها وتعديل tabs.json بنيويّاً (maestro-tabs)، فتح جلسات النواة الثابتة (قرارٌ بنيويٌّ للمالك)، خطوات الجلسة بعد فتحها (schoolos-flow).
disable-model-invocation: true
allowed-tools: Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/tools/routing.py:*), Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/tools/watch_once.py:*), Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/tools/session_load_v2.py:*), Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/tools/validate_registry.py:*), Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/tools/ledger.py:*), Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/skills/maestro-spawn/scripts/spawn_preflight.py:*), Read, Write, Edit
---

# الاستحداث: جلسةٌ مرنةٌ في 04 لمهمّةٍ واحدة

الغرض: أن تُفتح الجلسةُ المرنةُ حين لا يكفي غيرُها، باسمٍ صحيحٍ في مرحلتها، وبسعةٍ مقيسة، وبموافقة المالك في التطبيق — ثمّ تُعرَّف في السجلّ فلا يختلف الشريطُ عن `tabs.json`.
المصدر: `tabs.json` → `session_policy` (naming، serial، open_when، big_task، stage_moves، approval، archive_when)، وD-43م..D-51م، و`templates/spawn_card_template.md` — في `C:/Users/mesue/delivery_manager_work/`.

## الشروطُ قبل البدء
- بطاقةٌ كاملةٌ في السجلّ (أربعةُ أسطرٍ وزمنٌ وأولويّة) صنّفتها «0301 · المستشار: التصنيف والتسمية» واقترحت اسمَها (D-50م؛ «0302» أُلغيت).
- قرارُ `maestro-load-check` هو `spawn` (أو `assign_candidate` حكمتَ أنّه ليس من عائلة المهمّة). `core_owner`/`queue`/`ask` لا استحداثَ فيها.

## الإجراء
1. **أعِد الفتحَ قبل الإنشاء:** جلسةٌ مؤرشفةٌ للمهمّة نفسها (الرمزُ في اسمها) تُعاد بـ`unarchive_session` برقمها القديم، ولا تُنشأ أخرى. السكربتُ في الخطوة 2 ينبّه إن وجد الرمزَ في `archived_log` أو في أعضاء 04.
2. **الفحصُ المسبق:**
   ```bash
   python -X utf8 C:/Users/mesue/delivery_manager_work/skills/maestro-spawn/scripts/spawn_preflight.py \
     --tag واجهة --task "فراغ بطاقة الغياب" --code W-018          # أو --title "<اسمٌ كامل>" ، و--slice "1 من 3"
   ```
   **عند إصدار بطاقة spawn_task أضِف `--reserve`** — يحجز رقمَ العنوان 12 ساعة (`ledger/spawn_reservations.json`) فلا تأخذه بطاقةٌ ثانيةٌ قبل أن تُفتح الأولى؛ لأنّ `per_tab_next` لا يزيد إلّا عند الفتح (تصادم «0408» مرّتين 09-29). وبلا `--reserve` الفحصُ قراءةٌ فقط.
   يبني الاسمَ بالرقم التالي ويدقّقه بقواعد `validate_registry.name_problems` نفسِها، ويقرأ أعضاءَ 04 مقابل `live_cap`، والذاكرةَ بعتبات `thresholds.json`. `ok: false` (رمز 1) = مانع: اسمٌ مخالف، وسمٌ غيرُ معروف، رقمٌ أُعطي من قبل، أو 04 ممتلئة. `warnings` لا تمنع.
3. **الذاكرةُ تنبيهٌ لا مانع (D-51م):** أحمرُ أو حرجٌ ← أبلغ المالكَ برقمها (غيغا ووقتها) وافتح جلسةً واحدةً ثمّ انتظر حتى تستقرّ قبل التالية. ولا أكثرَ من جلستين أو ثلاثٍ عاملةٍ في آنٍ واحد (`handover.md` §5 بعد حادثة 20:24).
4. **البطاقة (BLUF):** بالقالب المصحَّح في `references/00-card-and-first-message.md` — القرارُ المطلوب، لماذا لا يكفي التوجيه (بأرقام الحِمل)، السعة، الأسطرُ الأربعة، المهاراتُ والصلاحيّاتُ من `specialties` للوسم، شرطُ الأرشفة، والرسالةُ الأولى.
5. **الفتحُ بموافقة المالك في التطبيق:** بطاقةُ مهمّةٍ يضغطها هو (أداةُ `spawn_task`)، فالعنوانُ بالاسم المدقَّق حرفيّاً، ثمّ `move_sessions` إلى مجموعة «04 · التنفيذ والمعالجة» — كلُّ استدعاءٍ بموافقته. خيارُ «بلا موافقةٍ داخل السقف» (D-43م) غيرُ مفعَّلٍ حتى صلاحيّات MAE-03 (`session_policy.approval`).
6. **الرسالةُ الأولى** مكتفيةٌ بنفسها وتبدأ بـ«الفلو v<الإصدار الحاليّ>»: الرمز، الأسطرُ الأربعة، الوسمُ ومهاراتُه، «اعمل في شجرتك، ولا دفعَ قبل الاعتماد»، والتسليمُ «جاهزٌ للمعاينة» إلى 0501. ما بعد ذلك في مهارة `schoolos-flow`.
7. **السجلّ** (بعد ظهور الجلسة لا قبله): في `tabs.json` أضِف الاسمَ إلى أعضاء 04 وزِد `serial.per_tab_next["04"]`؛ وفي `session_names.json` «مجلّدُ الشجرة ← الاسم»؛ وفي `sessions_snapshot.json` الاسمَ؛ ثمّ `python -X utf8 …/tools/validate_registry.py --sessions C:/Users/mesue/delivery_manager_work/projects/schoolos/sessions_snapshot.json` ← «السجلُّ متّسق». وتوليدُ المواثيق بمهارة `maestro-tabs`.
8. **البطاقةُ في السجلّ:** `ledger.py move <W-…> routed --note "فُتحت 0405"`، وسطرٌ للمالك: الاسم، السبب، الذاكرة.

## دورةُ حياة الجلسة (لا تكرّر الفلو — أحِل)
- تبقى في 04 طوال عملها ولا تُنقل إلى 05 أو 06 أو 07 (D-47م ألغى نقلَ D-46م). 0501 وحدها تثبّت على 8500، و0601 تدمج وتنشر، و0701 تحدّث الخارطة (`stage_moves`).
- تُؤرشف (لا تُحذف) بعد الدمج والنشر + الخارطة + مذكّرةِ تسليمٍ في `handover_notes/` + لا ملفّاتٍ غيرِ مودَعة + لا تعمل الآن (`archive_when`) — بمهارة `maestro-archive-check`؛ ورقمُها لا يُعاد لغيرها.
- المهمّةُ الضخمة (> يوم عمل أو أكثرُ من طبقة) شرائحُ متتالية «… 1 من 3»، الأساسُ أوّلاً، ولا ملفَّ في شريحتين، وهجراتُ التطبيق الواحد في شريحةٍ واحدة (`big_task`). تُفتح الشريحةُ التالية حين تقترب سابقتُها من الاعتماد لا كلُّها معاً.

## القواعد وأسبابها
- الاسمُ `04SS · <الوسم>: <مهمّةٌ قصيرة> (<الرمز>)` ≤ 40 حرفاً، والوسمُ من `specialties[].name_tag` (واجهة/جدول/إدارة): الشريطُ أبجديّ فالرقمُ يرتّب الجلساتِ بأقدميّتها، والوسمُ يُظهر الاختصاصَ بلا تبويبٍ له (D-45م، D-46م).
- الرقمُ لا يُعاد لجلسةٍ أُرشفت، ويبقى للجلسة وإن تغيّرت مهمّتُها في الاسم (D-44م، `serial.note`).
- 04 من 0 إلى 10 جلساتٍ مرنة، والنواةُ الثابتةُ خارج هذا الحدّ (D-51م، `live_cap`).
- المايسترو يقترح الفتحَ والمالكُ يوافق في التطبيق؛ لا يُفتح شيءٌ «على الأصل» (`operating_model.md` §7).

## فخاخٌ وقعت فعلاً
- خطأ: فتحُ خمسِ جلساتٍ معاً مساءَ 09-28 (جلساتُ نواة، والدرسُ واحد) وإيقاظُ أخرى برسائل ← 0.16 غيغا حرّة عند 20:24 (`board_state.md`). الصواب: واحدةٌ ثمّ انتظار.
- خطأ: «الذاكرة حمراء فلا استحداث» — نصُّ القالب القديم وعتبةُ «أصفر» في `thresholds.json`. الصواب: D-51م أحدث: تنبيهٌ يُبلَّغ به المالك، والفتحُ بالتتابع.
- خطأ: اسمٌ بلا رقم أو بوسمٍ قديم («بصريّ · محور الجوال»، «منصّة · …») ← `validate_registry` يرفضه. الصواب: «0405 · واجهة: …».
- خطأ: إعادةُ «0401» لأنّ صاحبتها أُرشفت. الصواب: التالي من `per_tab_next["04"]`.
- خطأ: «تقترحه 0302» ← أُلغيت في D-50م. الصواب: 0301.
- خطأ: نقلُ الجلسة إلى 05 حين تجهز (نصُّ `principle` في tabs.json ما زال يقول «تنتقل») ← D-47م. الصواب: تبقى في 04 وتعلن لـ0501.
- خطأ: تثبيتُها (Pinned) في أعلى الشريط ← يُخرجها من مجموعتها؛ أُلغي في D-44م.
- خطأ: جلسةٌ حاديةَ عشرة في 04. الصواب: `queue` حتى تُؤرشف منتهية.
- خطأ: فتحُ جلسةٍ ثابتةٍ ثانيةٍ في تبويبٍ فيه واحدةٌ فتأخذ صلاحيّاتِها ومهاراتِها من التبويب (وَرِثت 0101..0105 «لا دفع» ومهاراتِ المايسترو، ليلة 10-01/02). الصواب: لا تُفتح ثانيةٌ في تبويبٍ منفردٍ (03، 05، 06، 08) قبل أن يُكتب **ميثاقٌ صريحٌ للجلستين** في `tabs.json` (`session_policy.charters`: role وscope وboundaries)؛ و`validate_registry.py` يرفض تبويباً مشترَكاً بميثاقٍ بلا «حدود»، والقالبُ لا يورّث من التبويب بعد إصلاح 0102 (D-107م، اقتراح 0104).
- خطأ: أرشفةُ جلسة نواةٍ ظُنّت مرنة (0201 في D-43م، أُعيدت في D-47م). الصواب: `core_sessions` قبل أيّ أرشفة.

## المراجع
| الملف | متى تقرؤه |
|---|---|
| `references/00-card-and-first-message.md` | عند كتابة بطاقة الاستحداث والرسالة الأولى، ومثالٌ كامل |
| `references/01-registry-after-open.md` | بعد ظهور الجلسة: تحديثُ الملفّات الثلاثة والتحقّق، وإعادةُ الفتح |
| `references/99-test-cases.md` | عند مراجعة الوصف واختبار التفعيل |
| `scripts/spawn_preflight.py` | يُشغَّل ولا يُقرأ؛ `--help` لخياراته |
