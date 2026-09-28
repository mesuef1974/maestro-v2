# قراءةُ مخرج الفاحص
متى تقرأ هذا الملفّ: حين يُرجع `archive_check.py` مانعاً لا تعرف علاجه، أو حقلاً في `facts` لا تفهمه، أو حين تجهّز ملفَّ الجلسات لـ`validate_registry`.

## الأوامر (مُتحقَّقٌ منها بـ`--help` يوم 09-28)
```
python C:/Users/mesue/delivery_manager_work/tools/archive_check.py <مجلّد-الشجرة> --title "<العنوان>" [--running] [--shared N] [--project schoolos]
python C:/Users/mesue/delivery_manager_work/tools/validate_registry.py [--sessions <ملف.json>] [--project schoolos]
python C:/Users/mesue/delivery_manager_work/tools/watch_once.py [--json] [--no-live] [--project schoolos]
```
- `<مجلّد-الشجرة>` اسمٌ لا مسار (`basename` لـ`cwd`). شجرةٌ غيرُ موجودةٍ في `git worktree list` ⇒ خروجٌ بـ«لا شجرةَ باسم …».
- `--project` يغيّر ملفَّ `tabs.json` وحدَه؛ المستودعُ ثابتٌ `D:/shschool_mvp` في الشيفرة (`gather(repo=…)`).
- الفاحصُ قراءةٌ فقط: `git rev-list/reflog/cherry/status --no-optional-locks` و`gh pr list`. لا `fetch`؛ فإن كان `origin/main` قديماً فشغّل قبله `session_load_v2.py` (يجلب) أو اقبل أنّ القياسَ على آخر جلب.
- `validate_registry --sessions` يأخذ **ملفَّ JSON فيه مصفوفةُ عناوين** (مثل `projects/schoolos/sessions_snapshot.json`)، لا مخرجَ `list_sessions` كاملاً. يُرجع «السجلُّ متّسق» ورمزَ 0، أو قائمةَ مشكلاتٍ ورمزَ 1.

## الحقول
| الحقل | معناه | من أين |
|---|---|---|
| `eligible` | لا مانعَ واحداً | `evaluate` |
| `reason` | سطرُ نافذة الموافقة، مقصوصٌ على 400 حرف | يُنسخ حرفيّاً |
| `facts.open_prs` | طلباتٌ مفتوحةٌ رأسُها في `rev-list` الشجرة أو في `reflog` لها | gh + git |
| `facts.cherry_plus` | إيداعاتٌ «+» في `git cherry origin/main HEAD` | معلومةٌ؛ لا تمنع إن عُرفت حالةُ الطلب |
| `facts.branch_status` | حكمُ `branch_status.classify_tree` | الجدولُ التالي |
| `facts.branch_prs` | أرقامُ الطلبات التي بُني عليها الحكم | gh |
| `facts.dirty_files` | أسطرُ `git status --porcelain` | git |
| `facts.running` / `shared_with` | **ما أعطيتَه أنت** في `--running` و`--shared` | `archive_inputs.py` |
| `facts.handover_saved` | وجودُ `handover_notes/<الشجرة>.md` (لا يقرأ محتواه) | نظامُ الملفّات |
| `facts.warnings` | فشلُ git أو gh؛ `branch_status: null` يعني تعذّر gh | — |

## حالاتُ الفرع وعلاجُها
| الحالة | نصُّها في `reason` | تمنع؟ | العلاج |
|---|---|---|---|
| `open_pr` | (يظهر في «طلبات مفتوحة») | نعم | الطلبُ يمضي في الفلو؛ الأرشفةُ بعد دمجه ونشره |
| `merged` | اندمج بطلبه | لا | تحقّق من النشر والخارطة يدويّاً |
| `merged_elsewhere` | اندمج عبر طلب فرعٍ آخر | لا | كذلك |
| `merged_dirty` | اندمج وفيه ملفّاتٌ غيرُ مودَعة | نعم (بالملفّات) | يراجعها صاحبُها: تُودَع طلباً أو تُحفظ خارج المستودع قبل أيّ شيء — الإزالةُ تمحوها، وحزمةُ `git bundle` لا تحملها |
| `work_after_merge` | إيداعاتٌ بعد دمج طلبه | نعم | اسأل صاحبها: طلبٌ جديد أم مستبدَل؟ |
| `closed_unmerged` | طلبٌ مغلقٌ بلا دمج | نعم | قرارُ المالك: مستبدَلٌ (مثالُ #699 الذي أغنى عنه #693، D-22) أم يُعاد فتحه |
| `no_pr` | عملٌ بلا طلب | نعم | عملٌ غيرُ مدفوع: صاحبُه يدفعه بالفلو أو يقرّر المالكُ إهمالَه |
| `clean` | لا عملَ خارج main | لا | — |
المصدر: `tools/branch_status.py` (`LABEL_AR`، `classify_tree`)، و`watch_once.py` (`ORPHAN_ACTION`).

## أمثلةٌ حقيقيّة (09-28 ~21:00، قراءةٌ فقط)
- `vision-footer`: `cherry_plus: 4`، `branch_status: merged` (#714) ⇒ المانعُ الوحيد «لا مذكّرةَ تسليمٍ محفوظة». الإيداعاتُ الأربعة أثرُ السحق لا عملٌ ضائع.
- شجرةُ «0404 · …» بـ`--running --shared 1`: ثلاثةُ موانع — «تعمل الآن» و«لا مذكّرة» و«الشجرةُ مشتركةٌ مع 1 جلسةً أخرى (تُؤرشَف معها)»، مع `cherry_plus: 10` و`merged` (#710).
- شجرةُ 0501 بعنوانها: مانعٌ واحد «جلسةٌ ثابتةٌ من النواة» — مع أنّ `handover_saved: true` (مذكّرةُ جلسةٍ سابقة).

## سطرُ السبب حين تكون أهلاً
صيغتُه من الشيفرة: «أرشفةُ «<العنوان>»: لا طلبَ مفتوح · <حالةُ الفرع ورقمُ الطلب> · 0 ملفّ غيرُ مودَع · غيرُ دائمة · لا تعمل الآن · مذكّرةُ تسليمٍ محفوظة · العودةُ بـunarchive_session». لا تُضِف إليه وعوداً لم يفحصها («ونُشر»، «والخارطةُ محدّثة») إلّا وقد تحقّقتَ منها في الخطوة 5، وبعبارةٍ تذكر مصدرَها.

## أنماطٌ مضادّة
- تشغيلُ الفاحص بلا `--shared` لأنّ «الشجرةَ تبدو لجلسةٍ واحدة».
- إعادةُ صياغة `reason` بعباراتٍ أجمل: المالكُ يوافق على ما يقرأ، والفاحصُ هو ما يُحاسَب عليه.
- قراءةُ `branch_status: null` حكماً بالسلامة.
- إزالةُ الشجرة أو الفرع يدويّاً «لأنّ الفاحص قال أهلاً» — ذلك لأمين المستودع بفحوصه.
