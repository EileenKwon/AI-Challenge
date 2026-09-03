#!/usr/bin/env bash
# Render 배포 트리거.
#
# 왜 필요한가: 이 서비스는 공개 저장소 URL 로 만들어졌고 Render 의 GitHub App 이
# 저장소에 설치돼 있지 않다. 그래서 `autoDeploy: yes` 설정에도 불구하고 **main 에
# 푸시해도 배포가 자동으로 걸리지 않는다**(2026-09-04 실측 — 머지 후에도 이전
# 커밋이 계속 live 였다). 근본 해결은 저장소 소유자가 Render GitHub App 을
# 설치하는 것이고, 그때까지는 이 스크립트로 수동 배포한다.
#
# 사용법:
#   RENDER_API_KEY=rnd_... bash scripts/deploy_render.sh
#   RENDER_API_KEY=rnd_... RENDER_SERVICE_ID=srv-... bash scripts/deploy_render.sh
set -euo pipefail

: "${RENDER_API_KEY:?RENDER_API_KEY 환경변수가 필요합니다}"
SERVICE_ID="${RENDER_SERVICE_ID:-srv-dac1eom7bikc73ejnhng}"
API="https://api.render.com/v1/services/$SERVICE_ID"

echo "  [STAGE] 배포 요청 → $SERVICE_ID"
curl -fsS -X POST "$API/deploys" \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"clearCache":"do_not_clear"}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('  [OK] deploy',d.get('id'),'commit',(d.get('commit') or {}).get('id','')[:7])"

echo "  [STAGE] 완료 대기"
prev=""
for _ in $(seq 1 90); do
  status=$(curl -fsS "$API/deploys?limit=1" \
    -H "Authorization: Bearer $RENDER_API_KEY" -H "Accept: application/json" \
    | python3 -c "import sys,json;d=json.load(sys.stdin)[0]['deploy'];print(d['status'],(d.get('commit') or {}).get('id','')[:7])")
  [ "$status" != "$prev" ] && { echo "    $status"; prev="$status"; }
  case "$status" in
    live*) echo "  [OK] 배포 완료"; exit 0 ;;
    build_failed*|update_failed*|canceled*) echo "  [ERR] 배포 실패: $status"; exit 1 ;;
  esac
  sleep 20
done
echo "  [ERR] 시간 초과 — Render 대시보드에서 확인하세요"; exit 1
