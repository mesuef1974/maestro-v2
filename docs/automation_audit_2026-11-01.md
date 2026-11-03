# تقييمُ أتمتة مستودع الحوكمة بمنهج مهارة schoolos-automation — 2026-11-01

المنهج: البنودُ الاثنا عشر في `D:/shschool_mvp/.claude/skills/schoolos-automation/references/02-automation-checklist.md` (الحاسمةُ ★: 1 عدمُ التكرار، 2 مهلة، 4 قفل، 6 نتيجةٌ صادقة، 7 إنذارٌ عند الفشل **والغياب**، 8 اختبار، 9 أسرارٌ من البيئة، 10 لا بياناتٍ شخصيّة)، وعقدُ المخرج في `03-output-contract.md` (الغيابُ إنذار؛ آخرُ قيمةٍ سليمةٍ تبقى؛ الزمنُ بإزاحته؛ إنذارٌ واحدٌ لكلّ عطل)، وجردُ `00-inventory.md` (الهدفُ في Claude Code: صفرُ مهمّةٍ مفعَّلة، D-50م).
القياسات أُخذت 2026-11-01 ≈01:10 الدوحة على المجلّد الرئيس `C:/Users/mesue/delivery_manager_work` قراءةً فقط. ما لم يُقَس كُتب «غيرُ مقيس».

## 1) الجدول الموجز

| المكوّن | يعمل؟ | البنودُ الناقصة (من القائمة) | الخطورة |
|---|---|---|---|
| خطّاف Stop: `tools/session_state.py stop-hook` | نعم: 3,213 استدعاءً في `handover_notes/stop_hook_calls.log` (10-26→11-01)، 35 فشلاً مسجَّلاً كلُّها قبل 10-27 | 7 (الغيابُ لا يُقرأ: لا أحد يقيس عمرَ آخر «جُدِّد»)، 5 جزئيّاً (`~/.claude/hooks/stop.py` بلا منطقة) | P2 |
| خطّاف SessionStart: `session_identity.py` + `session_state.py hook` + `flow_pump_hook.py` | نعم | 2 (انتظارٌ حتى 15 ث لكلّ بدء: `session_identity.py:64`)، 5 (`datetime.now()` بلا منطقة `session_identity.py:206,223`)، 7 (فشلُ التعرّف يُكتم بـ`return ""` في `session_state.py:859` ولا يُقاس) | P2 |
| خطّاف PreToolUse: `lang_guard.py` (بلا matcher: كلُّ أداة) و`identity_guard.py` و`memory_index_guard.py` و`~/.claude/hooks/pre_bash.py` | نعم، الوضع `block` (`lang_guard.mode`) | 5 (السجلّ بـUTC: `lang_guard.py:79` — مخالفٌ لقاعدة الدوحة)، 7 (سجلٌّ 95,862 سطراً لا يقرؤه أحد)، 2 (قراءةُ 400 KB من النصّ عند كلّ أداة: `lang_guard.py:30,54`) | P2 |
| خطّاف PostToolUse: `inbox.py hook`، `ready_mark_hook.py`، `msg_counter.py hook`، `~/.claude/hooks/post_edit.py` | نعم (0.71 ث للصندوق) | 5 (`ready_mark_hook.py:37`، `msg_counter.py:33` بلا منطقة)، 7 (فشلُ `post_edit` يُكتم: `except Exception: pass` سطر 36) | P3 |
| المضخّة: `flow_pump_hook.py` → `flow_pump.py --apply` (+ `ledger_sync` + `pump_health`) | نعم: 3,270 سطراً في `ledger/flow_pump.log`، 2,467 دورةً بـrc=0 و2 بـrc=2؛ آخرُ دورة 01:07 | 7 ★ (الغيابُ يقرؤه `watch_once.py:324` ولا أحد يشغّل `watch_once`)، 2 جزئيّاً (`approval_check.run()` بلا مهلة: `approval_check.py:39` ويُستدعى من `flow_pump.py:87` كلَّ دورة)، 5 (`flow_pump.py:428,1496` بلا منطقة)، 6 جزئيّاً (فشلُ مرحلةٍ يُطبع في `.out` ويُكتب rc=0) | P1 |
| الدفتر `tools/ledger.py` | نعم: 12,190 حدثاً، 841 بطاقة، تحميل 0.105 ث + اختزال 0.005 ث | لا نقصَ حاسماً؛ 7 (سطرٌ تالف يُهمَل بتحذير stderr فقط: `ledger.py:89`) | P3 |
| `push_approved.py` / `approval_check.py` / `visual_gate.py` / `record_owner_confirmation.py` | نعم | 2 (`approval_check.py:39`، `visual_gate.py:180` بلا مهلة)، 4 (`record_owner_confirmation.py:150,187` إلحاقٌ بلا قفل)، 7 (`visual_gate.py:282,339` `except Exception: pass`) | P2 |
| الصندوق `inbox.py` (send/read/wait/hook) والجرس | نعم: 8 مراقبات حيّة (نبضٌ ≤1 ث) | 7 ★ (صندوق `0000` فيه 2 معلَّقان ولا قارئَ له؛ نبضا 0428 و0702 ميّتان منذ 153,172 ث ≈ 42.5 س ولم يُحصدا)، 12 (`reap` بلا مشغِّل) | P2 |
| مراقبُ الإيقاظ `wake_monitor.py` + المهامُّ الدوريّة `periodic_tasks.py` | **لا**: آخرُ سطر في `wake_log.jsonl` 2026-10-29T15:11، و`ledger/periodic_state.json` كلُّه 2026-10-29، و`ledger/periodic_log.jsonl` غيرُ موجود | 7 ★ (غائبٌ ~58 ساعة بلا إنذار)، 12 (مشغّلُه «الكنّاس» غيرُ مسجَّل في أداة المهامّ) | P1 |
| مهامُّ Claude المجدولة `~/.claude/scheduled-tasks/*` | 5 مسجَّلة كلُّها `enabled=false` (المفعَّل = 0: متوافقٌ مع D-50م)؛ 9 مجلّداتٍ يتيمةٍ غيرُ مسجَّلة | 12 (جردٌ لا يطابق القرص: `usage-snapshot-hourly` موقوفٌ و0 تشغيلٍ بينما الذاكرة تُلزم 0101 بلقطتين يدويّاً) | P3 |

