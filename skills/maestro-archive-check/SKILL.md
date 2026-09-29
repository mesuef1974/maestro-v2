---
name: maestro-archive-check
description: |
  Use before archiving any Claude Code session of the SchoolOS project: decides eligibility with tools/archive_check.py (core sessions blocked, open PRs, branch judged by its PR state in gh not by rev-list because merges are squashed, uncommitted files, running, handover note, shared worktree) and produces the exact approval reason for archive_session. Trigger on: archive session, archive_session, finished/idle session, sidebar cleanup, "is this session done", unarchive, "أرشف"، «نظّف الشريط»، «الجلسة خلصت»، «من يُؤرشف؟»، «الخاملة تُؤرشف»، ولو لم يُذكر الفحص.
  استخدمها قبل أيّ طلبِ أرشفةٍ لجلسةٍ في مشروع المدرسة، وعند سؤال «هل انتهت هذه الجلسة؟»، وبعد اندماج عمل جلسةٍ مرنةٍ في 04 ونشره.
  ليست لـ: حذفِ جلسة (ممنوعٌ أبداً)، ولا إزالةِ الأشجار أو الفروع (أمينُ المستودع)، ولا فتحِ الجلسات وتسميتها (maestro-spawn وschoolos-flow)، ولا جلساتِ المشاريع الأخرى (بأمرٍ باسمها فقط)، ولا نقلِ الجلسات بين التبويبات (maestro-tabs).
allowed-tools: Read, Write, mcp__ccd_session_mgmt__list_sessions, Bash(python .claude/skills/maestro-archive-check/scripts/archive_inputs.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/archive_check.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/archive_sweep.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/validate_registry.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/watch_once.py:*), Bash(bash scripts/preview.sh status)
---

# فحصُ أهليّة الأرشفة

الغرض: ألّا تُؤرشف جلسةٌ فيها عملٌ حيّ، أو جلسةٌ من النواة، أو جلسةٌ تجرّ معها جلسةً أخرى تشاركها الشجرة — وأن يرى المالكُ في نافذة الموافقة سبباً صادقاً قابلاً للتحقّق.
الأرشفةُ في التطبيق توقف عمليّةَ الجلسة، و**تُزيل شجرتَها افتراضيّاً**، و**تؤرشف معها كلَّ جلسةٍ تشاركها الشجرة** (المصدر: وصفُ أداة `archive_session`). فالخطأ هنا يمحو ملفّاتٍ غيرَ مودَعة ويُسقط جلسةً عاملة.

## من يملك قرارَ الأرشفة
- **المايسترو (0101) وحدَه** مفوَّضٌ بأرشفة الجلسات **المنتهية** بالضوابط (D-07؛ الذاكرة `feedback_never_archive_without_order.md`، استثناءُ 09-26).
- غيرُه (ومنه 0103 · الحوكمة التي تستعمل الفحصَ للكشف) لا يؤرشف إلّا بأمرٍ صريحٍ من المالك **باسم الجلسة**.
- **لا أرشفةَ لجلسةٍ عاملةٍ حتى تنتهي** (D-27م)، ولا لجلسةٍ من النواة الثابتة (D-43م، D-47م..D-51م). جلساتُ المشاريع الأخرى لا تُمسّ إلّا بأمرٍ باسمها (`tabs.json` → `parked_other_projects`).
- **أرشفةٌ لا حذف:** `delete_session` ممنوعٌ على كلّ الجلسات (D-38م). متى تُؤرشف المرنةُ في الفلو: `schoolos-flow`.

## الإجراء
0. **الطريقةُ الافتراضيّة — المكنسة (D-75م):** نادِ `list_sessions` واحفظ مخرجَه JSON ثمّ:
   `python C:/Users/mesue/delivery_manager_work/tools/archive_sweep.py --sessions <الملف> --write-notes` (≈50 ث).
   تفحص كلَّ جلسةٍ مرنةٍ في 04 بفحوص الخطوات 1–4، **وتفحص النشرَ** (هل بلغ الطلبُ المدموجُ الإنتاجَ الحيّ؟ من `/health/`) **والخارطةَ** (هل ذُكر رقمُ الطلب في هجرة roadmap على main؟)، وتكتب مذكّرةَ التسليم من الحقائق **للجاهزات وحدَها**. ثمّ لكلّ «جاهزة»: `archive_session`، وبعده `python C:/Users/mesue/delivery_manager_work/tools/archive_sweep.py --record-archived "<العنوان>" ...` يحدّث tabs.json (members ← archived_log) ثمّ `validate_registry.py`. **متى:** بعد كلّ إبلاغ 0601 بنشرٍ متحقَّق، وفي موجز اليوم بعد النافذة. الخطواتُ 1–7 أدناه للحالة التي تحتاج حكماً (شجرةٌ مشتركة، خارطةٌ بلا بند لطلبٍ وثائقيّ).
