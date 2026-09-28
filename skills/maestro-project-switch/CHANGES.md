# تغييراتُ maestro-project-switch (من 17 سطراً إلى مهارةٍ بمراجعها)

| البند | القديم | الجديد | السبب | الدليل |
|---|---|---|---|---|
| الوصف | عربيٌّ بسطرين، ثلاثُ كلماتٍ إنجليزيّة | إنجليزيٌّ ثمّ عربيّ بعباراتٍ عاميّة، والحدودُ مع maestro-tabs/spawn/archive-check وschoolos-platform وazkia | منعُ تفعيلها لتعديل تبويبات المدرسة | BRIEF.md §2 |
| allowed-tools | Read/Write و`validate_registry.py` | + Edit و`list_sessions` و`ls projects` وأدواتُ القياس القرائيّة؛ **بلا** `render_charters.py` | الإجراءُ يتحقّق بالقياس؛ `render_charters` يكتب فوق مواثيق المدرسة | شيفرةُ `render_charters.py` (`docs/tab_charters.md` ثابت) |
| «التبديل» | «مرِّر `--project` لـsession_load_v2 وrouting وwatch_once وvalidate_registry وarchive_check» | جدولُ ما يحترم `--project` وما هو مربوطٌ بـ`D:/shschool_mvp` | `--project` يبدّل الملفّات لا المستودع | `grep` في `tools/*.py`: `archive_check.gather`، `watch_once`، `flow_metrics`، `evidence_pack`، `owner_load_study`، `review_window` |
| «المشروع الحاليّ» | يُفترض حالٌ محفوظة | لا حالَ محفوظة؛ الافتراضيُّ `schoolos` في كلّ أداة | منعُ ملفِّ حالةٍ وهميّ | `--help` لكلّ أداة |
| الملفّات | ستّةٌ مسمّاة | سبعةٌ بجدول: من يقرأ كلّاً، وما يحدث إن غاب | `session_load_v2` يُرجع `{}` صامتاً لملفٍّ غائب | `session_load_v2.py::load_json`؛ تشغيلُ `validate_registry --project demo` (FileNotFoundError) |
| المشروعُ الجديد | «انسخ مجلّد schoolos وعدّل group_prefix والتبويبات…» | هيكلٌ أدنى مُجرَّبٌ بـ`validate()` و`render()`، وقائمةُ ما لا يُنسخ | النسخُ الكامل يحمل نواةَ المدرسة ومواثيقَها ومساراتها؛ و`group_prefix` صار فارغاً | تشغيلٌ 09-28 («السجلُّ متّسق»)؛ `tabs.json` (`group_prefix` = ""، `group_name_format`، D-46م) |
| التسمية | لا ذكر | `TTSS · <اسم>` ≤40 مفروضةٌ على كلّ مشروع | `validate_registry.name_problems` لا يستثني | الشيفرة؛ D-45م؛ تجربةٌ بأسماءٍ مخالفة 09-28 |
| المستودعُ الآخر | لا ذكر | ما يُقاس وما لا يُقاس، والصيانةُ لـ0102 بقرار | أرقامٌ مضلِّلةٌ من مستودع المدرسة | D-37م؛ ميثاقُ 0102 في `tabs.json` |
| المشاريعُ الأخرى | «لا يُدار بلا أمر؛ ما خارج المشروع لا يُمسّ» | + نصُّ `parked_other_projects` والتبويبُ المقترح، ولا إضافةَ لأشجارها في أسماء المدرسة | ترتيبُ الشريط لا يبرّر المساس | `tabs.json` → `parked_other_projects`؛ الذاكرة `feedback_never_archive_without_order.md` |
| الحوكمة | «أخبر الحوكمة (تملك تعريف التبويبات)» | أبلغ 0103 بملفّ مشروعٍ جديدٍ أو تعديل `session_policy`؛ تبويباتُ المدرسة لـ`maestro-tabs` | 0103 تحرس قواعدَ الجلسات بميثاقها | ميثاقُ 0103 في `tabs.json` |
| الاختبارات | لا ذكر | `test_package.py` لـschoolos وحده؛ `validate_registry` حارسُ الجديد | لا حارسَ آليّاً لمشروعٍ جديد | `tools/test_package.py` الأسطر 20–22؛ 82 اختباراً ناجحاً 09-28 |
| الفخاخ | لا شيء | خمسةُ فخاخٍ خطأ:/الصواب: ثبتت بالشيفرة أو التشغيل | — | المصادرُ في كلّ فخّ |
| المراجع | لا شيء | 00 ملفُّ المشروع والأدوات، 01 مشروعٌ جديد، 99 الاختبارات | الجسمُ ≤120 سطراً | الكرّاسة §2 |

## اختلافاتٌ بين المصادر والواقع
- النسخةُ السابقة تعدّ `archive_check` و`watch_once` قابلتين للتبديل بـ`--project`؛ الشيفرةُ تقرأ مستودعَ المدرسة ثابتاً.
- `render_charters.py` مذكورٌ في `PACKAGE.md` «مولّدُ المواثيق» دون ذكر أنّه يكتب ملفّاً واحداً مشتركاً أيّاً كان المشروع.
