#!/usr/bin/env bash
# متابعةُ الدمج والنشر والأحمر في سكربتٍ واحد (جلسة 0601، أمر المالك 2026-10-18).
#
#   release_follow.sh <PR> <رأس8> [--mig] [--apply-cards]
#
# الخطوات: انتظارُ خضرة الفحصين المطلوبين فقط (بمهلةٍ؛ الاستشاريّ لا يوقف) ← عند الأحمر يُطبع سببُه ويُخرج 2 ← فحصُ الشروط ← دمجٌ بالرأس ←
# انتظارُ الهبوط ← انتظارُ نشرٍ جديد ← أسطرُ الهجرات والصحّةُ ← عرضُ البطاقات (وبـ--apply-cards تُنقل).
# تغيّر الرأس: يُطبع ويُخرج 3 (طلبُ هجرةٍ لا يُكمل أبداً؛ غيرُه يُكمل فقط إن كان approval_check ✔ على الرأس الجديد).
# --mig: يسمح بوجود هجرةٍ في الطلب، وبشرط أن تكون كلمةُ المالك المباشرةُ على الرأس مسجَّلةً في owner_confirmations.md.
# يُشغَّل بالتشغيل الخلفيّ المرصود لا بـnohup (يموت صامتاً على ويندوز). مخرجاتُ الخروج: 0 تمّ، 2 أحمر، 3 رأسٌ تغيّر،
# 4 شرطٌ لم يتحقّق، 5 انتهت المهلة.
set -u
# approval_check يطبع قبل حكمه أسطرَ سياقٍ («المصدر المقروء: …» بعد #56) فلا يُقرأ السطرُ الأوّل؛ الحكمُ سطرٌ يبدأ بـ✔ في أيّ موضعٍ من المخرج.
approval_passed() { grep -q '^✔'; }
# الفحصان المطلوبان للدمج فقط («ملخص بوابة الجودة» و«Security Summary»)؛ ما عداهما استشاريّ لا يحجب الدمج ولا يُنتظر.
# مخرجُ `gh pr checks` (اسم⇥حالة⇥…) ← FAIL إن أخفق أحدُهما، وPENDING إن غاب أو لم يكتمل، وإلا PASS.
required_verdict() { awk -F'\t' '$1=="ملخص بوابة الجودة"||$1=="Security Summary"{n++; if($2=="fail")f=1; else if($2!="pass"&&$2!="skipping")p=1} END{if(f)print "FAIL"; else if(n<2||p)print "PENDING"; else print "PASS"}'; }
PR="${1:?رقم الطلب}"; S="${2:?رأس 8 خانات}"; shift 2
MIG=0; APPLY=0
for a in "$@"; do case "$a" in --mig) MIG=1;; --apply-cards) APPLY=1;; esac; done
R=sh-school/shschool_mvp
DM=C:/Users/mesue/delivery_manager_work
OWNER="$DM/owner_confirmations.md"
HEALTH=https://shschoolmvp-production.up.railway.app/health/
CHECK_TIMEOUT=${CHECK_TIMEOUT:-5400}   # ثانية: انتظارُ الفحوص
LAND_TIMEOUT=${LAND_TIMEOUT:-1800}
DEPLOY_TIMEOUT=${DEPLOY_TIMEOUT:-1800}
cd /d/shschool_mvp 2>/dev/null || true

say() { echo "[$(date +%H:%M:%S)] $*"; }
prod_commit() { curl -s "$HEALTH" | sed -n 's/.*"commit": "\([0-9a-f]*\)".*/\1/p'; }
latest_dep() { railway deployment list 2>/dev/null | sed -n 2p; }

# 0) تحقّقٌ مبكّر: الطلب موجود ومفتوح، وسطرُ الاعتماد في وصفه يذكر الرأس، ونافذةُ النشر
INFO="$(gh pr view "$PR" --repo $R --json state,body,labels,headRefOid 2>/dev/null)" || { say "الطلب #$PR غير موجود"; exit 4; }
STATE=$(echo "$INFO" | python -X utf8 -c 'import sys,json;print(json.load(sys.stdin)["state"])')
[ "$STATE" = "OPEN" ] || { say "الطلب #$PR حالته $STATE لا OPEN"; exit 4; }
FIRST=$(echo "$INFO" | python -X utf8 -c 'import sys,json;print((json.load(sys.stdin)["body"] or "").split("\n")[0])')
case "$FIRST" in
  *"اعتُمد من المالك على 8500"*"الرأس $S"*) ;;
  *) say "سطرُ الاعتماد في وصف الطلب لا يذكر الرأس $S: «$FIRST»"; exit 4;;
