# CHANGES — maestro-review-window

الأصل: `C:/Users/mesue/delivery_manager_work/skills/maestro-review-window/SKILL.md` (16 سطراً). الجديد: SKILL.md (55) + أربعةُ مراجع.

| البند | القديم | الجديد | السبب | الدليل |
|---|---|---|---|---|
| من يبني النافذة | «أرسل للمالك» بصوت المايسترو | «0501 · المعاينة: اعتمادُ المالك على 8500» وحدها تثبّت وتعدّ النافذة وتسجّل؛ المايسترو يطلب فتحَها إن غابت | الفلو v2.6+ نقل المرحلة 05 إلى جلسةٍ ثابتة | D-47م، D-50م؛ `tabs.json` → 0501 و`stage_moves` |
| الوصف والتفعيل | «Trigger on: review window…» مع `disable-model-invocation: true` | وصفٌ بلغتين بحالاتٍ عاميّة و«ليست لـ»؛ حُذف `disable-model-invocation` | المهارةُ عملُ 0501 اليوميّ ويجب أن تُفعَّل عند ردّ «وش ينتظرني» أو وصول «جاهز» | `tabs.json` → 0501 skills؛ الكرّاسة §1 (الوصفُ آليّةُ التفعيل) — **يحتاج تأكيدَ المايسترو** |
| allowed-tools | review_window/ledger/evidence_pack كاملة، `preview.sh status` و`integrate plan` | أوامرُ فرعيّةٌ محدّدة (`render` لا `apply`، `ledger list/show`)، و`pin`/`release`/`list`، و`risk_tier.py` و`tag_card.py` و`git worktree list` و`date -u` | أضيقُ صلاحيّةٍ تكفي؛ `apply` لمهارة approvals؛ 0501 تملك pin/release | `tabs.json` → 0501 permissions؛ `--help` لكلّ أداة 09-28 |
| وسمُ البطاقات | «سجّل الخطورةَ والمسار في بطاقته (`ledger.py`)» | `tag_card.py --apply` قبل `render` | `ledger.py` لا أمرَ فيه يكتب tier/area؛ بلا وسمٍ كلُّ البطاقات حزمةٌ واحدة «? · ?» low | قراءةُ `ledger.py`؛ تجربةٌ على نسخةٍ بـ`LEDGER_PATH`: `{'1': [W-…-001, W-…-005]}` ثمّ حزمتان و`high: [1]` بعد الوسم |
| السعة | «حزمٌ بحدّ السعة المرن» | 6 للنافذة عاديّاً و10 مرتفعاً، من `thresholds.json`؛ «≤8» في القالب أقدم | الأداةُ تقرأ `per_window` | `thresholds.json` → `owner_capacity`؛ `review_window.py` (`CAPS`) |
| سطرُ الفلو | غيرُ مذكور | صحّحه من `flow_changelog.md` | `render` يكتب v2.1 ثابتاً | `review_window.py` (`flow_version="v2.1"`)؛ مخرجٌ فعليّ 09-28 |
| الردُّ السريع | غيرُ مذكور | احذف أرقامَ high من السطر المعبّأ | نسخُه يعدّ ذكراً صريحاً للرقم فيعتمد العالي | `parse_reply`: «اعتمد: 1 2 3» يعتمد 3 العالي (مجرَّب) — استنتاجٌ من غرض `approvals_policy.md` §2 |
| الظهورُ على 8500 | غيرُ مذكور | status ← integrate plan ← pin/release بالدور، وأسبابُ التخطّي الستّة | «لا بندَ لا يُرى على 8500» | `feedback_approval_only_after_8500_preview`؛ `docs/deployment/local_preview.md` §3.1 |
| BLUF والروابط | غيرُ مذكور | رابطٌ ودورٌ وما يُنظر إليه، وما لا تعكسه المعاينة، ومثالٌ كامل | مخرجُ `render` هيكلٌ بلا أثرٍ ولا رابط | `templates/review_window_template.md`؛ `operating_model.md` §3؛ `tabs.json` → 0501 boundaries |
| الوقت | «15:30 / 20:30» | من `date -u` + 3؛ لا `TZ=` في Git Bash | أخطأ التقديرُ مرّتين | `operating_model.md` §6؛ `feedback_doha_time_on_windows` |
| الفخاخ | لا شيء | سبعةُ فخاخٍ خطأ:/الصواب: | من وقائع | السجلّ الزمنيّ 09-28 16:07 و16:16؛ `handover.md` (تثبيتٌ عالق ~18:13)؛ تجربةُ `integrate` من شجرةٍ قديمة |
| ما ليس لها | «حدود» في سطرٍ واحد | قسمٌ صريح + «ليست لـ» في الوصف | منعُ التفعيل الخاطئ | الكرّاسة §2 |
| حالاتُ الاختبار | لا شيء | `references/99-test-cases.md` (9 تُفعَّل، 7 لا، 7 حدّيّة، معاييرُ المخرج) | إلزاميّ | الكرّاسة §2 |
| الإحالة | لا شيء | خطواتُ الفلو إلى `schoolos-flow` | منعُ التكرار | الكرّاسة §3 |

## ما لم يُنقل من الأصل
- «يحفظ خريطةَ الأرقام في `ledger/windows/`» بقي، مع تنبيه أنّ `render` يكتب ملفّاً (ليس قرائيّاً بحتاً).
- «بلّغ كلَّ جلسة» نُقل إلى maestro-approvals (مهارةٌ واحدةٌ للإبلاغ).
