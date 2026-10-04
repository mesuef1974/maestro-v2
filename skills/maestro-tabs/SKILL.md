---
name: maestro-tabs
description: |
  Use for keeping the Claude app sidebar of the SchoolOS project identical to the registry projects/schoolos/tabs.json: audit consistency (validate_registry.py --sessions <file>), plan and execute group create/rename and session moves/renames with the owner's in-app approval, verify afterwards, and apply an owner's structural decision on stages 01..08 to tabs.json then regenerate docs/tab_charters.md. Trigger on: sidebar, groups, tabs, stages, move session to its group, rename session, session outside its tab, "السجلّ غير متّسق", tab charters, live_cap, core sessions, TTSS numbering.
  استخدمها عند: «رتّب الشريط»، «انقل الجلسة لمجموعتها»، «في جلسة برّا التبويبات»، «عدّل التبويب/المرحلة»، «غيّر اسم الجلسة»، «حدّث المواثيق»، «validate_registry طلع مشاكل».
  ليست لـ: فتح جلسةٍ مرنةٍ وتسميتها أوّلَ مرّة (maestro-spawn)، أرشفة جلسة (maestro-archive-check)، اختيار جلسةٍ لبطاقة (maestro-load-check)، شرح الفلو نفسه (schoolos-flow)، جلسات المشاريع الأخرى (لا تُمسّ إلّا بأمرٍ باسمها).
disable-model-invocation: true
allowed-tools: Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/tools/validate_registry.py:*), Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/tools/render_charters.py), Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/tools/session_load_v2.py:*), mcp__ccd_sidebar__list_groups, mcp__ccd_session_mgmt__list_sessions, Read, Write, Edit
---

# التبويبات: الشريطُ مرآةُ السجلّ

الغرض: أن يطابق الشريطُ في التطبيق `projects/schoolos/tabs.json` في كلّ لحظة — مجموعةٌ لكلّ مرحلةٍ من الفلو، وكلُّ جلسةٍ حيّةٍ في مرحلتها باسمٍ مرقّم — وأن يدخل كلُّ قرارٍ بنيويٍّ للمالك السجلَّ والمواثيقَ قبل أن يُبلَّغ.
المصدر: `tabs.json` (المصدرُ الوحيد؛ المجموعةُ في التطبيق اسمٌ فقط والميثاقُ في السجلّ)، وD-38م وD-43م..D-55م، و`flow_changelog.md` — في `C:/Users/mesue/delivery_manager_work/`.

## الإجراء: مزامنةُ الشريط
1. **اقرأ الواقع:** `list_groups` و`list_sessions`، واكتب عناوينَ جلسات المشروع الحيّة قائمةَ JSON في `projects/schoolos/sessions_snapshot.json`.
2. **دقّق:**
   ```bash
   python -X utf8 C:/Users/mesue/delivery_manager_work/tools/validate_registry.py \
     --sessions C:/Users/mesue/delivery_manager_work/projects/schoolos/sessions_snapshot.json
   ```
   المطلوب حرفيّاً «السجلُّ متّسق» (رمز 0). `--sessions` مسارُ ملفّ لا عناوين. معاني الرسائل في `references/00-registry-map.md`.
3. **خطِّط وأعرض قبل أوّل استدعاءٍ مُغيِّر:** جدولٌ (الجلسة/المجموعة، الآن، المطلوب، السبب بقرارٍ أو حقلٍ في tabs.json). المالكُ يوافق على الخطّة ثمّ على كلّ استدعاءٍ في التطبيق.
4. **نفِّذ بأدوات الشريط** بالترتيب: `create_group` (نادراً) ← `rename_group` ← `set_session_title` ← `move_sessions`. اسمُ المجموعة «NN · <اسمُ المرحلة>» كما في `tabs[].number` و`name` (`group_name_format`).
5. **تحقّق:** `list_groups` (أعدادُ الأعضاء = `members` لكلّ مرحلة) وأعِد الخطوة 2. وحدِّث `session_names.json` لكلّ إعادة تسمية (مجلّدُ الشجرة ← الاسم) وإلّا صارت الشجرةُ يتيمةً في `session_load_v2`.

## الإجراء: قرارٌ بنيويٌّ من المالك (مرحلة، نواة، حدّ، مهارة، ميثاق)
1. القرارُ نصّاً من المالك؛ لا اقتراحُ جلسة. يراجعه «0103 · الحوكمة: حراسةُ القواعد» مقابل القواعد القائمة قبل التسجيل (ميثاق 0103).
2. سطرٌ في `decisions.md` بالرقم التالي `D-NNم` ووقتٍ من الساعة، وسطرٌ في `flow_changelog.md` برقم إصدارٍ جديد — لا إبلاغَ قبلهما (قواعدُ التغيير في `flow_changelog.md`).
3. عدِّل `tabs.json` بـEdit موضعيّاً ← المدقّقُ (الخطوة 2 أعلاه) ← `python -X utf8 C:/Users/mesue/delivery_manager_work/tools/render_charters.py` (بلا وسائط؛ يكتب `docs/tab_charters.md` ويطبع «docs/tab_charters.md ✔»).
4. طبِّق على الشريط بالإجراء الأوّل، وأبلغ الجلساتِ المعنيّةَ برسالةٍ أوّلُها «الفلو v<الجديد>»، وCLAUDE.md بطلبٍ يمرّ بالفلو عبر 0103 إن مسّ نصَّه.
التفصيلُ وأمثلةُ D-46م..D-55م في `references/01-structural-change.md`.

