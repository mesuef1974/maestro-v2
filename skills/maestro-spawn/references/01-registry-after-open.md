# السجلُّ بعد الفتح أو إعادة الفتح أو إعادة التسمية
متى تقرأ هذا الملف: بعد أن تظهر الجلسةُ في الشريط باسمها (أو تُعاد من الأرشيف، أو يتغيّر اسمُها)، وقبل أن تعلن الفتحَ منتهياً.
المصدر: `session_policy.serial` و`archive_when` في `tabs.json`؛ `validate_registry.py` و`session_load_v2.py` (يقرآن هذه الملفّات)؛ مهارةُ maestro-spawn الأصل (الخطوة 6: «جدِّد بعد كلّ فتحٍ أو أرشفةٍ أو إعادة تسمية»).

## 1) الملفّاتُ الثلاثة (في `C:/Users/mesue/delivery_manager_work/projects/schoolos/`)
| الملفّ | ما يُكتب | من يقرؤه |
|---|---|---|
| `tabs.json` | الاسمُ في `tabs[number="04"].members`؛ و`session_policy.serial.per_tab_next["04"]` + 1 (للفتح الجديد وحده) | validate_registry، route_now، spawn_preflight، render_charters |
| `session_names.json` | `"<مجلّد الشجرة>": "<الاسم>"` | session_load_v2 (بدونه تظهر الشجرةُ يتيمةً غيرَ صالحةٍ للإسناد) |
| `sessions_snapshot.json` | قائمةُ عناوين الجلسات الحيّة (JSON list) | `validate_registry --sessions` |
- مجلّدُ الشجرة يُعرف من الجلسة نفسها (مسارُ عملها `…/.claude/worktrees/<الاسم>`) أو من `unnamed_trees` في `session_load_v2.py --json --no-fetch` بعد الفتح.
- اكتب بـEdit تعديلاً موضعيّاً؛ لا تُعِد كتابةَ `tabs.json` كلّه (62KB، فيه مواثيقُ لا تمسّها).

## 2) التحقّق
```bash
python -X utf8 C:/Users/mesue/delivery_manager_work/tools/validate_registry.py \
  --sessions C:/Users/mesue/delivery_manager_work/projects/schoolos/sessions_snapshot.json
```
- المخرجُ المطلوب حرفيّاً: «السجلُّ متّسق» (رمز 0). غيرُه قائمةُ مشكلات (رمز 1)، أشهرُها:
  - «جلسةٌ حيّةٌ غيرُ مسجَّلة» ← نسيتَ `tabs.json`.
  - «مسجَّلةٌ بلا جلسةٍ حيّة» ← نسيتَ `sessions_snapshot.json` أو أُرشفت ولم تُحذف من الأعضاء.
  - «الأعضاءُ (11) فوق الحدّ (10)» ← فتحٌ فوق `live_cap`.
  - «أوّلُ خانتين … لا تطابقان رقمَ مرحلته» ← جلسةٌ في غير مرحلتها.
- `--sessions` يأخذ **مسارَ ملفّ** JSON لا عناوين في سطر الأوامر.
- ثمّ توليدُ `docs/tab_charters.md` (الأعضاءُ فيه) بمهارة `maestro-tabs`.

## 3) إعادةُ التسمية (المهمّةُ تغيّرت، D-44م)
- `set_session_title` بموافقة التطبيق؛ الرقمُ لا يتغيّر.
- الاسمُ الجديد في المواضع الثلاثة، ثمّ التحقّق. لا زيادةَ لـ`per_tab_next`.

## 4) الأرشفة (للتذكير — التنفيذُ في maestro-archive-check)
- الشروط: مدموجٌ ومنشور (أو أُغلق الطلب) + الخارطةُ محدَّثة + مذكّرةُ تسليمٍ في `handover_notes/<مجلّد الشجرة>.md` + لا ملفّاتٍ غيرِ مودَعة + لا تعمل الآن.
- `archive_check.py <مجلّد الشجرة> --title "<الاسم>"` يرفض النواةَ الثابتةَ وحدها وما لم تتحقّق شروطُه.
- بعدها: احذف الاسمَ من أعضاء 04 ومن اللقطة، وأضِف سطراً إلى `archived_log` (العنوان، التاريخ، القرار) — ولا تُنقص `per_tab_next`.

## أنماطٌ مضادّة
- تحديثُ السجلّ قبل أن يضغط المالكُ الفتح: إن رفضه صار السجلُّ يصف جلسةً لا وجودَ لها.
- زيادةُ `per_tab_next` عند إعادة فتح مؤرشفة أو إعادة تسمية.
- تحرير `docs/tab_charters.md` يدويّاً لإضافة العضو — يُولَّد من tabs.json ويُكتب فوقه.
- ترك الشجرة بلا سطرٍ في `session_names.json` ← تظهر «شجرةً يتيمة» في `watch_once` (`orphan_tree`) ويُسأل المالكُ عن صاحبها، ولا تُسنَد إليها بطاقة.