## 2) ما يعمل جيّداً (بأدلّة)

- الدفتر محميٌّ بقفلٍ بين العمليّات (`ledger.py:98-130`، `msvcrt`/`fcntl` بمهلة 30 ث) ونسخةٍ يوميّةٍ قبل أوّل إلحاق (`ledger.py:133-149`، `BACKUP_KEEP=30`)؛ وسطرٌ تالف لا يُسقط القراءة (`ledger.py:89`). الانتقالاتُ محروسة: `check_transition` (`ledger.py:411`) يمنع القفزَ فوق `GATES`، والاعتمادُ يلزمه `--head` sha8 (`check_head:425`) و`--note`، و`pushed` يرفض رأساً يخالف المعتمَد (قفلُ الرأس، `ledger.py:355-362`)، والحرّاسُ القابلة للاستثناء كلُّها مسجَّلة بسبب: `--waive-spec` (670/708)، `--waive-wip` (779)، `--waive-preflight` (853)، `--waive-pump-only` (989)، و`reapprove` (1472) و`waive-head` (1519، يرفض الملفّات الحاكمة: 1566). لا بياناتٍ شخصيّة: `_PII` (`ledger.py:43`) يرفض رقمَ هويّةٍ أو بريداً في كلّ حقلٍ نصّيّ.
- المضخّة: قفلٌ بإنشاءٍ حصريّ `O_EXCL` وقفلٌ ميّتٌ بعد 900 ث (`flow_pump.py:1366-1376`)، ومفاتيحُ إيقافٍ بلا نشر لكلّ مرحلة (`flow_pump.off`/`.nomerge`/شجرة/prepush/طلب: 1340-1343, 1435-1458)، والخطّافُ لا يحجب الجلسةَ (`Popen` منفصل، `flow_pump_hook.py:103-122`) ولا يطلق دورةً تحت قفلٍ حيّ (`pump_running:84`). الدمجُ الآليّ مقيَّد بالرأس `--match-head-commit` (`flow_pump.py:1254`) ويُستثنى الهجراتُ والأمنُ والواسع (`SENSITIVE_GLOBS:69`، `MAX_FILES:71`). نسبةُ العبور بلا تدخّل آخرَ 24 س = 0.75 (15/20) في `ledger/pump_health.jsonl` سطر 2026-11-01، و0.812 يوم 10-30.
- `push_approved.py`: حرّاسٌ صريحة قبل أيّ دفع (الفرع، الحالة، رأسُ الاعتماد، الشجرةُ النظيفة، إيصالُ prepush، `approval_check`: 83-115)، دفعٌ بلا `--force`، وتحقّقٌ من البعيد بعد الدفع (127-129)، ورمزُ خروج 3 عند الرفض (149).
- `record_owner_confirmation.py`: لا يكتب نصّاً منسوباً للمالك لم يُسجَّل (`standing_quote:90-103`)، ويرفض التفويضَ لما يمسّ الهجراتِ والواجهةَ والأمنَ وسلسلةَ الاعتماد نفسَها (`FORBIDDEN:59-65`).
- خطّاف Stop: كلُّ استدعاءٍ يُسجَّل بنتيجته (`_log_stop_call:863`) فلا رجوعَ صامتاً — 863 «جُدِّد» و581 «تخطّي: الرقم غير محدَّد» و35 «ValueError: الحجم يتجاوز 4096» آخرُها 10-27 (أُصلح بـ`fit_state:635`). الكتابةُ ذرّيّة (`os.replace`) وidempotent مع نبضٍ كلَّ 10 د (`write_state:652`). الحالةُ المحقونة تُفحص ضدّ كلماتِ الاعتماد والـPII (`validate:404-474`).
- الصندوق: إلحاقٌ فقط، مراقبٌ واحدٌ لكلّ رقم، يخرج إذا تغيّرت بصمةُ الشيفرة (`inbox.py:113-129`)، ونبضٌ لا يُقبل من معرّفٍ غير حيّ (`beat:77-83`). رفضُ الإرسال لرقمٍ بلا جلسةٍ حيّة (`main:334`).
- الاختبارات: 555 اختباراً نجحت في 192 ث (`pytest` على 17 ملفاً تخصّ المكوّنات المقيَّمة)؛ الدفتر وحده 22 ملفَ اختبار، و`approval_check` 5.
- الأسرار (البند 9): لا نمطَ سرٍّ ولا عنوانَ إنتاجٍ حرفيٍّ في أيٍّ من 23 ملفاً (المدقّق: صفر `G-SECRET`/`G-HOST`/`G-QID`).
- الجدولة في Claude Code: 0 مهمّةٍ مفعَّلة (هدفُ `00-inventory.md` §4 محقَّق).