esac
URGENT=$(echo "$INFO" | python -X utf8 -c 'import sys,json;print(int(any(l["name"]=="نشر-عاجل" for l in json.load(sys.stdin)["labels"])))')
# نافذةُ النشر (CLAUDE.md): لا دمجَ يُشغّل نشراً وسط الدوام (أحد–خميس 07:00–14:30 بتوقيت الدوحة) إلا بوسم «نشر-عاجل» أو EMERGENCY=1
# الدوحة = UTC+3 بلا توقيتٍ صيفيّ؛ لا نعتمد TZ لأنّه لا يُطبَّق في Git Bash على ويندوز
QNOW=$(( $(date -u +%s) + 10800 ))
DOW=$(date -u -d "@$QNOW" +%u); HM=$(date -u -d "@$QNOW" +%H%M)
if [ "$URGENT" != 1 ] && [ "${EMERGENCY:-0}" != 1 ] && [ "$DOW" != 5 ] && [ "$DOW" != 6 ] && [ "$HM" -ge 0700 ] && [ "$HM" -lt 1430 ]; then
  say "وسط الدوام ($HM) والطلب بلا وسم نشر-عاجل ولا EMERGENCY=1 — لا دمج"; exit 4
fi
# داخل النافذة بوسم «نشر-عاجل» أو EMERGENCY=1 لا يكفي الوسم وحده: لا بدّ من سطر «أمرُ نافذة» للمالك في owner_confirmations.md للطلب (أو بطاقته)
if [ "$DOW" != 5 ] && [ "$DOW" != 6 ] && [ "$HM" -ge 0700 ] && [ "$HM" -lt 1430 ]; then
  python -X utf8 -c 'import sys;sys.path.insert(0,sys.argv[1]);from record_owner_confirmation import window_order_present as w;t=open(sys.argv[2],encoding="utf-8").read();sys.exit(0 if (w(t,"#"+sys.argv[3]) or w(t,sys.argv[4])) else 1)' "$(dirname "$0")" "$OWNER" "$PR" "${CARD:-NONE}"     || { say "داخل نافذة الدوام ($HM) ولا سطرَ «أمرُ نافذة» للمالك في owner_confirmations.md للطلب #$PR — لا دمج (سجِّله: record_owner_confirmation.py --window-order)"; exit 4; }
fi
say "نشر-عاجل=$URGENT توقيت الدوحة=$HM"

# 1) انتظارُ اكتمال الفحوص بمهلة
t0=$(date +%s); backoff=30
while :; do
  out="$(gh pr checks "$PR" --repo $R 2>/dev/null)"
  # الحكمُ على الفحصين المطلوبين وحدَهما: أحمرٌ استشاريّ أو فحصٌ استشاريٌّ معلَّق لا يوقف المتابعة
  verdict="$(echo "$out" | required_verdict)"
  [ "$verdict" = PASS ] && break
  [ "$verdict" = FAIL ] && break
  [ $(( $(date +%s) - t0 )) -gt "$CHECK_TIMEOUT" ] && { say "انتهت مهلة الفحوص"; exit 5; }
  sleep "$backoff"; [ "$backoff" -lt 120 ] && backoff=$(( backoff + 15 ))
done

# 2) الرأس الحاليّ
H=$(gh pr view "$PR" --repo $R --json headRefOid -q .headRefOid)
if [ "${H:0:8}" != "$S" ]; then
  say "تغيّر الرأس: المطلوب $S والحاليّ ${H:0:8}"
  if [ "$MIG" = 1 ]; then say "طلبٌ فيه هجرة: لا يكمل بلا كلمة مالكٍ جديدة على الرأس الجديد"; exit 3; fi
  if python -X utf8 "$DM/tools/approval_check.py" pr "$PR" --head "${H:0:8}" 2>&1 | approval_passed; then
    say "الاعتمادُ ✔ على الرأس الجديد — أعيد التشغيل به"
    exec bash "$0" "$PR" "${H:0:8}" "$@"
  fi
  say "لا اعتمادَ على الرأس الجديد — أبلغ 0101"; exit 3
