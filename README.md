# 채무회복 내비게이터

저신용·다중채무자를 위한 근거 기반 AI 채무회복 실행 코파일럿.

## 원칙

> **숫자는 확정, 제도는 후보.**
> 상환여력은 결정론적 계산 모듈이 확정 숫자로 산출한다.
> 제도 적합성은 판정하지 않고 근거·미확인 조건과 함께 검토 후보로만 제시한다.

## 시작하기

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # ANTHROPIC_API_KEY 설정
uvicorn dn.main:app --reload --app-dir src
```

API 서버가 실행되면 `http://127.0.0.1:8000/docs`에서 OpenAPI 문서를 확인할 수 있다.

## 현재 구현 범위

- PDF 업로드, 텍스트 추출, PII 마스킹과 프롬프트 인젝션 감지
- LLM 기반 구조화 추출과 결과 검증
- 결측값·충돌 탐지 및 보완 질문 생성
- 결정론적 현금흐름과 소득 감소 시나리오 계산
- YAML 정책 카드 로더와 3-state 조건 평가

상세한 구현 순서와 남은 작업은 [`CODEX_TASKS.md`](CODEX_TASKS.md)를 기준으로 관리한다.

## 팀 개발 흐름

1. Issue에서 작업 범위와 완료 조건을 확정한다.
2. `main`을 기준으로 `feat/<issue>-<topic>` 또는 `fix/<issue>-<topic>` 브랜치를 만든다.
3. 코드와 테스트를 같이 작성하고 로컬 품질 검사를 통과시킨다.
4. PR 템플릿을 채워 리뷰를 요청하고, CI와 리뷰가 완료된 뒤 병합한다.

```bash
pytest -q
ruff check src tests eval tools
ruff format --check src tests eval tools
```

세부 규칙은 [`CONTRIBUTING.md`](CONTRIBUTING.md)와 [`AGENTS.md`](AGENTS.md)를 따른다.

## 문서

| 파일 | 내용 |
|---|---|
| `ARCHITECTURE.md` | 시스템 아키텍처, 불변식, 모듈 설계 |
| `AGENTS.md` | 코딩 에이전트 작업 규약 (절대 규칙 10개) |
| `CODEX_TASKS.md` | T00~T23 순차 구현 지시서 |
| `docs/기획서.md` | 서비스 기획서 (원본) |
| `CONTRIBUTING.md` | 브랜치, 커밋, PR, 테스트 규칙 |

## 배포 전 체크리스트

- [ ] `config/config.yaml: rules.allow_unverified_cards` 를 `false` 로 변경
- [ ] 모든 정책 카드의 `verified: true` 및 `source.url` 기입 완료
- [ ] `eval/E1~E6` 전량 실행, `reports/metrics_summary.md` 생성
- [ ] `data/redteam/attacks.yaml` 전량 통과
- [ ] 업로드 원본 TTL 삭제 동작 확인

## 유의사항

본 서비스는 금융·법률 자문, 신용평가 또는 공식 자격심사를 제공하지 않는다.
최종 신청 가능 여부와 조정 조건은 신용회복위원회, 법원 등 공식기관을 통해 확인해야 한다.