1. **اجمع الحقائق من التطبيق، لا من الذاكرة.** نادِ `list_sessions` (بلا `include_archived`، `limit` 50)، واحفظ مخرجَه JSON في ملفٍّ مؤقّت، ثمّ:
   `python .claude/skills/maestro-archive-check/scripts/archive_inputs.py --sessions <الملف> --title "<العنوان حرفيّاً>"`
   يعطيك: الشجرة (من `cwd`)، `is_core`، `running`، `pinned`، **`shared_with` بأسمائها**، و`note_names_this_session`، وسطرَ `archive_check_cmd` جاهزاً.
2. **`is_core: true` ← قف.** لا فحصَ ولا طلب؛ النواةُ لا تُؤرشف (المصدر: `archive_check.py::permanent_titles` يقرأ `session_policy.core_sessions`).
3. **شغّل الفاحص بالسطر الجاهز** (قراءةٌ فقط: git وgh):
   `python C:/Users/mesue/delivery_manager_work/tools/archive_check.py <الشجرة> --title "<العنوان>" [--running] --shared <N>`
4. **اقرأ `blockers` وعالج كلّاً بما يخصّه** (الجدولُ الكامل في `references/01-tool-output.md`):
   - «لا مذكّرةَ تسليمٍ محفوظة» ← اكتبها الآن بالقالب في `references/02-handover-note.md` ثمّ أعِد الخطوة 3.
   - «الشجرةُ مشتركة…» ← لا تُؤرشف حتى تنتهي **كلُّ** جلسةٍ في `shared_with` وتحمل مذكّرتَها؛ ثمّ يكون السببُ شاملاً لها بأسمائها.
   - «طلباتٌ مفتوحة» / «عملٌ بلا طلب» / «إيداعاتٌ بعد دمج طلبه» / «طلبٌ مغلقٌ بلا دمج» ← عملٌ حيّ: اسأل صاحبها، لا تُؤرشف.
   - «تعمل الآن» ← انتظر؛ التطبيقُ يرفضها أصلاً.
5. **تحقّق يدويّاً ممّا لا يفحصه الكود.** شرطُ الأرشفة في `tabs.json` → `archive_when`: «بعد الدمج **والنشر** + الخارطةُ محدَّثة». الفاحصُ يرى الدمجَ وحدَه: تأكّد أنّ طلبَها في الإنتاج (`bash scripts/preview.sh status` من شجرتك يقارن main بـ`commit` في `/health/`) وأنّ 0701 سجّلت البند.
6. **`eligible: true` ← اطلب `archive_session`** وسببُ الموافقة (`reason`) هو حقلُ `reason` من الفاحص **حرفيّاً** (≤400 حرف). طلبٌ واحدٌ لكلّ جلسة؛ والتطبيقُ يطلب موافقةَ المالك على كلّ استدعاء.
7. **بعد الأرشفة:** انقل العنوانَ من `members` إلى `archived_log` في `tabs.json` بالقرار والتاريخ (سابقةُ D-40م وD-43م)، ثمّ `python C:/Users/mesue/delivery_manager_work/tools/validate_registry.py --sessions <ملفّ JSON بقائمة عناوين list_sessions الحيّة>` حتى «السجلُّ متّسق»؛ وأبلغ المالكَ بالقائمة وسببِ كلٍّ وطريقةِ العودة (`unarchive_session`)؛ وسجّل السطرَ في السجلّ اليوميّ (`maestro-handover`).

## قواعدٌ وسببُها
- **«مدموج» بحالة طلب الفرع في gh، لا بـ`rev-list` ولا `git cherry`.** الدمجُ بالسحق يصنع إيداعاً جديداً فيبقى كلُّ إيداعٍ في الفرع «غيرَ مدموج» بالعدّ. مثالٌ حيّ (09-28): `vision-footer` يُظهر `cherry_plus: 4` وحالتُه `merged` بـ#714، فلا يمنع. المصدر: `tools/branch_status.py` (docstring)، والذاكرة `feedback_worktree_removal_safety_checks.md` البند 4.
- **الفاحصُ يثق بما تعطيه:** `--running` افتراضُه «لا تعمل» و`--shared` افتراضُه 0، و«المذكّرةُ محفوظة» = وجودُ `handover_notes/<الشجرة>.md` أيّاً كان كاتبُها. لذلك تأتي هذه القيمُ من `list_sessions` عبر السكربت لا من التقدير. المصدر: `archive_check.py::gather/main`.
- **إن تعذّر gh** فالفاحصُ يرجع إلى `git cherry` احتياطاً فيمنع بأيّ إيداعٍ ظاهر؛ و`facts.warnings` تقول ذلك. لا تتجاوزه: أصلِح `gh auth` وأعِد.
- **ذاكرةٌ حمراء ليست سبباً للأرشفة:** إجراءُ «red» في `thresholds.json` نصُّه «لا أرشفةَ إلا بأمره أو ضمن تفويض المنتهية»؛ خفّف بإيقاف الخوادم الخاملة (`watch_once.py`).