## القواعد وأسبابها
- الجلساتُ المرنةُ في 04 وحدها ولا تنتقل بين المراحل؛ تعلن لـ0501 وتبقى (D-47م ألغى نقلَ D-46م). فجلسةٌ مرنةٌ في 05 أو 06 خطأٌ يُصحَّح بإعادتها إلى 04.
- الاسمُ «TTSS · <اسمٌ معبّر>»، TT رقمُ المرحلة وSS أقدميّةُ الإنشاء فيها، ≤ 40 حرفاً، والرقمُ ثابتٌ للجلسة ولا يُعاد لغيرها بعد أرشفتها: الشريطُ أبجديٌّ فالرقمُ وحده يرتّب (D-44م، D-45م).
- لا تثبيتَ (Pinned): يُخرج الجلسةَ من مجموعتها (D-44م).
- لا حذفَ لمجموعة ولا لجلسة؛ «08 · مهامّ مجدولة» قد تفرغ وتبقى، والجلسةُ تُؤرشف لا تُحذف (D-38م).
- النواةُ الثابتة (`session_policy.core_sessions`، ثلاث عشرة اليوم) لا تُؤرشف ولا تُنقل من مرحلتها؛ وحدودُ المراحل من `live_cap` (04 = 10 للمرنة، والنواةُ خارجه — D-51م).
- `docs/tab_charters.md` مولَّدٌ لا يُحرَّر: كلُّ تعديلٍ يدويٍّ يمحوه التوليدُ التالي.
- جلساتُ المشاريع الأخرى لا تُنقل ولا تُسمّى إلّا بأمرٍ باسمها (`parked_other_projects`).

## فخاخٌ وقعت فعلاً
- خطأ: اتّباعُ `docs/sidebar_migration_plan.md` «خطّةً حاليّة» (كما قال الأصل) ← مجموعاتٌ بأسماء 09-26 («مشروع المدرسة · القيادة…») ألغتها D-38م ثمّ D-46م. الصواب: `tabs.json` وحده؛ الخطّةُ تاريخ.
- خطأ: الأخذُ بسطر `principle` في tabs.json («الجلسةُ تنتقل بينها بتقدّم عملها») ← نصٌّ من D-46م لم يُحدَّث. الصواب: `session_policy.stage_moves` (D-47م).
- خطأ: `render_charters.py --help` ← يعدّ `--help` اسمَ مشروعٍ ويسقط بـFileNotFoundError؛ والتشغيلُ بلا وسائط **يكتب** الملفّ. الصواب: شغّله عمداً بعد التدقيق فقط.
- خطأ: `validate_registry.py --sessions "0101 · المايسترو"` ← يحاول فتحَ ملفٍّ بهذا الاسم. الصواب: مسارُ `sessions_snapshot.json`.
- خطأ: أرشفةُ «0201 · البوابة: البلاغاتُ والطابور» مع الخاملات في D-43م ← كانت ثابتةً بقرار 09-25، فأُعيدت في D-47م. الصواب: قارن بـ`core_sessions` قبل أيّ إخراجٍ من الشريط.
- خطأ: أوقاتُ D-40م..D-49م كُتبت تقديراً متقدّماً على الساعة وصُحّحت بسطرٍ لاحق. الصواب: وقتُ القرار من الساعة (`date -u -d '+3 hours'`).
- خطأ: إبلاغُ الجلسات بترتيبٍ جديدٍ قبل سطره في `flow_changelog.md` ← صيغتان متتاليتان لقاعدةٍ واحدة (سابقة 09-26). الصواب: قرارٌ ← سطرٌ ← رقمٌ ← إبلاغ.

## مثال (مختلَق)
المدخل: المدقّقُ يقول «جلسةٌ حيّةٌ غيرُ مسجَّلة: «0405 · إدارة: تنبيه التوجيه (W-008)»» و«مسجَّلةٌ بلا جلسةٍ حيّة: «0401 · واجهة: حذف الطباعة (W-003)»». ← المعنى: 0405 فُتحت ولم تُسجَّل، و0401 أُرشفت ولم تُحذف من الأعضاء. ← Edit لـ`tabs.json` (أضِف 0405، احذف 0401 وأضِف سطرها إلى `archived_log`، وتأكّد أنّ `per_tab_next["04"]` = 6)، و`session_names.json`، واللقطة ← «السجلُّ متّسق» ← `render_charters.py` ← `list_groups` يُظهر 04 بأربعة أعضاء.

## المراجع
| الملف | متى تقرؤه |
|---|---|
| `references/00-registry-map.md` | لمعنى حقول tabs.json، والمراحل ونواتها وحدودها، ورسائل المدقّق، وما يقرأ كلَّ ملفّ |
| `references/01-structural-change.md` | قبل تطبيق قرارٍ بنيويٍّ للمالك، وفحصُ انحراف المواثيق بلا كتابة |
| `references/99-test-cases.md` | عند مراجعة الوصف واختبار التفعيل |
