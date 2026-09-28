# ملفُّ المشروع: ملفّاتُه وما يقرؤه كلُّ أداة
متى تقرأ هذا الملفّ: قبل تشغيل أيّ أداةٍ بـ`--project` غير `schoolos`، أو قبل تعديل أيّ ملفٍّ في `projects/<اسم>/`.

## الملفّات (`C:/Users/mesue/delivery_manager_work/projects/<اسم>/`)
| الملفّ | ما فيه | من يقرؤه | إن غاب |
|---|---|---|---|
| `tabs.json` | التبويبات (المراحل) وأعضاؤها، `session_policy` (النواة، التسمية، الترقيم، الأرشفة، المواثيق)، `specialties`، `parked_other_projects`، `scheduled_task_title_prefixes` | validate_registry، archive_check، render_charters | فشلٌ صريح |
| `routing.json` | `problem_types`: نوعُ المشكلة ← التبويب/الاختصاص، و`path_globs` لتخمين النوع من المسارات؛ و`default_wip_limit`، `expedite` | routing، validate_registry | فشلٌ صريح |
| `thresholds.json` | عتباتُ الذاكرة وإجراءاتُها، التدفّق، سعةُ المالك ونوافذُه | watch_once (بـ`--project`)، review_window (**schoolos دائماً**) | فشلٌ صريح في watch_once |
| `session_names.json` | اسمُ مجلّد الشجرة ← عنوانُ الجلسة | session_load_v2، watch_once | `{}` صامت |
| `pr_owner_overrides.json` | رقمُ الطلب ← الجلسة، لحسم النسبة يدويّاً | session_load_v2 | `{}` صامت |
| `ignored_trees.json` | `{"trees": [...]}` أشجارٌ لا تُعدّ | session_load_v2، watch_once | `{}` صامت |
| `sessions_snapshot.json` | مصفوفةُ عناوين الجلسات الحيّة لـ`validate_registry --sessions` | يدويّاً | — |
المصدر: شيفرةُ الأدوات (`grep -n "projects\|--project"` في `tools/*.py`، 09-28).

## الأدواتُ والمشروعُ والمستودع
| الأداة | `--project` | المستودع | ملاحظة |
|---|---|---|---|
| `validate_registry.py` | نعم | لا يلمسه | JSON وحده؛ الأصلحُ لمشروعٍ جديد |
| `routing.py` | نعم | عبر `--live` (يستدعي session_load_v2) | `<نوع> --live` أو `--load-json` أو `--paths …` |
| `session_load_v2.py` | نعم | **`--repo`** (افتراضُه `D:/shschool_mvp`) | الكتابةُ الوحيدة `git fetch` (تُعطَّل بـ`--no-fetch`) |
| `watch_once.py` | نعم (العتبات والأسماء) | `D:/shschool_mvp` في الشيفرة | `--no-live` للذاكرة وحدها بلا مستودع |
| `archive_check.py` | نعم (النواة) | `D:/shschool_mvp` في الشيفرة | انظر `maestro-archive-check` |
| `flow_metrics.py` | لا | `D:/shschool_mvp` في الشيفرة | — |
| `evidence_pack.py`، `owner_load_study.py` | لا | `D:/shschool_mvp` في الشيفرة | — |
| `review_window.py` | لا | — | يقرأ `projects/schoolos/thresholds.json` ثابتاً |
| `render_charters.py` | موضعيّ (`render_charters.py <اسم>`) | — | **يكتب** `docs/tab_charters.md` أيّاً كان المشروع |
| `ledger.py` | لا | — | سجلُّ عملٍ واحدٌ لكلّ الحزمة (`ledger/events.jsonl`) |

النتيجة: مشروعٌ في مستودع المدرسة نفسِه (تبويباتٌ أخرى للمنظومة نفسِها) يعمل بـ`--project` وحده؛ ومشروعٌ في مستودعٍ آخر لا يُقاس إلّا بـ`validate_registry` و`session_load_v2 --repo` و`watch_once --no-live` حتى تُصان البقيّة.

## الحقولُ الإلزاميّة في كلّ تبويب
`id`، `name`، `order`، `layer`، `purpose`، `goals`، `kpis`، `inputs`، `outputs`، `skills`، `permissions`، `lifecycle`، `live_cap`، `members` — كلُّها غيرُ فارغةٍ إلّا `members` (الجلساتُ تُفتح عند الطلب، D-43م). ويُستحسن `number` (رقمُ المرحلة ذو الخانتين): منه يُقارَن أوّلُ خانتين في اسم كلّ عضو.
المصدر: `validate_registry.py` → `REQUIRED_TAB_KEYS` و`name_problems`.

## ما يفحصه `validate_registry`
- حقولٌ ناقصة؛ `id` أو `order` مكرَّر؛ أعضاءٌ فوق `live_cap`؛ عضوٌ في تبويبين.
- اسمُ العضو: `TTSS · <اسم>`، وTT = `number` تبويبه (أو ما في `serial.carried_from`)، وSS ≥ 01، والطولُ ≤ `serial.max_title_len` (40).
- كلُّ عنوانٍ في `session_policy.core_sessions` مسجَّلٌ في تبويب.
- كلُّ `problem_types.*.tab` تبويبٌ أو اختصاصٌ موجود (أو `exec_*` حرفيّاً).
- مع `--sessions`: جلسةٌ حيّةٌ غيرُ مسجَّلة، ومسجَّلةٌ بلا جلسة (عدا بادئات `scheduled_task_title_prefixes` و`pending_archive`).
تشغيلٌ فعليّ 09-28: `--project schoolos --sessions projects/schoolos/sessions_snapshot.json` ⇒ «السجلُّ متّسق»، ورمزُ 0.

## جلساتُ المشاريع الأخرى في الشريط
`tabs.json` → `parked_other_projects`: «جلساتُ مشاريعَ أخرى (أبحاث، IELTS، لعبة): لا تُدار ولا تُؤرشف إلا بأمرٍ باسمها؛ يُقترح لها مجموعةٌ واحدة لتنظيف الشريط فقط»، والمجموعةُ المقترحة «مشاريع أخرى · أرشيف». النقلُ إليها بـ`maestro-tabs` وبموافقة التطبيق. ولا تُضاف أشجارُها إلى `session_names.json` الخاصّ بالمدرسة؛ إن أزعجت في «أشجارٌ بلا اسم» فمكانُها `ignored_trees.json` بقرار.

## أنماطٌ مضادّة
- قراءةُ `flow_metrics` أو `watch_once` لمشروعٍ في مستودعٍ آخر وتقديمُ أرقامها له.
- إضافةُ جلسات مشروعٍ آخر إلى `projects/schoolos/session_names.json` «لتختفي من التحذير».
- تشغيلُ `render_charters.py` لغير `schoolos`.
- وضعُ اسم المشروع الحاليّ في متغيّرٍ أو ملفٍّ «عامّ» تفترضه الجلساتُ اللاحقة — لا آليّةَ كهذه، والافتراضيُّ `schoolos` في كلّ أداة.
