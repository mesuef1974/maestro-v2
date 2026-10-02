# جردُ المهارات لقرار مهارةِ كلّ مرحلةٍ وجلسة — 2026-09-28
> أعدّته «0102 · تقييم المايسترو» بطلب المالك: «اعرض عليّ كلّ شيءٍ من المهارات حتى نقرّر مهارةَ كلّ بندٍ من الفلو». **لم يُعدَّل شيءٌ في المواثيق**؛ القرارُ للمالك. الأوصافُ منقولةٌ من ملفّات المهارات نفسِها والأعدادُ محقَّقة بالأمر.

## أ) مهاراتُ منصّة المدرسة (7) — في `D:/shschool_mvp/.claude/skills/` ومتتبَّعةٌ في غيت، فتصل كلَّ شجرة
| المهارة | ما تفعله | مرحلتُها الطبيعيّة |
|---|---|---|
| schoolos-platform | خريطةُ المشروع: الملفّاتُ والنماذجُ والخدماتُ، ونظامُ التقييم القطريّ، والأدوارُ (20×5)، وقواعدُ العمل والفخاخ | 03 · 04 · 08 |
| schoolos-migration-guard | فحصُ أمان أيّ هجرةٍ على بياناتٍ حقيقيّة (أقفالٌ، فقدُ بيانات، توافقٌ رجعيّ، NOT NULL) | 04 · 06 · 08 |
| pdppl-pii-audit | تدقيقُ PDPPL في المنصّة: حقولُ PII، وتسرّبُها في القوالب والسجلّات، والموافقةُ والمحو والخرق | 02(0201) · 04 · 07(0702) |
| nplus1-hunter | صيدُ استعلامات N+1 في Python وقوالب Django وإثباتُ الإصلاح باختبار عدّ | 04 · 07(0702) |
| web-design-mastery | معاييرُ التصميم والـCSS: الرموزُ والطبقاتُ والوضعُ الليليّ وRTL وHTMX وميزانيّاتُ الأداء | 04 · 05 · 07(0702) |
| schoolos-report-ar | تقاريرُ PDF وExcel الرسميّةُ العربيّة (ترويسةٌ وترقيمٌ وتذييلٌ وخطوط) | 04 · 05 |
| drf-endpoint-scaffold | مولّدُ نقاط DRF بالطبقات ورقابةِ الصلاحيّات | 04 · 08 |

## ب) مهاراتُ المايسترو (11) — في `delivery_manager_work/skills/` (مركَّبةٌ في شجرة المايسترو فقط)
| المهارة | ما تفعله |
|---|---|
| maestro-intake | مدخلٌ ← بطاقةٌ بأربعة أسطر وإلغاءُ تكرار وتصنيفُ استعجال |
| maestro-load-check | حِملُ الجلسات واختيارُ المقعد المختصّ بجدول التوجيه |
| maestro-spawn | توجيهٌ أم إعادةُ فتحٍ أم استحداث، وبطاقةُ الاستحداث |
| maestro-tabs | إدارةُ المراحل والمجموعات ونقلُ الجلسات وتوليدُ المواثيق |
| maestro-review-window | نافذةُ مراجعةٍ للمالك بحزمٍ مرتَّبةٍ وBLUF والتقاطُ قراره |
| maestro-approvals | تسجيلُ قرار المالك أثراً قابلاً للتدقيق وإبلاغُه |
| maestro-evidence | حزمةُ أدلّةٍ للطلب (الخطورةُ والفحوصُ وسطرُ الاعتماد) بلا اختلاق أرقام |
| maestro-incident | قيادةُ الحادث S1..S3 وإيقاعُ الإبلاغ والمراجعةُ بلا لوم |
| maestro-archive-check | أهليّةُ الأرشفة وسطرُ السبب |
| maestro-handover | مذكّرةُ التسليم وسجلُّ القرارات وسجلُّ الفلو |
| maestro-project-switch | تبديلُ المشروع وبناءُ ملفّ مشروع |