fi

# 3) الأحمر: اطبع سببه
ADVISORY=$(echo "$out" | awk -F'\t' '$1!="ملخص بوابة الجودة" && $1!="Security Summary" && $2=="fail"{print $1}')
[ -n "$ADVISORY" ] && say "فحوصٌ استشاريّةٌ حمراء (لا تحجب الدمج): $(echo "$ADVISORY" | paste -sd, -)"
BAD=$(echo "$out" | awk -F'\t' '($1=="ملخص بوابة الجودة" || $1=="Security Summary") && $2!="pass" && $2!="skipping"{print $1"\t"$2"\t"$4}')
if [ -n "$BAD" ]; then
  say "فحوصٌ غير ناجحة:"; echo "$BAD"
  echo "$BAD" | while IFS=$'\t' read -r name st url; do
    jid=$(echo "$url" | grep -oE 'job/[0-9]+' | cut -d/ -f2)
    [ -n "$jid" ] && gh api "repos/$R/actions/jobs/$jid/logs" 2>/dev/null \
      | grep -E 'FAILED |AssertionError|^.{0,40}E  ' | head -8 | cut -c1-260
  done
  exit 2
fi

# 4) الشروط
MIGN=$(gh pr diff "$PR" --repo $R --name-only | grep -c 'migrations/')
git fetch origin main -q 2>/dev/null
PC=$(prod_commit)
PEND=$(git diff --name-only "$PC" origin/main -- '*/migrations/*' 2>/dev/null | wc -l)
# الاعتماد: من نسخة الأدوات النظيفة (نسخة delivery_manager_work قد تحمل تعديلاً محليّاً غير معتمد)
AC="C:/Users/mesue/delivery_manager_work_rebuild/tools/approval_check.py"; [ -f "$AC" ] || AC="$DM/tools/approval_check.py"
cp -rn "$DM/evidence/." "$(dirname "$(dirname "$AC")")/evidence/" 2>/dev/null
if LEDGER_PATH="$DM/ledger/events.jsonl" python -X utf8 "$AC" pr "$PR" --head "$S" 2>&1 | approval_passed; then LINE=1; else LINE=0; fi
if [ "$MIG" = 1 ]; then LINE=$(( LINE + $(grep -c "$S.*مباشر\|مباشر.*$S" "$OWNER") )); [ "$(grep -c "$S.*مباشر\|مباشر.*$S" "$OWNER")" -ge 1 ] || LINE=0; fi
say "pr=$PR head=$S migrations_in_pr=$MIGN pending_on_prod=$PEND approval_ok=$LINE"
# ظلُّ الدمج الآليّ (W-20261020-020، بلا تفعيل): يطبع حكمَ مصنِّف شروط التوقف ولا يغيّر شيئاً ممّا بعده — يُستعمل لقياس أخطاء التصنيف أسبوعاً قبل عرض التفعيل على المالك
CLS="$(python -X utf8 "$(dirname "$0")/merge_stop_classifier.py" "$PR" --repo $R 2>&1 | head -8)"
say "[ظلّ] حكم الدمج الآليّ: $(echo "$CLS" | head -1) (لا أثر على هذا الدمج)"; echo "$CLS" | tail -n +2
if [ "$MIGN" != 0 ] && [ "$MIG" != 1 ]; then say "في الطلب هجرة ولم تُمرَّر --mig"; exit 4; fi
if [ "$PEND" != 0 ] || [ "$LINE" -lt 1 ]; then say "شرطٌ لم يتحقق (هجراتٌ معلّقة على الإنتاج أو لا سطرَ مالك)"; exit 4; fi

