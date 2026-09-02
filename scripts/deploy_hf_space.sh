#!/usr/bin/env bash
# Hugging Face Space(Docker SDK) 배포.
#
# Space 저장소는 소스의 정본이 아니라 배포 산출물이다. GitHub 저장소에서
# 런타임에 필요한 것만 복사해 올린다 — 테스트·평가 하네스·합성 라벨은 뺀다.
#
# 사용법:
#   HF_TOKEN=hf_... bash scripts/deploy_hf_space.sh <user>/<space-name>
#
# 시크릿(DN_OPENAI_* 등)은 이 스크립트가 다루지 않는다. Space 설정 화면이나
# huggingface_hub.add_space_secret 으로 따로 넣는다 — 저장소에 남기지 않기 위해서다.
set -euo pipefail

REPO_ID="${1:?사용법: bash scripts/deploy_hf_space.sh <user>/<space-name>}"
: "${HF_TOKEN:?HF_TOKEN 환경변수가 필요합니다 (write 권한)}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

echo "  [STAGE] 배포 파일 수집 → $STAGE"
cp "$ROOT/Dockerfile" "$ROOT/pyproject.toml" "$STAGE/"
cp -R "$ROOT/src" "$ROOT/config" "$STAGE/"
mkdir -p "$STAGE/data/synthetic"
cp -R "$ROOT/data/synthetic/pdf" "$STAGE/data/synthetic/pdf"

# Space 카드용 README. 앞부분 YAML 프런트매터가 없으면 HF 가 Space 로 인식하지 않는다.
# app_port 는 Dockerfile 의 EXPOSE/CMD 와 같아야 한다.
cat > "$STAGE/README.md" <<'MD'
---
title: 채무회복 내비게이터
emoji: 🧭
colorFrom: green
colorTo: gray
sdk: docker
app_port: 8000
pinned: false
short_description: 저신용·다중채무자를 위한 근거 기반 AI 채무회복 실행 코파일럿
---

# 채무회복 내비게이터

2026 금융 AI Challenge 출품작. 신용정보조회서를 올리면 상환여력을 결정론적으로
계산하고, 검토 가능한 채무조정 제도 후보를 근거·미확인 조건과 함께 제시한다.

> **숫자는 확정, 제도는 후보.**
> 상환여력은 결정론적 계산 모듈이 확정 숫자로 산출한다.
> 제도 적합성은 판정하지 않고 근거·미확인 조건과 함께 검토 후보로만 제시한다.

**시작은 `/` 에서.** 세션 없이 화면 경로로 직접 들어가면 404 가 뜬다.

조회서가 없어도 두 가지 방법으로 체험할 수 있다 — 업로드 화면의
**"데모용 합성 문서 선택"**(실제 개인정보가 아닌 생성 문서 13종) 또는
**"문서 없이 직접 입력"**.

본 서비스는 금융·법률 자문, 신용평가 또는 공식 자격심사를 제공하지 않는다.
최종 신청 가능 여부와 조정 조건은 신용회복위원회, 법원 등 공식기관을 통해 확인해야 한다.

소스: https://github.com/EileenKwon/AI-Challenge
MD

echo "  [STAGE] Space 생성/업로드 → $REPO_ID"
python - "$REPO_ID" "$STAGE" <<'PY'
import sys
from huggingface_hub import HfApi
repo_id, stage = sys.argv[1], sys.argv[2]
api = HfApi()
api.create_repo(repo_id=repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
api.upload_folder(repo_id=repo_id, repo_type="space", folder_path=stage,
                  commit_message="deploy: 채무회복 내비게이터")
print(f"  [OK] https://huggingface.co/spaces/{repo_id}")
PY