## 3) ما يتعطّل أو يفشل صامتاً (مسار:سطر)

1. **مراقبُ الإيقاظ والمهامُّ الدوريّة غائبان منذ 2026-10-29 15:11** (`wake_log.jsonl` آخرُ سطر؛ `ledger/periodic_state.json` كلُّ المفاتيح `2026-10-29`؛ `ledger/periodic_log.jsonl` الذي يعد به `periodic_tasks.py:9` غيرُ موجود). المشغّلُ الوحيد لـ`periodic_tasks.run_due` هو `wake_monitor.py:547`، ومشغّلُ `wake_monitor` كان مهمّةَ Claude (المجلّدات `wake-send-10min`، `watch-readonly-10min`، `wake-monitor-weekly-trial` على القرص) وهي غيرُ مسجَّلةٍ في أداة المهامّ (القائمةُ تعيد 5 مهامّ فقط). الإنذارُ الوحيد للغياب هو `watch_once.py::monitor_of_monitor_alerts` (`watch_once.py:322-345`، عتبة 30 د) ولا خطّافَ ولا مهمّةَ تشغّل `watch_once` (لا ذكرَ له في `~/.claude/settings.json`). النتيجة: الصمتُ يُقرأ نجاحاً — النمطُ المضادّ الأوّل في `02-automation-checklist.md`.
2. **فشلُ مراحل المضخّة لا يغيّر رمزَ الخروج**: `flow_pump.py:1479` يأخذ `rc` من `ledger_sync.cycle` وحده ثمّ `1496` يكتب `rc=0` ولو فشل الدفع/prepush. القياس: 30 سطرَ «✘» في `ledger/flow_pump.log` (أمثلة: `prepush-حوكمة: W-20261028-014 3bd3bca5 ✘ رمز الخروج 1` مرّتين 10-31؛ `prepush: W-20261031-003 5fcf2a4a ✘`) بينما rc≠0 ظهر مرّتين فقط في 3,270 سطراً. من يقرأ `.out`؟ لا أحد آليّاً؛ التصعيدُ بعد 90 د يكتب في `ledger/pump_report_0101.txt` (`pump_health.py:92-96`) وهو ملفٌّ يُلحَق ولا يُقرأ بعقدٍ.
3. **مهلاتٌ غائبة في مسار المضخّة**: `approval_check.py:39` `subprocess.run` بلا `timeout` ويُستدعى لكلّ بطاقةٍ معتمَدةٍ من `flow_pump.py:86-93` و`push_approved.py:52` (هنا بمهلة 120 ث). تعليقُ `gh` فيه يعلّق الدورةَ حتى موت القفل (900 ث) ثمّ تتداخل دورةٌ جديدة فوقها. `visual_gate.py:180` كذلك بلا مهلة.
4. **خطّاف Stop يتخطّى 18%** من الاستدعاءات (581/3,213 «الرقم غير محدَّد: 0 مرشّحاً») — جلساتٌ بلا عنوانٍ رقميّ أو خارج الأشجار؛ ليس عطلاً لكنّه ليس مقيساً كغيابٍ لأحد. و23 استدعاءً «2 مرشّحاً: 0101,01…» (التباسُ شجرةٍ مشتركة).
5. **صندوق النظام `0000`**: `inbox.py pending` → `0000: 2`؛ `SYSTEM_RECEIVERS={"0000"}` يَعِد بـ«مراقبٍ خاصّ» (`inbox.py:213`) ولا مراقبَ (لا `0000.beat`). ونبضا `0428.beat` و`0702.beat` عمرُهما 153,172 ث؛ `reap` (`inbox.py:151`) يحتاج من يشغّله.
6. **سجلّاتٌ بغير توقيت الدوحة** (البند 5 وعقدُ المخرج §4): `lang_guard.py:79` يكتب UTC صراحةً (95,862 سطراً)؛ `flow_pump.py:428,1496`، `ready_mark_hook.py:37`، `msg_counter.py:33`، `~/.claude/hooks/stop.py:9`، `session_identity.py:206` بلا إزاحة.
7. **كتمٌ على خطواتٍ جوهريّة**: `~/.claude/hooks/post_edit.py:36` (`except Exception: pass` يكتم فشلَ ruff/eslint نفسه)؛ `flow_pump.py:175` (`hand_off` إلى الصندوق يفشل صامتاً فتعلق البطاقةُ بلا مالكٍ مُبلَّغ)؛ `session_state.py:597` (`_log_injection` فشلُها صامت)؛ `visual_gate.py:282,339`.
8. **زمنُ البدء**: `session_identity.app_title` تنتظر حتى 15 ث (`ID_WAIT_S=15.0`, `session_identity.py:64-77`) حين لا يُطابَق المعرّف؛ ثمّ `git merge-base` (`:296`) بمهلة 10 ث. قياسٌ بحمولةٍ بلا معرّف: 1.15 ث؛ مع معرّفٍ غير مكتوبٍ بعدُ: غيرُ مقيس (الحدُّ الأقصى 25 ث).