## ج) مهاراتٌ عامّةٌ تصلح للمدرسة (من مستودع المهارات الشخصيّ وclaude.ai)
| المهارة | الفائدةُ للمدرسة | ملاحظة |
|---|---|---|
| arabic-rtl-review | مراجعةُ النصوص العربيّة والاتّجاه والتنسيق | مناسبةٌ تماماً |
| pdppl-compliance | تدقيقُ امتثال PDPPL وخرائطُ البيانات وطلباتُ أصحاب البيانات | مناسبة |
| pdppl-qatar-advisor | تحليلُ سيناريو قانونيّ بصيغة ثابتة (DPIA، الخرق 72 ساعة، النقل عبر الحدود) | مناسبة (استشاريّة لا ملزِمة) |
| security-advisor | مراجعةُ أمنٍ بعقليّة الاختراق وتصنيفُ الخطورة | مناسبةٌ للمراجعة الأمنيّة |
| chrome-browser · built-in-browser | قراءةُ الصندوق على الإنتاج، ومعاينةُ 8500 | مهارتا claude.ai لأدوات المتصفّح |
| skill-creator | إنشاءُ المهارات وقياسُ فاعليّتها بالتجارب | يخدم 0102 في اختبار المهارات |
| schoolos-debugger (وكيل) | تتبّعُ أعطال SchoolOS | وكيلٌ لا مهارة |
| /code-review · /adr · /django-app · /explain-code (أوامر) | مراجعةٌ وقراراتٌ معماريّة وتوليدُ تطبيقات | للمرحلة 04 |

## د) لا تناسب منصّةَ المدرسة (وقد وضعتُ بعضَها في مواثيقي خطأً)
- **azkia-devops:** مكتوبٌ لنشر LiveSky على Vercel وSupabase؛ نشرُ المدرسة على Railway. **أزلته من اقتراحي للمرحلتين 06 و08.**
- **governance-advisor:** يطبّق «دستورَ أذكياء» (R-rules وCEF)، لا حوكمةَ الجلسات. **أزلته من اقتراحي للمرحلتين 01 و03.**
- **azkia-qa / qa-gate-advisor / azkia-security / azkia-engineering:** أقسامُ شركة أذكياء ومعاييرُها التسعة، لا فلو المدرسة.
- **مهاراتُ الرياضيات البحثيّة** (analytic-number-theory، rigorous-number-theory، conjecture-guard، exact-count، lean-formal-bridge، math-prof، polymath، solve-math، lmfdb-oeis، latex، bibliographic-verification، certificate-ledger، research-release-governance، spectral-operator-no-go): بحثٌ لا صلةَ له بالمنصّة. **و**qubatossamah-* (5)، وsma-design، وazkia-marketing، وAzkia-ux، وai-architecture-advisor: مشاريعُ أخرى.
- **مهاراتُ إضافاتٍ عامّة** (`engineering:*` و`product-management:*` و`data:*` و`design:*`): عامّةٌ لا مدرسيّة، ولم أتحقّق من تثبيتها في جلسات المراحل. **اقتراحي: تُحذف من كلّ الأمثلة.**