## فخاخٌ وقعت فعلاً
- خطأ: أرشفةُ جلسةٍ من النواة ضمن دفعة «الخاملة»: «0201 · أمين البلاغات» أُرشفت خطأً في D-43م واستُعيدت في D-47م.
  الصواب: قائمةُ النواة من `tabs.json` تُفحص أوّلاً (الخطوة 2)؛ «خاملة» لا تعني «منتهية».
- خطأ: الحكمُ «يتيمةٌ فيها عملٌ غيرُ مدموج» من عدّ الإيداعات: إنذاراتٌ كاذبةٌ لـ`vision-footer` (#714) و`qcc-collectors` (#707) قبل إصلاح 09-28 (`docs/TODO_after_transition.md` البند 1).
  الصواب: `branch_status` وحده يحكم؛ وعددُ `cherry_plus` معلومةٌ لا مانع.
- خطأ: نسيانُ `--shared`: شجرةُ `priceless-snyder-945a8f` كانت لجلستين («مسار الديون التقنيّة» و«تقييم ملفات مايسترو الإدارية (fork)») فأُرشفتا معاً بمذكّرةٍ واحدة (D-43م).
  الصواب: `shared_with` بأسمائها في السبب، ولا طلبَ حتى تنتهي كلُّها.
- خطأ: قبولُ `handover_saved: true` في شجرةٍ أُعيد استعمالُها: `magical-montalcini-c69014` مذكّرتُها لـ«مسار الجودة» المؤرشَف، وفيها اليوم 0501.
  الصواب: `note_names_this_session: false` ⇒ مذكّرةٌ جديدةٌ لهذه الجلسة (القسم «شجرةٌ أُعيد استعمالُها» في `references/02-handover-note.md`).
- خطأ: «`eligible: true` ثمّ احفظ المذكّرة» (النسخةُ السابقة من هذه المهارة): الفاحصُ لا يُرجع `true` بلا مذكّرة أصلاً.
  الصواب: المذكّرةُ قبل الفحص الأخير.
- خطأ: قراءةُ «تمام» على مقترحٍ مركَّبٍ أمراً بالأرشفة: أُرشفت جلستان 09-25 ثمّ أُعيدتا بـ`unarchive_session` (الذاكرة `feedback_never_archive_without_order.md`).
  الصواب: خارج تفويض المنتهية: الأمرُ باسم الجلسة، والموافقةُ على مقترحٍ مركَّبٍ لا تشمل بندَ الأرشفة ما لم يُسمَّ.
- خطأ: مذكّرةٌ بجملةٍ منسوخة لا تصدق عليها: «مدموجةٌ ومنشورةٌ ضمن 4aa8069 إن وُجدت» في شجرةٍ حالتُها `clean` بلا طلب (مذكّراتُ D-43م).
  الصواب: كلُّ سطرٍ في المذكّرة من `facts` للفاحص أو من مصدرٍ مسمّى.

## ما ليس لهذه المهارة
حذفُ الجلسات؛ إزالةُ الأشجار والفروع وحزمُ الأرشيف (أمينُ المستودع بفحوصه)؛ فتحُ الجلسات وتسميتُها (`maestro-spawn`)؛ نقلُها بين التبويبات (`maestro-tabs`)؛ خطواتُ الفلو قبل الأرشفة (`schoolos-flow`).

## المراجع
| الملفّ | متى تقرأه |
|---|---|
| `references/00-authority-and-model.md` | قبل أوّل أرشفةٍ في الجلسة، أو إن شككتَ هل لك أن تؤرشف هذه الجلسة |
| `references/01-tool-output.md` | لتفسير حقلٍ أو حالةٍ من مخرج الفاحص، أو مانعٍ لا تعرف علاجه |
| `references/02-handover-note.md` | حين يكون المانعُ «لا مذكّرة»، أو الشجرةُ أُعيد استعمالُها |
| `references/99-test-cases.md` | عند تعديل هذه المهارة أو وصفها |
