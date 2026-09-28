# CHANGES — maestro-evidence

الأصل: `C:/Users/mesue/delivery_manager_work/skills/maestro-evidence/SKILL.md` (16 سطراً). الجديد: SKILL.md (54) + مرجعان + حالاتُ الاختبار + `scripts/tag_card.py` (112 سطراً، مجرَّب).

| البند | القديم | الجديد | السبب | الدليل |
|---|---|---|---|---|
| مرحلتا الحزمة | `evidence_pack.py <رقم>` وحده | قبل الدفع: الفرعُ و`tag_card.py --branch`؛ بعده: `evidence_pack.py` | في الفلو الحاليّ البندُ يُعرض قبل أن يكون طلباً، والأداةُ تقرأ GitHub وحده | CLAUDE.md «الفلو» (لا طلبَ قبل الاعتماد)؛ `evidence_pack.py` (`fetch`) |
| تسجيلُ النتيجة | `ledger.py move <id> ready_for_review` | `tag_card.py … --apply` (حدثُ update: tier/category/area/flags/head/pr) | `move` لا يكتب الخطورة؛ و`review_window.py` يجمع بها | قراءةُ `ledger.py` و`review_window.py`؛ تجربةٌ على نسخة |
| سكربتٌ جديد | — | `scripts/tag_card.py`: عرضٌ افتراضاً، `--apply` للكتابة، رفعٌ بسببٍ ولا خفض، `LEDGER_PATH` للتجربة | عملٌ حتميٌّ متكرّرٌ قبل كلّ نافذة | اختباراتٌ 09-28: فرعٌ، طلب #725، مسارات، رفضُ الخفض، رفضُ بلا سبب، بطاقةٌ مجهولة، فرعٌ مجهول؛ السجلُّ الأصليّ لم يتغيّر (md5 قبل/بعد) |
| حكمٌ فوق الأداة | «التصنيفُ تقريبيّ» | جدولُ ما تُخطئه بمساراتٍ حقيقيّة | الجلسةُ تحتاج أمثلةً لا تحذيراً | `risk_tier.py` على `core/middleware_rls.py` و`api/views_erasure.py` و`shschool/settings/*` ⇒ medium؛ `templates/base/base.html` بلا علامة (القالبُ الأساسيّ ليس `templates/base.html` على main) |
| ثلاثُ نقاط | غيرُ مذكور | `git diff --name-only origin/main...<الفرع>` | نقطتان تضخّمان الفرق | سلوكُ git |
| سطرُ الاعتماد | «غائبٌ ⇒ لا يدخل كمعتمَد» | الصيغةُ الحرفيّة للأداة؛ وجودُه ليس دليلَ معاينة؛ مطابقةُ الرأس | #725 اعتُمد ثمّ أُصلح بعده | `evidence_pack.py` (APPROVAL)؛ السجلّ الزمنيّ 09-28؛ `gh pr view 725` (رأسان: 570eef88 ثمّ 2cb2bd25) |
| الاستثناءُ الانتقاليّ | غيرُ مذكور | «مشمولٌ باستثناء الفلو» لا يصحّ لطلبٍ جديد | الأداةُ ما زالت تقبل الصيغة | D-09، D-10؛ `evidence_pack.py` (EXEMPT) |
| الفحوصُ قبل الدفع | غيرُ مذكور | «مُعلَنةٌ من الجلسة» لا «خضراء» | لا CI على إيداعٍ محلّيّ | `approvals_policy.md` §6 |
| حالةُ الدمج | غيرُ مذكور | UNKNOWN بعد الدمج؛ الحقيقةُ من `--json state,mergedAt` | لُوحظ على #725 و#713 | تشغيلُ `evidence_pack.py` 09-28 |
| --help | غيرُ مذكور | الأداتان بلا مساعدة (ValueError؛ «--help» يُصنَّف مساراً) | منعُ هدرٍ وسوءِ فهم | تشغيلُ `--help` 09-28 |
| الخطورةُ العالية | «اطلب ملخّص الهجرة» | ثلاثةُ أسئلةٍ محدّدة، وما لم يُجب «لم يُذكر» | لا ملءَ بالتقدير | `evidence_pack_spec.md`؛ CLAUDE.md «الهجرات» |
| allowed-tools | evidence_pack وrisk_tier و`gh pr view` | + `tag_card.py` و`ledger show/list` و`git worktree list` و`git diff --name-only` و`git rev-parse` | ما يلزم الإجراء قراءةً | `--help` وتجارب |
| الفخاخ | لا شيء | سبعةُ فخاخ | وقائع وتجارب | D-39م (#713)؛ #725؛ تجاربُ risk_tier |
| حالاتُ الاختبار | لا شيء | `references/99-test-cases.md` | إلزاميّ | الكرّاسة §2 |

## ملاحظةٌ للتبنّي
مسارُ السكربت في allowed-tools يفترض نسخَ المهارة إلى `C:/Users/mesue/delivery_manager_work/skills/maestro-evidence/`. والأصحُّ على المدى البعيد أمرٌ `tag` في `ledger.py` نفسه (المايسترو يصون أدواته، D-37م)، ثمّ يُحذف السكربت.