## هـ) معرفةٌ موجودةٌ بلا مهارة (ثغراتٌ) — كلُّها مكتوبةٌ في الذاكرة والوثائق، لم تُحوَّل مهارةً بعد
| # | المهارةُ المقترحة | مصدرُ معرفتها الموجود | تخدم |
|---|---|---|---|
| G1 | schoolos-flow | الفلو v2.8 موزَّعٌ بين CLAUDE.md وflow_changelog وoperating_model: الخطواتُ، وسطرُ الاعتماد، والنوافذ، والتسمية | **كلَّ** الجلسات |
| G2 | schoolos-git-safety | قواعدُ غيت المتوازي في CLAUDE.md (لا add -A ولا stash، ولا عبورَ أشجار)، وrep19_git_guard، وprune | 04 · 0501 · 0601 · 08 |
| G3 | schoolos-feedback-intake | بروتوكولُ 09-25 والقرارات D-52م..D-54م وgate.js واختبارُه وقالبُ التقرير | 0201 |
| G4 | schoolos-watch | watch_once وincident_runbook ومصادرُ الإنذار (health وCI والنسخ والذاكرة) وتصنيفُ S1..S3 | 0203 |
| G5 | schoolos-source-of-truth | ميثاقُ المستشار: نسخةُ md من ملفّات الوزارة، والـPDF حَكَم، وصيغةُ الجواب (مصدرٌ ونوعٌ وثقة) | 0301 |
| G6 | schoolos-preview-8500 | preview.sh (pin/release/status)، وخطرُ إعادة حقن 8500، وفرقُ خطّ PDF، وقياسُ صفحةٍ محميّة بلقطة | 0501 |
| G7 | schoolos-deploy | وصفةُ النشر (طابورٌ ← معاينةٌ ← redeploy ← verify_deploy)، وRailway، ونافذةُ النشر، و«لا تثق بادّعاء طلبٍ فافحص diff» | 0601 |
| G8 | schoolos-roadmap-sync | طابورُ مزامنة الخارطة، وملكيّةُ الهجرات، وقواعدُ الإغلاق برقم الطلب، وMAE-00/14 | 0701 |
| G9 | schoolos-quality-guards | regression_guards.md (133 سطراً)، وسقّاطاتُ CSS/JS وWeb Vitals، ووصفاتُ قياس المسارات التسعة | 0702 |
| G10 | schoolos-automation | أنماطُ أتمتةٍ بلا Claude: أمرُ إدارة Django، وRailway beat/cron، وGitHub Actions، وجدولةُ ويندوز؛ وسجلُّ التشغيل | 0801 |
| G11 | maestro-audit | ميثاقُ 0102: قائمةُ التقييم اليوميّ والأسبوعيّ وقالبُ التقرير | 0102 |
| G12 | schoolos-governance | قواعدُ الجلسات: التسمية والترقيم والأرشفة لا الحذف والعربيّةُ وحدها وسقفُ الجلسات | 0103 |

**قيود التنفيذ إن اعتُمدت:** موضعُ المهارات المدرسيّة: المستودعُ العامّ للمنصّة (فتصل كلَّ شجرة، ولا يجوز فيها أيُّ سرٍّ أو بياناتٍ شخصيّة)، أم مستودعُ المايسترو الخاصّ (يُركَّب في شجرة المايسترو فقط)، أم مستودعُ المهارات الشخصيّ (حدُّ CI: SKILL.md ≤ 120 سطراً، والمراجعُ ≤ 200، ووصفٌ بلغتين، و`references/99-test-cases.md`).