## 4) المخاطر

- **R1 (P1) العالقُ خارج مراحل المضخّة لا يُوقَظ**: `STALE_RULES` (`wake_monitor.py:52-59`) تغطّي routed/in_progress/ready_for_review؛ بغياب المراقب منذ 10-29 لا جرسَ لها إلّا ما تطلقه المضخّةُ نفسُها للمراحل approved/pushed/merged (`pump_health.py:4-6`). الأثر: بطاقاتٌ موجَّهةٌ تنتظر أيّاماً — السيناريو الذي دوّنه `wake_monitor.py:14` نفسُه («39 موجَّهةً بقيت أياماً»).
- **R2 (P1) غيابُ المضخّة غيرُ مرصود**: المضخّةُ تدور حين يتحرّك خطّافٌ في جلسةٍ ما (`flow_pump_hook.py:10-11`)؛ ليلاً أو عند تعطّل الخطّافات تتوقّف، والعتبةُ في `watch_once` (30 د) لا تُشغَّل. مفتاحُ `flow_pump.off` إن نُسي مفعَّلاً فالصمتُ كاملٌ أيضاً (الدورةُ تطبع «لا دورة» وتخرج 0: `flow_pump.py:1381-1383`).
- **R3 (P2) خطّافاتٌ ثقيلةٌ عند كلّ أداة**: `lang_guard` بلا matcher يقرأ ذيلَ النصّ 400 KB في كلّ PreToolUse، و`inbox.py hook` بلا matcher في كلّ PostToolUse (0.71 ث مقيس). مع 20+ جلسةٍ حيّة (`msg_counter.json`: 21 جلسة) يتكرّر ذلك آلافَ المرّات يوميّاً (Stop وحده 800 استدعاءً يوم 10-29).
- **R4 (P2) `events.jsonl` 5.06 MB ينمو بلا تقليم** (12,190 حدثاً منذ 09-28؛ ≈150 KB/يوم). اليوم 0.1 ث للتحميل، ويُحمَّل في كلّ Stop وكلّ دورة مضخّةٍ عدّةَ مرّات (`flow_pump.py:1410,1482`, `ledger_sync.py:253,272`). الخطرُ تدريجيّ لا فوريّ.
- **R5 (P2) إلحاقٌ بلا قفل في `owner_confirmations.md`** (`record_owner_confirmation.py:150,187`): سجلُّ الاعتماد نفسُه، تكتبه جلساتٌ متوازية؛ احتمالُ التداخل منخفضٌ لكنّ أثرَه على `approval_check` عالٍ.
- **R6 (P3) معرّفاتُ جهازٍ حرفيّة**: `C:/Users/mesue/...` في 17 ملفاً من `tools/` (مثل `session_identity.py:157,165,182`) — ليست أسراراً لكنّها تخالف روحَ البند 9 (المستودعُ قد يُنشر) وتكسر النقل.
- **R7 (P3) جردٌ غيرُ مطابق**: 14 مجلّداً في `~/.claude/scheduled-tasks/` مقابل 5 مسجَّلة؛ بينها `qatar-advisor-security-sprint` بصلاحيّات push/deploy كاملة (موقوفة، آخرُ تشغيل 04-10) و`skylive` فارغة.

