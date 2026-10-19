# تسجيلُ خطّاف ready_mark — مقطعٌ يلصقه المالكُ وحدَه (W-20261015-015)

الخطّافُ `tools/ready_mark_hook.py`: بعد كلِّ إرسالِ رسالةٍ تبدأ بـ«جاهزٌ للمعاينة» ويرد فيها `(رقمُ الجلسة)` ورمزُ بطاقةٍ و`الرأس <sha>` يستدعي `ready_mark.mark` وحدَه
(فتسري بوّاباتُه: الرأسُ موجودٌ ويحمل رمزَ البطاقة، والبطاقةُ غيرُ معتمدة، والحاملةُ هي المرسِلة). لا يعتمد ولا يدفع ولا يراسل.
أيُّ فشلٍ (JSON تالف، دفترٌ غائب، رفضُ بوّابة) يخرج بـ0 بلا ناتج، ويُكتب سببُه في `logs/ready_mark_hook.log` إن وُجد المجلّد.

## الصيغةُ المطلوبة في الرسالة (وإلّا لا يفعل شيئاً)

`جاهزٌ للمعاينة (0702) W-20261015-014 الرأس 904a660d الرابط http://localhost:8500/… الدور principal`

## المقطع (في `~/.claude/settings.json` ضمن `hooks`)

```json
"PostToolUse": [
  {
    "matcher": "SendMessage|mcp__ccd_session_mgmt__send_message",
    "hooks": [
      {
        "type": "command",
        "command": "python C:/Users/mesue/delivery_manager_work/tools/ready_mark_hook.py",
        "timeout": 20
      }
    ]
  }
]
```

إن وُجد في الملفّ مفتاحُ `PostToolUse` أصلاً فأضف العنصرَ أعلاه إلى مصفوفته لا مفتاحاً ثانياً.

## تراجعٌ

احذف العنصرَ من المصفوفة؛ لا أثرَ آخر. وللتحقّق قبل التفعيل:
`python -m unittest test_ready_mark_hook` من مجلّد `tools/` (7 اختبارات).
