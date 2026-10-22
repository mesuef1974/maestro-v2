# مقطعا تسجيل الحارسَين في ~/.claude/settings.json (0103، W-20261013-030/032)

أذن المالك («مسموح هيا»، الهدف SETTINGS-guards-warn). يُلصق المقطعان داخل المصفوفة
`hooks.PreToolUse` في `C:\Users\mesue\.claude\settings.json`، بعد عنصر `lang_guard.py` مباشرةً
(وقبل `]` التي تغلق `PreToolUse`)، مع فاصلة بعد عنصر lang_guard. كلاهما بوضع warn افتراضياً (لا حجب).

```json
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python C:/Users/mesue/delivery_manager_work/tools/memory_index_guard.py"
          }
        ]
      },
      {
        "matcher": "SendMessage|mcp__ccd_session_mgmt__send_message",
        "hooks": [
          {
            "type": "command",
            "command": "python C:/Users/mesue/delivery_manager_work/tools/message_length_guard.py"
          }
        ]
      }
```

التحقّق بعد اللصق: `python -c "import json;json.load(open(r'C:\Users\mesue\.claude\settings.json',encoding='utf-8'))"`
ثمّ جلسةٌ جديدة. الرجوع: حذف العنصرين. الحارسان لا يُسقطان جلسةً (أيّ خللٍ = سماح).
القياس بعد أسبوع: `token_measure.py --reinject --days 7` و`message_length_guard.py --measure`.

## بدء قياس الأسبوع (0103، 2026-10-13 ~22:30 توقيت الدوحة)
الحارسان مسجَّلان (تحقّقتُ من settings.json) بوضع warn. الأساس قبل التسجيل: إعادة حقن الفهرس 723 في 31 جلسة/7 أيام (الأكبر 128)؛ الرسائل 8799 وسيطها 488 حرفاً وp90 1007 و901 رسالة فوق 1000 حرف (1,269,238 من 5,103,985 حرفاً).
القياس الثاني بعد 7 أيام (2026-10-20) بالأمرين نفسهما، ثم قرار الحجب في قرارٍ مسجَّل.