## 5) التبسيطاتُ الممكنة (مرتّبةً بالعائد ÷ الخطر)

1. **إنذارُ غيابٍ واحد بدل مراقبٍ جديد**: تشغيلُ `monitor_of_monitor_alerts` من داخل خطّاف Stop (هو يحمّل الدفترَ أصلاً) مرّةً كلَّ 30 د بختمٍ مثل `flow_pump.stamp`، يطبع سطراً واحداً إلى الجلسة حين يتجاوز عمرُ `wake_log.jsonl` أو `flow_pump.log` العتبة. عائدٌ عالٍ (يغلق R1/R2) وخطرٌ منخفض (قراءةُ mtime).
2. **رمزُ خروجٍ صادق للمضخّة**: `_run` يعيد 1 إن وُجد «✘» في أيّ مرحلة، ويكتب `ledger/LAST_STATUS.json` بصيغة عقد المخرج (`ok`, `finished`, `counts`, `err` رمزاً، `next_due`) بدل سطر `rc=0`. عائدٌ عالٍ، خطرٌ منخفض، يستوفي البند 6 و7.
3. **إعادةُ المراقب إلى مشغِّلٍ قائم**: `wake_monitor --stale --commit` يحتاج `send_message` (أداةُ تطبيق) فلا يصلح خطّافاً؛ لكن `periodic_tasks.run_due` لا يحتاج إلّا الصندوقَ: نقلُه إلى دورة المضخّة (`flow_pump._run` بعد `pump_health`) يعيد المهامَّ الدوريّة بلا مهمّة Claude جديدة (يحترم D-50م).
4. **مهلةٌ في `approval_check.run()`** (سطر 39): `timeout=120` كما في `push_approved.py:52`. سطرٌ واحد، يغلق تعليقَ الدورة.
5. **matcher للخطّافات العامّة**: `lang_guard` على `Bash|PowerShell|SendMessage|…` لا على الكلّ، و`inbox.py hook` على أدواتٍ ذات دور (أو كلَّ N استدعاء بختم). يقلّل R3 بلا تغيير منطق.
6. **توحيدُ الطوابع بالدوحة**: `datetime.now(DOHA)` في المواضع السبعة (§3 بند 6). خطرٌ صفر.
7. **حصادُ النبضات والمراقبات الميّتة**: استدعاءُ `inbox.reap` من دورة المضخّة (الدليلُ `session_directory` موجود) وتعيينُ قارئٍ لصندوق `0000` أو حذفُ الاستثناء `SYSTEM_RECEIVERS`.
8. **تقليمُ `events.jsonl`**: أرشفةُ البطاقات المنتهية (`RELEASING_STATES`) الأقدم من 30 يوماً إلى `ledger/backups/` مع حدث `created` موجَز — يحتاج اختبارَ `reduce_state` على الملفّ المختزَل؛ عائدٌ متوسّطٌ وخطرٌ متوسّط فيؤجَّل حتى يتجاوز التحميلُ 0.5 ث.
9. **تنظيفُ `~/.claude/scheduled-tasks/`**: حذفُ المجلّدات التسعة اليتيمة (بعد موافقة المالك: إعدادٌ دائمٌ على جهازه، البند 12) وتحديثُ §4 في `00-inventory.md`.
10. **استبدالُ المسارات الحرفيّة** بـ`ROOT` المحسوب (موجودٌ أصلاً في كلّ ملفّ) — 17 ملفاً، عائدٌ منخفضٌ لكنّه آمن.

