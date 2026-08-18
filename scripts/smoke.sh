#!/usr/bin/env bash
# 데모 시나리오 스모크 테스트 (T23에서 완성)
set -euo pipefail
echo "=== Smoke Test ==="
echo "  [STAGE] healthz"
curl -fsS http://localhost:8000/healthz > /dev/null
echo "[DONE] healthz ok"