## و) شبكةُ القرار — المرشَّحُ لكلّ جلسة (✓ موجود · ➕ ثغرة)
| الجلسة | مهاراتٌ موجودة | ثغراتٌ مقترحة |
|---|---|---|
| 0101 المايسترو | maestro-intake · load-check · spawn · tabs · review-window · approvals · incident · handover · archive-check · project-switch · evidence | G1 |
| 0102 تقييم المايسترو | maestro-* (للفحص) · skill-creator | G11 · G1 |
| 0103 الحوكمة | maestro-tabs · maestro-archive-check | G12 · G1 · G2 |
| 0201 أمين البلاغات | pdppl-pii-audit · pdppl-compliance · pdppl-qatar-advisor · chrome-browser | G3 · G1 |
| 0202 طلبات المالك | maestro-intake · maestro-approvals | G1 |
| 0203 الرصد والإنذارات | maestro-incident · maestro-load-check · وكيل schoolos-debugger | G4 · G1 |
| 0204 البوابة الموحّدة | maestro-intake · maestro-load-check (التوجيه) | G1 |
| 0301 المستشار | schoolos-platform · arabic-rtl-review · pdppl-compliance · maestro-load-check | G5 · G1 |
| 0501 النشر على 8500 | maestro-review-window · maestro-approvals · maestro-evidence · built-in-browser · web-design-mastery · schoolos-report-ar | G6 · G2 · G1 |
| 0601 النشر على الإنتاج | schoolos-migration-guard · maestro-incident · security-advisor | G7 · G2 · G1 |
| 0701 تحديث الخارطة | schoolos-platform | G8 · G1 |
| 0702 مراقبات الجودة | nplus1-hunter · pdppl-pii-audit · web-design-mastery · security-advisor | G9 · G1 |
| 0801 أتمتة الجدولة | schoolos-platform · schoolos-migration-guard · drf-endpoint-scaffold | G10 · G2 · G1 |
| المرحلة 04 (لم تُراجَع) | كلُّ مهارات «أ» بحسب الاختصاص، وأوامرُ /code-review و/django-app | G2 · G1 |

## ز) من يستخدم كلَّ مهارةٍ في الفلو
| المهارة | من يستخدمها |
|---|---|
| schoolos-platform | 0301 (التصنيف والمرجع) · 04 · 0701 · 0801 |
| schoolos-migration-guard | 04 (مهامّ الهجرات) · 0601 (قبل النشر) · 0801 |
| pdppl-pii-audit | 0201 · 04 (مهامّ البيانات) · 0702 |
| nplus1-hunter | 04 · 0702 |
| web-design-mastery | 04 (الواجهة) · 0501 (الفحص البصريّ) · 0702 (الميزانيّات) |
| schoolos-report-ar | 04 (التصدير) · 0501 (معاينة PDF) |
| drf-endpoint-scaffold | 04 · 0801 |
| maestro-intake | 0101 · 0202 · 0204 |
| maestro-load-check | 0101 · 0203 · 0204 · 0301 |
| maestro-spawn | 0101 |
| maestro-tabs | 0101 · 0103 |
| maestro-review-window | 0101 · 0501 |
| maestro-approvals | 0101 · 0202 · 0501 |
| maestro-evidence | 0501 · 0101 |
| maestro-incident | 0101 · 0203 · 0601 |
| maestro-archive-check | 0101 · 0103 |
| maestro-handover | 0101 · 0102 |
| maestro-project-switch | 0101 (نادراً) |
| arabic-rtl-review | 0301 · 04 · 0501 |
| pdppl-compliance | 0201 · 0301 |
| pdppl-qatar-advisor | 0201 · 0301 |
| security-advisor | 0601 · 0702 |
| chrome-browser | 0201 |
| built-in-browser | 0501 |
| skill-creator | 0102 |
| وكيل schoolos-debugger | 0203 · 04 |
| G1 schoolos-flow | كلُّ الجلسات |
| G2 schoolos-git-safety | 04 · 0501 · 0601 · 0801 |
| G3 schoolos-feedback-intake | 0201 |
| G4 schoolos-watch | 0203 |
| G5 schoolos-source-of-truth | 0301 |
| G6 schoolos-preview-8500 | 0501 |
| G7 schoolos-deploy | 0601 |
| G8 schoolos-roadmap-sync | 0701 |
| G9 schoolos-quality-guards | 0702 |
| G10 schoolos-automation | 0801 |
| G11 maestro-audit | 0102 (توصيةُ الدمج: في ميثاقها) |
| G12 schoolos-governance | 0103 (توصيةُ الدمج: في G1) |