## 6) نتائجُ `audit_automation.py --json`

الأمر: `python -I D:/shschool_mvp/.claude/skills/schoolos-automation/scripts/audit_automation.py --json <23 ملفاً>`؛ رمزُ الخروج 1 (FAIL واحد). النوعُ المكتشَف لكلّها `pyscript`.

| الملف | FAIL | WARN |
|---|---|---|
| tools/pump_health.py | **S-EXIT** (لا `sys.exit` برمز) | S-LOCK، S-STATUS |
| tools/session_state.py | — | S-SWALLOW، S-LOCK |
| tools/session_identity.py | — | S-SWALLOW، S-NAIVE-TIME (2)، S-LOCK، S-STATUS |
| tools/lang_guard.py | — | S-SWALLOW، S-LOCK، S-STATUS |
| tools/flow_pump.py | — | S-SWALLOW، S-NAIVE-TIME (2) |
| tools/flow_pump_hook.py | — | S-SWALLOW، S-STATUS |
| tools/ledger_sync.py | — | S-LOCK، S-STATUS |
| tools/ledger.py | — | لا ملاحظات |
| tools/push_approved.py | — | S-LOCK |
| tools/approval_check.py | — | S-LOCK |
| tools/visual_gate.py | — | S-SWALLOW، S-LOCK |
| tools/record_owner_confirmation.py | — | S-LOCK، S-STATUS |
| tools/inbox.py | — | S-SWALLOW، S-LOCK، S-STATUS |
| tools/wake_monitor.py | — | S-LOCK، S-STATUS |
| tools/identity_guard.py | — | S-LOCK |
| tools/memory_index_guard.py | — | S-SWALLOW، S-LOCK، S-STATUS |
| tools/message_length_guard.py | — | S-SWALLOW، S-LOCK، S-STATUS |
| tools/ready_mark_hook.py | — | S-NAIVE-TIME (1)، S-LOCK، S-STATUS |
| tools/msg_counter.py | — | S-NAIVE-TIME (1)، S-LOCK |
| ~/.claude/hooks/stop.py | — | S-NAIVE-TIME (1)، S-LOCK، S-STATUS |
| ~/.claude/hooks/pre_bash.py | — | S-LOCK، S-STATUS |
| ~/.claude/hooks/post_edit.py | — | S-SWALLOW، S-LOCK، S-STATUS |
| ~/.claude/hooks/handoff_guard.py | — | S-SWALLOW، S-LOCK |

