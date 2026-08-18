#!/usr/bin/env bash
# 데모 시나리오 스모크 테스트 — 합성 문서 업로드 → 요약서 PDF 다운로드.
#
# 사용법:
#   docker compose up -d --build
#   bash scripts/smoke.sh
#
# 컨테이너 없이 로컬에서 uvicorn 을 직접 띄워도 동작한다:
#   uvicorn dn.main:app --app-dir src &
#   bash scripts/smoke.sh
set -euo pipefail

BASE_URL="${SMOKE_BASE_URL:-http://localhost:8000}"
FIXTURE_PDF="${SMOKE_FIXTURE_PDF:-tests/fixtures/sample_text.pdf}"

_json_field() {
  python3 -c "import sys, json; print(json.load(sys.stdin)['$1'])"
}

echo "=== Smoke Test ==="

echo "  [STAGE] healthz"
curl -fsS "$BASE_URL/healthz" > /dev/null
echo "  [OK] healthz"

echo "  [STAGE] 세션 생성"
CREATE_RESPONSE=$(curl -fsS -X POST "$BASE_URL/api/session")
SESSION_ID=$(echo "$CREATE_RESPONSE" | _json_field session_id)
echo "  [OK] session_id=$SESSION_ID"

echo "  [STAGE] 동의"
curl -fsS -X POST "$BASE_URL/api/session/$SESSION_ID/consent" > /dev/null
echo "  [OK] consent"

echo "  [STAGE] 합성 문서 업로드"
if [ ! -f "$FIXTURE_PDF" ]; then
  echo "[ERR] 데모 PDF 가 없습니다: $FIXTURE_PDF"
  exit 1
fi
curl -fsS -X POST "$BASE_URL/api/session/$SESSION_ID/document" \
  -F "file=@${FIXTURE_PDF};type=application/pdf" > /dev/null
echo "  [OK] document uploaded"

echo "  [STAGE] 추출 확인"
curl -fsS -X POST "$BASE_URL/api/session/$SESSION_ID/confirm" > /dev/null
echo "  [OK] confirm"

echo "  [STAGE] 보완 입력"
curl -fsS -X POST "$BASE_URL/api/session/$SESSION_ID/supplement" \
  -H "Content-Type: application/json" \
  -d '{"monthly_net_income": 2500000, "essential_living_cost": 1450000, "income_proof_available": true}' \
  > /dev/null
echo "  [OK] supplement"

echo "  [STAGE] 분석"
curl -fsS -X POST "$BASE_URL/api/session/$SESSION_ID/analyze" > /dev/null
echo "  [OK] analyze"

echo "  [STAGE] 7일 계획"
curl -fsS -X POST "$BASE_URL/api/session/$SESSION_ID/plan" > /dev/null
echo "  [OK] plan"

echo "  [STAGE] 요약서 PDF 다운로드"
OUT_PDF="$(mktemp).pdf"
curl -fsS -X POST "$BASE_URL/api/session/$SESSION_ID/report" -o "$OUT_PDF"
if [ ! -s "$OUT_PDF" ]; then
  echo "[ERR] PDF 가 비어 있습니다"
  exit 1
fi
if ! head -c 4 "$OUT_PDF" | grep -q "%PDF"; then
  echo "[ERR] 다운로드한 파일이 PDF 형식이 아닙니다"
  exit 1
fi
PDF_SIZE=$(wc -c < "$OUT_PDF")
echo "  [OK] PDF 다운로드 성공 (${PDF_SIZE} bytes)"

echo "[DONE] 데모 시나리오 스모크 테스트 통과"
