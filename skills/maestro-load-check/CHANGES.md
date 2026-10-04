# CHANGES — maestro-load-check
الأصل: `C:/Users/mesue/delivery_manager_work/skills/maestro-load-check/SKILL.md` (17 سطراً، 09-28 15:30). لم يُعدَّل الأصل.

| البند | القديم | الجديد | السبب | الدليل |
|---|---|---|---|---|
| الوصف | عربيٌّ وأربعُ كلماتٍ إنجليزيّة | إنجليزيٌّ «Use for/Trigger on» + عربيٌّ عاميّ + «ليست لـ» بخمس مهارات | التفعيلُ بالوصف؛ الحدُّ مع intake وspawn وtabs وflow | BRIEF §2 |
| مصدرُ القرار | `routing.py` وحده بقراراته الأربعة | `routing.py` + سكربتٌ جديد `scripts/route_now.py` يقرأ القياسَ على النموذج الحاليّ (نواة/وسم/04) | `routing.json` يطابق مقاعدَ أُرشفت في D-43م فيُرجع `wake_or_spawn` لكلّ نوعٍ تنفيذيّ | `routing.py ui --live` ← `wake_or_spawn` و0403 حيّةٌ 9MB بلا طلبات (09-28 21:00) |
| قراراتُ الخرج | assign / request_spawn / wake_or_spawn / file_owner | core_owner / assign_candidate / spawn / queue / file_owner / ask / unknown_type | تعكس النواةَ الثابتة (D-51م) وحدَّ 04 (live_cap 10) وما لم يُحسم (git وinfra_preview) | `tabs.json` session_policy وspecialties؛ مواثيقُ النواة |
| «عائلةُ المهمّة» | غائب | الوسمُ وحده لا يكفي للإسناد؛ الرمزُ أو الملفّاتُ نفسُها | المرنةُ تُفتح لمهمّةٍ وتُؤرشف بعدها (D-43م)، والاسمُ يتبع المهمّة (D-44م) | D-43م، D-44م |
| قياسُ الحِمل | ضمنيّ داخل `--live` | `session_load_v2.py --json --no-fetch > load.json` ثمّ `--load-json` | قرائيٌّ فعلاً (بلا git fetch)، وقياسٌ واحدٌ لدفعةٍ من البطاقات | شيفرةُ `session_load_v2.main` |
| تعريفُ «مثقلة» | غائب | ≥4 طلبات أو ≥40MB؛ فوق WIP >3؛ الشجرةُ بلا اسمٍ غيرُ صالحة؛ السياقُ = حجمُ أحدث محادثة | يُقرأ من الشيفرة لا من الذاكرة | `classify`، `operating_model.md` §2 |
| الأسماءُ المكرّرة | غائب | شجرتان باسمٍ واحدٍ تُجمعان بالأسوأ | ظهر 0401 و0402 صفّين في القياس | مخرجُ `session_load_v2.py` 20:58 |
| رسالةُ الإسناد | «أوّلُ سطرٍ يبدأ بـالفلو vX.Y» | قالبٌ كاملٌ في مرجع، ورقمُ الإصدار من آخر صفٍّ في flow_changelog.md، والتسليمُ إلى 0501 | إجراءٌ لا تلميح | `operating_model.md` §1 و§4؛ D-47م |
| الإيقاظُ المتزامن | غائب | لا أكثرَ من جلستين أو ثلاثٍ معاً، ورسائلُ العلم تُجمع | حادثةُ 09-28 20:24 (0.16 غيغا) | `handover.md` §5، `board_state.md` |
| الفخاخ | لا شيء | ستّةُ فخاخ خطأ:/الصواب: | BRIEF §2 | أعلاه |
| الأمثلة | لا شيء | مثالٌ في SKILL، وجدولُ مخرجاتٍ مجرّبة، ورسالةٌ كاملة | BRIEF §2 | تشغيلٌ فعليّ |
| allowed-tools | routing، session_load_v2، flow_metrics، Read | + ledger.py (لـ`show` و`move`) + route_now.py، وكلُّها بصيغة `python -X utf8` | الخطوتان 1 و6 تحتاجان ledger؛ و-X utf8 يجعل الرسائل مقروءة | — |
| مسارُ السكربت | — | `C:/Users/mesue/delivery_manager_work/skills/maestro-load-check/scripts/route_now.py` | يفترض نقلَ النسخة المجوَّدة إلى موضع الأصل عند الاعتماد | — |
| الاختبار | — | route_now جُرّب حيّاً وبـ`--load-json` ولفروع queue/ask/file_owner/unknown_type ببياناتٍ مصطنعة | BRIEF §6 | جلسةُ البناء 09-28 21:05 |