ملاءمةُ المدقّق: صُمّم لمسارات Actions وCelery وجدولة ويندوز وسكربتاتٍ مجدولة؛ الخطّافاتُ قصيرةُ العمر تُستدعى آلافَ المرّات فـ`S-LOCK` و`S-STATUS` لا يصلحان لها حرفيّاً (قفلٌ لكلّ خطّاف يبطئ كلَّ أداة)، ويصلحان للمضخّة والمراقب والمزامنة. `S-SWALLOW` التقط مواضعَ مقصودةً («الخطّاف لا يُسقط الجلسة») ومواضعَ جوهريّة (§3 بند 7) ولا يميّز بينها. `S-EXIT` على `pump_health.py` صحيحٌ نصّيّاً لكنّ الملفَّ مكتبةٌ تُستدعى من المضخّة أساساً. ما لا يراه المدقّق — الغيابُ والمشغِّلُ ومن يقرأ المخرج — هو ما حمل الخطورةَ P1 أعلاه.

## 7) أرقامٌ مرجعيّة (للمقارنة اللاحقة)

| المؤشّر | القيمة | التاريخ | الأداة |
|---|---|---|---|
| events.jsonl | 5,062,970 بايت / 12,190 حدثاً / 841 بطاقة | 2026-11-01 01:05 | `wc`, `ledger.load_events` |
| زمنُ تحميل الدفتر + الاختزال | 0.105 + 0.005 ث | 2026-11-01 | `time.perf_counter` |
| زمنُ `session_state.py stop-hook` (بلا معرّف) | 0.67 ث | 2026-11-01 | قياسٌ محلّيّ |
| زمنُ `session_identity.py` / `inbox.py hook` | 1.15 ث / 0.71 ث | 2026-11-01 | قياسٌ محلّيّ |
| استدعاءاتُ Stop | 3,213 (10-28: 583، 10-29: 800، 10-30: 352، 10-31: 145) | 2026-11-01 | `stop_hook_calls.log` |
| دوراتُ المضخّة | 2,467 rc=0، 2 rc=2، 30 «✘»؛ 10-28: 519 سطراً | 2026-11-01 | `flow_pump.log` |
| نسبةُ العبور بلا تدخّل | 0.75 (15/20) | 2026-11-01 00:07 | `pump_health.jsonl` |
| آخرُ إيقاظ / آخرُ مهمّةٍ دوريّة | 2026-10-29 15:11 / 2026-10-29 | — | `wake_log.jsonl`, `periodic_state.json` |
| مهامُّ Claude المفعَّلة | 0 من 5 مسجَّلة (14 مجلّداً) | 2026-11-01 | `list_scheduled_tasks` |
| اختباراتُ المكوّنات | 555 ناجحاً / 192 ث | 2026-11-01 | `pytest` (17 ملفاً) |
| عمرُ `LAST_STATUS.json` للنسخ الاحتياطيّ | كُتب 2026-10-31 03:00 (≈22 س) | 2026-11-01 | `~/.claude/backups/` |
