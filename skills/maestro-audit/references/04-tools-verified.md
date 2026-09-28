# أدواتُ المايسترو كما تعمل فعلاً (تحقّقٌ 2026-09-28 ~20:55 الدوحة)

متى تقرأ هذا الملف: قبل أن تشغّل أداةً من `C:/Users/mesue/delivery_manager_work/tools/` لا تعرف أهي قرائيّة، أو حين يختلف مخرجُها عمّا تتوقّع، أو حين تصون أداةً (D-37م).

كلُّ سطرٍ أدناه من تشغيلٍ فعليّ بـ`--help` ثمّ بوضعٍ قرائيّ، ومن قراءة الشيفرة. الأوامرُ من جذر المجلّد. الأدواتُ تضبط مخرجَها على UTF-8 بنفسها (طرفيّةُ ويندوز cp1256 كانت تُسقط الطباعة)؛ وإن مرّرتَ مخرجَها إلى `python -c` آخر فاضبط `PYTHONIOENCODING=utf-8`.

## الجدول
| الأداة | `--help` | يكتب؟ | الاستعمالُ القرائيّ | ما أخرجته 09-28 |
|---|---|---|---|---|
| validate_registry.py | يعمل | لا | `--sessions <json>` (قائمةُ عناوين) `[--project schoolos]` | «السجلُّ متّسق»، رمز 0؛ ورمز 1 مع سطرٍ لكلّ مشكلة |
| watch_once.py | يعمل | لا | `[--json] [--no-live]` | memory red/critical، oldest_pr_age 73.1 س (high)، ثلاثُ orphan_tree (warn)؛ ≈50 ث حيّاً |
| flow_metrics.py | يعمل (بلا وصف) | لا | `--days N [--json]` | 7 أيّام: 247 مدموجاً، متوسّط 3.58 س، وسيط 1.33 |
| session_load_v2.py | يعمل | `git fetch` فقط | `--no-fetch [--json]` | جدولُ الجلسات، unowned_prs [719, 696, 631]، ستُّ أشجارٍ بلا اسم |
| ledger.py | يعمل | `add` و`move` يُلحقان بـ`ledger/events.jsonl` | `list [--state S]`، `show ID` | 17 بطاقة، 0 أحداثِ اعتماد |
| archive_check.py | يعمل | لا | `<مجلّد الشجرة> --title "<العنوان>" [--running] [--shared N]` | JSON: eligible وblockers وreason؛ يمنع النواةَ (D-43م) |
| branch_status.py | لا مخرج | — | مكتبةٌ تستوردها watch_once وarchive_check؛ لا `main` | — |
| owner_load_study.py | **ينهار** (ValueError: `--help` ليس عدداً) | لا | `python tools/owner_load_study.py 7` (وسيطٌ موضعيّ = الأيّام) | 3 أيّام: 78 طلباً، ≈33 د/يوم بالحزم |
| render_charters.py | **خطأ** (`--help` يُقرأ اسمَ مشروع فيفشل قبل الكتابة) | **نعم**: يعيد كتابة `docs/tab_charters.md` | لا وضعَ قرائيّاً؛ شغّله عمداً بعد تعديل tabs.json | — |
| render_auto_sections.py | **يتجاهله ويشغّل كلَّ شيء** | لا ملفّ (stdout)، لكن `git fetch` ما لم يُعطَ `--no-fetch` | `--no-fetch` | القسمان [آلي] 2 و3 للّوحة |
| review_window.py | يعمل | **نعم**: `render` يحفظ في `ledger/windows/`، و`apply` يُلحق أحداثَ اعتماد | ليس لـ0102 | رقمُ الفلو الافتراضيّ في `render` v2.1 (قديم) |
| routing.py / risk_tier.py / evidence_pack.py | — | لا (قراءةٌ وgh) | للمايسترو و0501 | خارج التقييم الدوريّ |
| test_package.py + test_session_load_v2.py | — | لا | `cd tools && python -m unittest test_package test_session_load_v2` | Ran 82 tests … OK |

## ملاحظاتٌ تستحقّ أن تُعرف
- **validate_registry لا يفحص** مفاتيحَ `session_policy.charters` مقابل الأعضاء، ولا أنّ الجلسةَ في مجموعة رقمها في الشريط (يرى العناوينَ فقط). السكربتُ `daily_audit.py` يسدّ الاثنين.
- **watch_once `oldest_pr_age`** يعدّ كلَّ طلبٍ غيرِ مسوّدة، ومنها المؤجَّلُ عمداً؛ فالإنذارُ «high» دائمٌ ما بقي #631/#719 — البطاقة W-20260928-013.
- **watch_once `orphan_tree`** يحكم بحالة طلب الفرع (branch_status) لا بعدّ الإيداعات، لأنّ الدمجَ بالسحق يُبقي إيداعاتِ الفرع «غيرَ مدموجة» في `git cherry` (قياس 09-28: vision-footer ← #714). فلا تعِد حسابها بـ`rev-list`.
- **late_items** يعدّ البطاقةَ متأخّرةً إن حان `start` وحالتُها captured أو verified أو routed فقط؛ `in_progress` لا تُعدّ متأخّرةً مهما طالت (افحصها يدويّاً في الأسبوعيّ).
- **ledger.check_text** يرفض نصّاً فيه 9 أرقامٍ متتالية أو بريد، وأيَّ حقلٍ فوق 240 حرفاً: بطاقاتُ التحسين التي تكتبها تمرّ به.
- **مصدرُ الحقيقة للعتبات** `projects/schoolos/thresholds.json` (ذاكرةٌ 2.0/1.0/0.5 غيغا، طلبٌ 8/24 س، WIP 7–10، فشلُ main 2، نسخٌ 36 س)؛ لا تنقلها من الذاكرة.
- **الوقت:** الأدواتُ تكتب `generated_doha` بـUTC+3 صراحةً؛ و`TZ=Asia/Qatar date` في Git Bash قد يعطي UTC صامتاً — احسب من `date -u`. المصدر: feedback_doha_time_on_windows.

## أنماطٌ مضادّة
- «أجرّب `--help`» على render_charters.py أو render_auto_sections.py أو owner_load_study.py.
- تشغيلُ `review_window.py render` لقراءة الطابور (يكتب ملفّاً)، أو `ledger.py move` لتصحيح حالةٍ رأيتَها خطأً — الحالةُ لصاحب البطاقة؛ أنت تبلّغ.
- إصلاحُ أداةٍ دون اختبارٍ يغطّي الإصلاح، أو دون تشغيل الحزمة كلّها بعده.
- الاعتمادُ على رقم «Ran N tests» من قرارٍ قديم (77 ثمّ 79 ثمّ 81 ثمّ 82): العددُ يُقرأ من التشغيل.
