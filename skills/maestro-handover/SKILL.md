---
name: maestro-handover
description: |
  Use for keeping the maestro's own memory files true in C:/Users/mesue/delivery_manager_work: appending owner decisions to decisions.md (next D-NNم, append-only), a flow_changelog.md row with a new flow version before any rule is announced, regenerating board_state.md (auto sections from render_auto_sections.py, ≤150 lines), rotating history into log_<date>.md, RAID rows, rewriting handover.md, then a privacy scan and commit/push of the private maestro-v2 repo. Trigger on: handover, update board, board_state, log rotation, decision log, flow version bump, "before context compaction", end of a review window, after an incident, «حدّث اللوحة»، «سجّل القرار»، «دوّر السجلّ».
  استخدمها في آخر كلّ نافذةِ مراجعة، وبعد كلّ حادث، وفور صدور قرارٍ من المالك، وقبل ضغطِ السياق أو إنهاءِ الجلسة.
  ليست لـ: مذكّرةِ تسليم جلسةٍ قبل أرشفتها (maestro-archive-check)، ولا ذاكرةِ المشروع في ~/.claude، ولا الخارطةِ /roadmap/ (0701)، ولا owner_requests.md (0202 وحدها)، ولا بطاقاتِ العمل (maestro-intake).
allowed-tools: Read, Write, Edit, Grep, Bash(python C:/Users/mesue/delivery_manager_work/tools/render_auto_sections.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/flow_metrics.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/session_load_v2.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/watch_once.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/ledger.py list:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/ledger.py show:*), Bash(git -C C:/Users/mesue/delivery_manager_work status:*), Bash(git -C C:/Users/mesue/delivery_manager_work pull --ff-only:*), Bash(git -C C:/Users/mesue/delivery_manager_work add:*), Bash(git -C C:/Users/mesue/delivery_manager_work commit:*), Bash(git -C C:/Users/mesue/delivery_manager_work push origin main:*), Bash(git -C C:/Users/mesue/delivery_manager_work log:*), Bash(bash scripts/preview.sh status)
---

# التسليمُ وتدويرُ ذاكرة المايسترو

الغرض: أن يستأنف مايسترو بعد ضغط السياق أو إعادة التشغيل (أو بديلٌ عنه) من الملفّات لا من الذاكرة، فيجد كلَّ قرارٍ مسجَّلاً ومرقَّماً، واللوحةَ صادقةً الآن، والتاريخَ في السجلّ لا في اللوحة. المايسترو نقطةُ فشلٍ واحدة، ومذكّرتُه هي خطّةُ خلافته (`operating_model.md` §13).

## متى
- **فورَ** قرارٍ من المالك: الخطوتان 2–3 (لا تنتظر آخر النافذة؛ «لا إبلاغَ قبل قرارٍ مسجَّل وسطرِ فلو ورقم»).
- آخرَ كلّ نافذةِ مراجعة، وبعد كلّ حادث، وقبل ضغط السياق: الإجراءُ كاملاً.
- لا تُستعمل لغير ملفّات المايسترو (انظر الوصف).

## الإجراء
1. **ابدأ مزامَناً وبالوقت الصحيح.** `git -C C:/Users/mesue/delivery_manager_work pull --ff-only` (0102 تودع في المستودع نفسِه؛ `handover.md` §0)، ثمّ `git -C … status --short`: ملفٌّ لا تعرفه ليس لك. الوقتُ من الأداة: `generated_doha` في مخرجاتها، أو
   `python -c "from datetime import datetime,timedelta,timezone as tz;print(datetime.now(tz(timedelta(hours=3))).strftime('%Y-%m-%d %H:%M'))"` (لا `TZ=Asia/Qatar date` في Git Bash: يطبع UTC صامتاً — الذاكرة `feedback_doha_time_on_windows.md`).
2. **القرار ← `decisions.md`.** سطرٌ في الآخر بالرقم التالي (`grep -oE "^- D-[0-9]+م" decisions.md | tail -1` ثمّ +1): `- D-NNم | <التاريخ الوقت> | <نصُّ المالك بين «» ثمّ ما يعنيه> | <الأثر: ما تغيّر وأين> | <المرجع: المحادثة/AskUserQuestion>`. لا تعديلَ لسطرٍ قديم: التصحيحُ سطرٌ جديدٌ يشير إليه.
3. **إن غيّر القرارُ قاعدةً تعمل بها الجلسات ← `flow_changelog.md` قبل أيّ إبلاغ.** صفٌّ بستّة أعمدة ورقمُ إصدارٍ تالٍ (v2.9 ← v2.10)؛ والاستثناءُ الانتقاليّ يحمل تاريخَ أو شرطَ انتهاء؛ والإبلاغُ يبدأ بـ«الفلو vX.Y» ويُرسل مرّةً بنصٍّ واحد. تفصيلُ الفلو نفسِه في `schoolos-flow`؛ وتعديلُ نصّ القواعد في CLAUDE.md تحرسه 0103 ويمرّ بالفلو.
4. **قِس ثمّ اكتب اللوحة.** `python C:/Users/mesue/delivery_manager_work/tools/render_auto_sections.py --no-fetch` يطبع §2 و§3 جاهزتين (لا يكتب ملفّاً)؛ استبدل بهما القسمين في `board_state.md`. ثمّ §1 و§4–§6 يدويّاً بعد قياسٍ حيّ (`watch_once.py --no-live` للذاكرة على الأقلّ). الملفُّ كلُّه ≤150 سطراً (`wc -l`)؛ والتفصيلُ في `references/01-board-log-commit.md`.
5. **التاريخ ← السجلّ.** كلُّ حدثٍ مضى سطرٌ في ملفّ السجلّ الجاري `log_<التاريخ>.md` بصيغة `- YYYY-MM-DD HH:MM (الدوحة) — <ما جرى>`؛ اللوحةُ لا تحمل تاريخاً. ويومٌ جديدٌ ملفٌّ جديد.
6. **المخاطر ← `raid.md`.** صفٌّ جديدٌ برقمه؛ وما حُسم يُنقل إلى «مُغلَق» بتاريخ الحسم ولا يُحذف.
7. **`handover.md`** من `templates/handover_template.md`: الترويسة (آخرُ تحديث، الوضع، **إصدارُ الفلو = آخرُ صفٍّ في `flow_changelog.md`**)، ثمّ §0 ما تغيّر اليوم، §1 ما ينتظر المالك (≤8، مطابقٌ لـ§5 في اللوحة)، §2 التزاماتُ الجلسات بمواعيدها، §3 المراقباتُ والأوامر، §4 الحوادث، §5 ما لا يجوز.
8. **افحص الخصوصيّة ثمّ أودِع وادفع.** بحثٌ في الملفّات التي لمستَها عن أرقامٍ طويلةٍ وبريدٍ وأسماءٍ (الأمرُ في المرجع 01)؛ ثمّ `git -C … add <المسارات صراحةً>` و`commit` و`push origin main` (D-36م). مستودعُ المنصّة ممنوعٌ عليك دفعاً ودمجاً (D-36م، D-37م).