## ح) المهاراتُ المقترَحُ استبعادُها ولماذا
| المهارة أو المجموعة | سببُ الاستبعاد | بديلُها إن لزم |
|---|---|---|
| azkia-devops | مكتوبةٌ لنشر LiveSky على Vercel وSupabase؛ نشرُ المدرسة على Railway (وقد وضعتُها خطأً في 06 و08) | G7 schoolos-deploy |
| governance-advisor | تطبّق «دستورَ أذكياء» (R-rules وCEF) لا حوكمةَ جلسات المدرسة (وضعتُها خطأً في 01 و03) | G1 (وG12 مدموجةٌ فيه) |
| azkia (المنسّق) | تنسيقٌ بين أقسام شركة أذكياء ومجلسها الاستشاريّ | maestro-* |
| azkia-engineering | معاييرُ كودٍ عامّةٌ للشركة؛ schoolos-platform وتعليماتُ المستودع أدقّ | schoolos-platform |
| azkia-qa · qa-gate-advisor | تسعُ بوّاباتٍ وحكمُ PASS/FAIL آليّ؛ فلو المدرسة اعتمادُ المالك على 8500 بسطر اعتماد | maestro-evidence · 0501 |
| azkia-security | قسمُ أمن الشركة؛ يكفي security-advisor وpdppl-pii-audit وهما أخصّ بالمنصّة | security-advisor |
| Azkia-ux | تجربةُ مستخدمٍ عامّةٌ؛ web-design-mastery خاصٌّ بالمنصّة (رموزٌ قطريّة وطبقاتٌ وRTL) | web-design-mastery |
| ai-architecture-advisor | معماريةُ أنظمة ذكاءٍ اصطناعيّ؛ المنصّةُ بلا ميزاتٍ منه | — |
| azkia-marketing · sma-design | تسويقٌ وهويّاتُ علامات | — |
| مهاراتُ الرياضيّات البحثيّة (14): analytic-number-theory، rigorous-number-theory، conjecture-guard، exact-count-and-zero-tables، lean-formal-bridge، lmfdb-oeis-lookup، math-prof، polymath-advanced-math، solve-math-rigorously، latex، bibliographic-verification، certificate-ledger، research-release-governance، spectral-operator-no-go | بحثٌ رياضيٌّ لا صلةَ له بمنصّة إدارة المدرسة | — |
| qubatossamah-* (5) | مشروعُ «قبّة السماء» | — |
| مهاراتُ claude.ai العامّة: docs، docx، pptx، xlsx، pdf، deep-research، doc-coauthoring، web-artifacts-builder، theme-factory، canvas-design، brand-guidelines، slack-gif-creator، algorithmic-art، internal-comms، mcp-builder، import-memory، morning، computer-use | عامّةٌ للمنتَجات والبحث والتصميم، لا مرحلةَ من الفلو تحتاجها؛ تُستدعى عرَضاً بطلب المالك (مثلاً ملفّ PDF لتقرير) | — |
| مهاراتُ الإضافات العامّة: engineering:* · product-management:* · data:* · design:* | عامّةٌ تكرّر ما في maestro-* ومهاراتِ المنصّة، ولم يثبت تثبيتُها في جلسات المراحل | maestro-* |
| schedule | ينشئ مهامَّ مجدولةً في Claude Code وهذا ما أمر المالكُ بإنهائه (D-50م) | G10 |
| anthropic-skills:consolidate-memory · simplify | لا مرحلةَ تحتاجهما في الفلو | — |
| وكلاءُ أذكياء (azkia-orchestrator وazkia-qa-gate وazkia-security-auditor وcode-reviewer-azkia وazkia-architect وغيرها) | وكلاءُ شركة أذكياء ومعاييرُها | schoolos-debugger |
| أوامر /lesson · /vue-comp · /azkia-status · /morning · /save-memory | خططُ دروسٍ وVue وحالةُ الشركة؛ المنصّةُ Django وHTMX لا Vue | — |
| أمر /django-app | يولّد تطبيقاً كاملاً بمعماريّةٍ جديدة؛ المنصّةُ قائمةٌ ولا نبدأ تطبيقاً إلا بقرار | drf-endpoint-scaffold |
