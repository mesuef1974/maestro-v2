# قواعدُ الخطورة: ما تفعله risk_tier.py وأين تُخطئ

متى تقرأ هذا الملف: حين تصنّف بنداً، أو يبدو تصنيفُ الأداة أخفَّ من الواقع، أو يسأل المالكُ «ليش هذا عالي؟».

المصادر: `C:/Users/mesue/delivery_manager_work/tools/risk_tier.py` (مقروءٌ 09-28)، و`docs/approvals_policy.md` §3، وتجاربُ تشغيلٍ على مساراتٍ من `origin/main` يومَ 09-28.

## 1) الفئةُ لكلّ ملفّ (أوّلُ قاعدةٍ تنطبق)
| الترتيب | الشرط على المسار | الفئة | الخطورة |
|---|---|---|---|
| 1 | يبدأ بـ`roadmap/migrations/` | roadmap_data | light |
| 2 | `…/migrations/<ملفّ>.py` | migration | high |
| 3 | اسمُ الملفّ يبدأ بـ permissions أو rls أو crypto أو consent أو erasure، أو فيه `/auth/` | security | high |
| 4 | يبدأ بـ`templates/` أو `static/`، أو ينتهي بـ.html/.css/.js | visible_ui | medium |
| 5 | يبدأ بـ`tests/` | tests_only | light |
| 6 | `.github/` أو `scripts/` أو `.claude/` أو docker أو requirements أو Makefile | infra | low |
| 7 | ينتهي بـ.md أو يبدأ بـ`docs/` أو `AAdocs/` | docs_only | light |
| 8 | ينتهي بـ.py | backend | medium |
| — | غيرُ ذلك | infra | low |
خطورةُ العمل = خطورةُ أعلى فئةٍ فيه بالترتيب: migration ← security ← visible_ui ← backend ← infra ← roadmap_data ← tests_only ← docs_only. والمجالُ = أوّلُ جزءٍ من مسار أوّلِ ملفٍّ في الفئة العليا.

## 2) العلامات
| العلامة | متى | أثرُها |
|---|---|---|
| global_css | ملفٌّ تحت `static/css/custom/` | ترفع إلى medium على الأقلّ؛ «كلُّ الصفحات نهاراً وليلاً وبعرض 375» |
| base_template | `templates/base.html` أو `templates/login.html` حرفيّاً | ترفع إلى medium — لكنّ المسارين غيرُ موجودين (القسم 3) |
| hot_file | `docs/governance/regression_guards.md` أو `tests/mypy_ratchet_baseline.json` | لا ترفع؛ «رتّب الدمجَ لتفادي التعارض» |
| agent_rules | `CLAUDE.md` أو تحت `.claude/` | لا ترفع (CLAUDE.md وحده = light) |

## 3) ما تُخطئه الأداة — جُرِّب 09-28
| المسار (على main) | قالت الأداة | الصحيح بالحكم | لماذا |
|---|---|---|---|
| `core/middleware_rls.py` | backend · medium | high | RLS يعزل بياناتِ المدارس؛ الاسمُ لا يبدأ بـrls |
| `api/views_erasure.py` | backend · medium | high | حقُّ المحو (PDPPL) |
| `shschool/settings/*.py` | backend · medium | high غالباً | إعداداتُ أمنٍ وجلسات وCSP |
| `templates/base/base.html` | visible_ui · medium بلا علامة | medium + «كلُّ الصفحات» | القالبُ الأساسيّ الفعليّ هنا لا `templates/base.html` |
| `templates/auth/login.html` | security · high | high (صحيح) | يطابق `/auth/` — كلُّ قالبٍ تحت auth يُعدّ أمناً |
| `CLAUDE.md` | docs_only · light + agent_rules | بندٌ مستقلّ | يغيّر سلوكَ كلّ الجلسات |
| `roadmap/migrations/…` | light | light | مزامنةُ الخارطة (approvals_policy §3)؛ لكنّها لـ0701 وحدها |
الرفعُ بـ`tag_card.py --raise-to high --reason "…"`. قائمةُ هذه الفجوات بطاقةٌ للمايسترو ليصلح القواعد (D-37م)، لا تعديلٌ من الجلسة.

## 4) الخطورةُ ← طريقةُ العرض (approvals_policy §3)
| الدرجة | العرض |
|---|---|
| light | حزمةٌ خفيفةٌ واحدة، اعتمادٌ بكلمة، وتمرّ بالبوّابة كغيرها |
| low | ضمن الحزم بحسب المجال |
| medium | حزمةٌ لكلّ (فئة × مجال) مع حزمة الأدلّة |
| high | حزمةٌ مستقلّة، تُعتمد بذكر رقمها صراحةً، ولا يشملها «اعتمد الكلّ» |

## 5) أوامرُ جاهزة
```
git worktree list                                              # المجلّد ← الفرع
git diff --name-only origin/main...<الفرع>                     # ما يحمله الفرع (ثلاث نقاط)
python C:/Users/mesue/delivery_manager_work/tools/risk_tier.py <مسار> <مسار> …
```
`risk_tier.py` بلا مسارات يُرجع infra · low و`area: "-"` — ليس «آمناً»، بل لا شيءَ صُنِّف.

## أنماطٌ مضادّة
- خطأ: `git diff origin/main..<الفرع>` (نقطتان): يُدخل ما تغيّر في main بعد الافتراق فيضخّم الخطورة. الصواب: ثلاثُ نقاط.
- خطأ: خفضُ خطورة الأداة «لأنّ التغيير صغير». الصواب: الأداةُ حدٌّ أدنى؛ الحجمُ لا يُخفّف هجرة.
- خطأ: الاكتفاءُ بـ`files` في البطاقة (ملفّاتٌ مظنونةٌ قبل العمل). الصواب: الفرقُ الفعليّ للفرع.
