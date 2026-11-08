#!/usr/bin/env bash
# خانةُ معاينةٍ إضافيّة بجانب 8500 (قرار المالك 2026-11-07): ملفُّ إنشاء المعاينة نفسُه بوضع dev على شجرة البطاقة،
# فتمرّ حرّاسُ حسابات المعاينة كما تمرّ في التثبيت، بمشروعٍ ومنفذٍ وقاعدةٍ وredis منفصلة.
#   preview_slot.sh up <شجرة> <منفذ>   يقلعها ويهاجر ويبذر حسابات المعاينة
#   preview_slot.sh down <منفذ>        يوقفها؛ القاعدةُ صغيرةٌ وتبقى لرأسٍ تالٍ
set -eu

REPO="${SCHOOLOS_REPO:-D:/shschool_mvp}"
MAIN_PREVIEW="$REPO/.claude/worktrees/main-preview"
COMPOSE_FILE="$MAIN_PREVIEW/docker-compose.preview.yml"
TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
action="$1"

if [ "$action" = down ]; then
  docker compose -p "preview-slot-$2" down --remove-orphans
  exit 0
fi

tree="$2"
port="$3"
project="preview-slot-$port"
state="$(git -C "$MAIN_PREVIEW" rev-parse --absolute-git-dir)/preview-state"
live="$(cat "$state/slot" 2>/dev/null || printf a)"

source_db="$(cd "$MAIN_PREVIEW" && bash scripts/session-db.sh --name)"
gen="$(cat "$state/db_gen" 2>/dev/null || true)"
if [ -n "$gen" ] && [ "$gen" != 0 ]; then source_db="${source_db}_g$gen"; fi

cd "$tree"
db="$(bash scripts/session-db.sh --name)_preview"
SOURCE_DB="$source_db" SESSION_DB_NAME="$db" bash scripts/session-db.sh

export PREVIEW_DB="$db" PREVIEW_PORT="$port" PREVIEW_BIND=127.0.0.1 PREVIEW_ENV_FILE="$MAIN_PREVIEW/.env"
export PREVIEW_MODE=dev PREVIEW_SETTINGS=shschool.settings.development PREVIEW_DEBUG=True
export PREVIEW_REDIS_DB="$(( port % 10 + 10 ))"
export PREVIEW_SHA="$(git rev-parse --short=7 HEAD)"
export SCHOOLOS_IMAGE="$(docker inspect "schoolos-main-preview-$live-web-1" --format '{{.Config.Image}}')"
docker compose -p "$project" --project-directory "$tree" --env-file "$MAIN_PREVIEW/.env" -f "$COMPOSE_FILE" up -d web worker

code=000
for _ in $(seq 1 80); do
  code="$(curl -s -m 3 -o /dev/null -w '%{http_code}' "http://localhost:$port/health/" || true)"
  if [ "$code" = 200 ]; then break; fi
  sleep 3
done
if [ "$code" != 200 ]; then
  docker logs "$project-web-1" 2>&1 | tail -5
  exit 1
fi
# المهمّة المجدولة بلا طرفية: مقبضُ الدخل غير صالح فيسقط subprocess في الابن
PREVIEW_CONTAINER="$project-web-1" PYTHONUTF8=1 python "$TOOLS/preview_accounts.py" sync </dev/null
echo "slot $port ready"