## قواعدٌ وسببُها
- **سجلٌّ يُلحَق فقط** (رأسُ `decisions.md`): القرارُ دليلُ ما أمر به المالك وقتَها؛ تعديلُه يمحو الدليل. سابقة: تصحيحُ أوقات D-40م..D-49م جاء سطراً جديداً لا تعديلاً.
- **اللاحقة «م»** تميّز قراراتِ المايسترو عن قرارات الخارطة المتداخلة الأرقام (D-24 فما فوق) — رأسُ `decisions.md`.
- **اللوحةُ لقطةٌ لا سجلّ:** `board.md` القديم بلغ ~207 كيلوبايت فجُمِّد؛ لذلك الحدُّ 150 سطراً والتاريخُ في السجلّ (`operating_model.md` §13، `templates/board_state_template.md`).
- **المقيسُ يغلب المكتوب:** رقمٌ في اللوحة يعارض قياساً للتوّ يُصحَّح في هذه الدورة (قالبُ اللوحة).
- **PDPPL:** لا أسماءَ أشخاص، ولا نصَّ رسائل المستخدمين، ولا أرقامَ شخصيّة في أيّ ملفّ (`handover_template.md`؛ `ledger.py` يفرضها في الكود).

## فخاخٌ وقعت فعلاً
- خطأ: قراراتٌ غيّرت قواعدَ الجلسات (D-52م..D-56م) سُجّلت بلا صفٍّ في `flow_changelog.md`، فبقيت بلا رقمٍ حتى كشفها بناءُ مهارة `schoolos-flow` (v2.9، 09-28 ~21:00).
  الصواب: قرارٌ يمسّ قاعدةً = سطرُ قرار + صفُّ فلو + رقمٌ جديد، في الدورة نفسِها.
- خطأ: ترويسةُ `handover.md` تقول «v2.7» والفلو v2.8 (09-28 19:55).
  الصواب: الرقمُ يُقرأ من آخر صفّ في `flow_changelog.md` كلَّ مرّة.
- خطأ: أوقاتٌ مقدَّرةٌ في D-40م..D-49م «متقدّمةٌ على الساعة» صُحّحت لاحقاً بسطرٍ خاصّ.
  الصواب: الوقتُ من الأداة لا من التقدير (`operating_model.md` §6).
- خطأ: `render_auto_sections.py --help`: لا واجهةَ أوامر له، فيُشغَّل كاملاً ويجلب `origin` (git fetch).
  الصواب: `--no-fetch` وحده؛ ولا `--help` له.
- خطأ: اللوحةُ تقول «أخضر 6.26 غيغا (20:26)» والمراقبُ يقيس 0.6 أحمر (21:01).
  الصواب: §1 يُكتب بعد قياسٍ في الدورة نفسِها، ومعه وقتُه.
- خطأ: `git add -A` في مستودع المايسترو يبتلع ما تركته 0102 غيرَ مودَع (ملفّان في `docs/` يومَ 09-28).
  الصواب: مساراتٌ صريحة؛ وما لا تعرفه تسأل عنه.
- خطأ: `render_charters.py` يُظنّ قرائيّاً: يكتب `docs/tab_charters.md`.
  الصواب: ليس من خطوات التسليم؛ صاحبُه `maestro-tabs` بعد تعديل `tabs.json`.

## ما ليس لهذه المهارة
مذكّراتُ الجلسات في `handover_notes/` (`maestro-archive-check`)؛ ذاكرةُ المشروع (`save-memory`)؛ بنودُ الخارطة وهجراتُها (0701)؛ `owner_requests.md` (0202، D-56م)؛ `ledger/events.jsonl` (يُكتب بـ`ledger.py` وحده، ومتجاهَلٌ في غيت)؛ إبلاغُ الجلسات نفسُه (`schoolos-flow` للصيغة).

## المراجع
| الملفّ | متى تقرأه |
|---|---|
| `references/00-files-and-formats.md` | قبل الكتابة في أيّ ملفٍّ حيّ لأوّل مرّة في الجلسة: صيغتُه وحدودُه ومن يكتب فيه |
| `references/01-board-log-commit.md` | عند تحديث اللوحة أو تدوير السجلّ أو الإيداع والدفع وفحص الخصوصيّة |
| `references/99-test-cases.md` | عند تعديل هذه المهارة أو وصفها |