# 5) دمج ثمّ انتظارُ الهبوط
BASE=""
MOUT="$(gh pr merge "$PR" --repo $R --squash --match-head-commit "$H" 2>&1 | tail -2)"
say "gh: $MOUT"
# المقبول: دُمج، أو أُدخل الطابور، أو هو مصطفٌّ أصلاً؛ ما عداه رفضٌ فيخرج فوراً لا بعد مهلة الهبوط
case "$MOUT" in
  *"merge queue"*|*"already queued"*|*"Merged"*|*"merged"*|*"auto-merge"*) ;;
  *) [ "$(gh pr view "$PR" --repo $R --json state -q .state)" = "MERGED" ] || { say "رفض gh الدمج"; exit 4; };;
esac
t0=$(date +%s)
until [ "$(gh pr view "$PR" --repo $R --json state -q .state)" = "MERGED" ]; do
  [ "$(gh pr view "$PR" --repo $R --json state -q .state)" = "CLOSED" ] && { say "أُغلق الطلب"; exit 4; }
  [ $(( $(date +%s) - t0 )) -gt "$LAND_TIMEOUT" ] && { say "انتهت مهلة الهبوط"; exit 5; }
  sleep 20
done
say "هبط #$PR"

# 6) النشر: ننتظر حتى يعلن /health/ في الإنتاج commitاً يحوي دمجَ هذا الطلب (لا خطَّ أساسٍ يلتقط متأخراً)
MC=$(gh pr view "$PR" --repo $R --json mergeCommit -q .mergeCommit.oid 2>/dev/null)
[ -n "$MC" ] || { say "لا commit دمجٍ للطلب"; exit 4; }
say "commit الدمج: ${MC:0:7}"
git fetch origin main -q 2>/dev/null
t0=$(date +%s)
while :; do
  PC=$(prod_commit)
  if [ -n "$PC" ] && git merge-base --is-ancestor "$MC" "$PC" 2>/dev/null; then break; fi
  # الاحتياط: إن كان الإنتاج على commit غير معروف محلياً نجلب ثم نعيد
  git fetch origin main -q 2>/dev/null
  D=$(latest_dep)
  if echo "$D" | grep -Eq 'FAILED|CRASHED'; then say "فشل نشر: $D"; exit 4; fi
  [ $(( $(date +%s) - t0 )) -gt "$DEPLOY_TIMEOUT" ] && { say "انتهت مهلة النشر (الإنتاج على $PC)"; exit 5; }
  sleep 20
done
# النشر المقصود هو أحدث صفٍّ منتهٍ (SUCCESS/FAILED/CRASHED) لا أحدث صفٍّ مطلقاً: قد يكون فوقه نشرٌ لدمجٍ لاحقٍ ما زال WAITING
for _ in 1 2 3 4 5 6; do D=$(railway deployment list 2>/dev/null | sed 1d | grep -E "SUCCESS|FAILED|CRASHED" | head -1); [ -n "$D" ] && break; sleep 20; done
ID=$(echo "$D" | awk '{print $1}')
say "النشر: $D"
railway logs --deployment "$ID" 2>/dev/null | grep -E 'Applying ' | head -20
say "الصحّة: $(curl -s "$HEALTH" | cut -c1-140)"
echo "$D" | grep -q SUCCESS || exit 4

# 7) البطاقات: كلُّ بطاقةٍ مستحقّةٌ (publish_auto) تُنقل merged ثمّ published باسم 0601؛ وبلا --apply-cards يُعرض فقط
LIST="$(python -X utf8 "$DM/tools/publish_auto.py" 2>&1)"; echo "$LIST" | head -12
if [ "$APPLY" = 1 ]; then
  PCN=$(prod_commit)
  for c in $(echo "$LIST" | grep -oE 'W-[0-9]{8}-[0-9]{3}'); do
    python -X utf8 "$DM/tools/ledger.py" move "$c" pushed --by 0601 --waive-remote-check "الدمج تمّ فالفرع قد يكون حُذف (إنتاج $PCN)" >/dev/null 2>&1
    python -X utf8 "$DM/tools/ledger.py" move "$c" merged --by 0601 2>&1 | tail -1
    python -X utf8 "$DM/tools/ledger.py" move "$c" published --by 0601 --waive-remote-check "نشرٌ على الإنتاج $PCN وفحص /health/ سليم" 2>&1 | tail -1
  done
fi
exit 0
