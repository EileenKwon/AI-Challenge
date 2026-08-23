# 채무회복 내비게이터

저신용·다중채무자를 위한 근거 기반 AI 채무회복 실행 코파일럿.
**2026 금융 AI Challenge** (제출 마감 2026-09-07) 출품작.

## 원칙

> **숫자는 확정, 제도는 후보.**
> 상환여력은 결정론적 계산 모듈이 확정 숫자로 산출한다.
> 제도 적합성은 판정하지 않고 근거·미확인 조건과 함께 검토 후보로만 제시한다.

## 현재 진행 상황 (2026-08-21 기준)

**`CODEX_TASKS.md`의 T00~T23 전체 23개 태스크 구현 완료.** 테스트 328개
전량 통과(`pytest -q`), `ruff check` / `ruff format --check` 클린.

| 항목 | 상태 |
|---|---|
| 태스크 구현 (T00~T23) | ✅ 23/23 완료 |
| 단위·통합 테스트 | ✅ 323 passed |
| 린트/포맷 | ✅ `ruff check`, `ruff format --check` 클린 |
| 평가 하네스 (E1~E6) | ✅ 실행 완료 · 결과를 `docs/평가결과.md` 에 고정. E3 누락률 0.10 → **0.00**(정렬 결함 수정) |
| Docker 빌드 검증 | ⚠️ 샌드박스에 Docker 권한 없어 미검증 (Dockerfile/compose는 작성 완료, 로컬 uvicorn 기준 스모크 테스트로 대체 검증) |
| 브라우저 수동 워크스루 (T19) | ✅ 화면 7종 전환 버그 수정, API 흐름과 동일한 순서로 curl 검증 완료 — 단, 실기기 375px 육안 검증은 아직 (남은 한계는 아래 참고) |
| 정책 카드 공식 출처 검증 | 🟡 **6개 중 5개 `verified: true`** (2026-08-21 대조 완료). 개인워크아웃 1개만 미검증 — 총채무액 한도가 공식 출처 간 상이하여 `unresolved` 에 보존하고 인코딩 보류 |
| 실제 LLM(E1/E2 추출 정확도) 평가 | ⚠️ `ANTHROPIC_API_KEY` 미설정 상태라 `StubClient` 기반 `[STUB_MODE]` 결과만 존재 |

배포 전 남은 작업은 아래 [배포 전 체크리스트](#배포-전-체크리스트)를 따른다.

## 전체 로드맵 (`CODEX_TASKS.md` T00~T23)

| # | 태스크 | 상태 |
|---|---|---|
| T00 | 프로젝트 부트스트랩 | ✅ |
| T01 | 도메인 모델 | ✅ |
| T02 | 세션 저장소와 상태머신 | ✅ |
| T03 | 문서 인제스트 | ✅ |
| T04 | PII 마스킹 · 인젝션 스캐너 | ✅ |
| T05 | LLM 클라이언트 | ✅ |
| T06 | 추출기 · 정규화 · 검증 | ✅ |
| T07 | 누락 · 모순 탐지 | ✅ |
| T08 | 현금흐름 계산 모듈 ★최우선 정확도 | ✅ |
| T09 | 소득 감소 시나리오 분석 | ✅ |
| T10 | 정책 카드 스키마와 로더 | ✅ |
| T11 | 3-state 조건 평가기 | ✅ |
| T12 | 규칙 엔진 | ✅ |
| T13 | 트리아지 | ✅ |
| T14 | 설명 생성기와 숫자 그라운딩 검증 ★환각 방어선 | ✅ |
| T15 | 안전 필터 | ✅ |
| T16 | 7일 행동계획 | ✅ |
| T17 | 상담용 요약서 PDF | ✅ |
| T18 | API 라우터와 오케스트레이터 | ✅ |
| T19 | 화면 7종 | ✅ |
| T20 | 합성 신용정보조회서 생성기 | ✅ |
| T21 | 평가 하네스 E1~E6 | ✅ |
| T22 | 설명가능성 번들과 감사 로그 | ✅ |
| T23 | 배포와 스모크 테스트 | ✅ |

## 폴더 구조

```
debt-recovery-navigator/
├── src/dn/                     # 애플리케이션 본체
│   ├── domain/                 #   Tracked[T] 도메인 모델, Money/Ratio 타입
│   ├── ingest/                 #   PDF 업로드·텍스트 추출
│   ├── llm/                    #   Anthropic 클라이언트 (API 키 없으면 StubClient 폴백)
│   ├── extraction/              #   LLM 구조화 추출·정규화·숫자 그라운딩 검증
│   ├── reconcile/               #   결측값·충돌 탐지, 보완 질문 생성
│   ├── cashflow/                 #   결정론적 현금흐름 계산 (순수 함수, float 금지)
│   ├── rules/                    #   YAML 정책 카드 로더 + 3-state 조건 평가기
│   ├── planning/                 #   7일 행동계획 생성
│   ├── narrative/                #   설명 생성기 (LLM 서술 + 그라운딩 검증)
│   ├── safety/                   #   입력/출력 안전 필터 (탈옥·리스크 조언·낙인 탐지)
│   ├── report/                   #   상담용 요약서 PDF (WeasyPrint)
│   │   └── templates/
│   ├── pipeline/                 #   9단계 analyze() 오케스트레이터
│   ├── api/                      #   세션·문서·분석 라우터
│   ├── web/                      #   Jinja2 + HTMX 화면 7종
│   │   ├── templates/
│   │   └── static/
│   ├── storage/                  #   세션 저장소, 상태머신
│   └── main.py                   #   FastAPI 앱 팩토리
├── config/
│   ├── config.yaml                #   설정 (allow_unverified_cards 등)
│   ├── policy_cards/v2026-08-13/  #   YAML 정책 카드 6개 (전부 verified: false)
│   └── safety/                    #   인젝션 패턴, 금지 문구 YAML
├── data/
│   ├── cases/                     #   테스트용 시나리오 케이스
│   ├── redteam/                   #   레드팀 공격 샘플 (attacks.yaml)
│   └── synthetic/                 #   합성 신용정보조회서 PDF + 라벨
├── eval/                          #   평가 하네스 E1~E6 + report_builder
├── tools/synth/                   #   합성 데이터 생성 스크립트
├── tests/
│   ├── unit/ integration/ golden/ fixtures/
├── reports/                       #   metrics_summary.md 등 평가 결과 산출물
├── scripts/smoke.sh               #   데모 시나리오 curl 스모크 테스트
├── Dockerfile, docker-compose.yml #   배포 아티팩트 (빌드 미검증, §진행상황 참고)
├── ARCHITECTURE.md                #   시스템 아키텍처, 불변식, 모듈 설계
├── AGENTS.md                      #   코딩 에이전트 작업 규약 (절대 규칙 10개)
├── CODEX_TASKS.md                 #   T00~T23 순차 구현 지시서
└── docs/기획서.md                  #   서비스 기획서 (원본)
```

## 시작하기

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # ANTHROPIC_API_KEY 설정 (없어도 StubClient로 동작함 — 아래 참고)
uvicorn dn.main:app --reload --app-dir src
```

API 서버가 실행되면 `http://127.0.0.1:8000/docs`에서 OpenAPI 문서를 확인할 수 있다.

**브라우저로 화면을 보려면** 루트 경로(`http://127.0.0.1:8000/`)에 접속한다.
랜딩 페이지에서 "새 세션 시작하기"를 누르면 세션이 만들어지며 소개·동의
화면(`/web/session/{session_id}/intro`)으로 이동한다. (세션 없이 화면
경로로 직접 들어가면 `404 Not Found`가 뜬다 — 반드시 `/`부터 시작한다.)

### ANTHROPIC_API_KEY 없이 개발하기

`ANTHROPIC_API_KEY`가 설정되지 않으면 `get_llm_client()`가 자동으로
`StubClient`로 폴백하고 `dev_mode`가 켜진다 (`src/dn/llm/client.py`). API
자체는 키 없이도 정상 동작하며(`eval/E1`·`E2`만 `[STUB_MODE]` 자리표시자
결과), `scripts/smoke.sh`·`tests/integration/test_smoke_flow.py`가 API를
직접 순서대로 호출하는 흐름은 키 없이도 끝까지(PDF 다운로드까지) 통과한다.

**브라우저 클릭만으로 화면 7종을 끝까지 진행할 수 있다.** 각 화면 폼에 `fetch`
기반 스크립트(`_layout.html`의 `dnPost`/`dnShowError`)를 붙여 API를 호출한 뒤
다음 화면으로 이동하도록 고쳤고, 보완입력(04) 화면은 폼 필드를
`SupplementRequest` 스키마(채무별 금리·월상환액, 소득/생활비 질문, 조건부
질문)에 맞게 변환해서 보내도록 다시 짰다. 분석(`/analyze`)은 보완입력
직후, 계획(`/plan`)은 경로(06) 화면의 버튼 클릭 시 자동으로 호출된다.

> ⚠️ 남은 알려진 제약
> - 업로드(02) 화면의 "데모용 합성 문서 선택"·"문서 없이 직접 입력"은 대응하는
>   API가 아직 없어 안내 메시지만 표시한다 — PDF/이미지 업로드만 동작한다.
> - 보완입력(04)의 "최근 6개월 이내 신규채무 여부"(`Q5_RECENT_DEBT`) 질문은
>   화면에는 남아 있지만 저장할 도메인 필드가 아직 없어 전송되지 않는다.
> - 375px 등 실기기 화면에서의 육안 검증은 아직 하지 않았다 — 위 내용은
>   curl로 API 호출 순서를 실제 JS와 동일하게 재현해 검증한 것이다.

## 팀 개발 흐름

1. Issue에서 작업 범위와 완료 조건을 확정한다.
2. `main`을 기준으로 `feat/<issue>-<topic>` 또는 `fix/<issue>-<topic>` 브랜치를 만든다.
3. 코드와 테스트를 같이 작성하고 로컬 품질 검사를 통과시킨다.
4. PR 템플릿을 채워 리뷰를 요청하고, CI와 리뷰가 완료된 뒤 병합한다.

```bash
pytest -q
ruff check src tests eval
ruff format --check src tests eval
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
| `reports/metrics_summary.md` | E1~E6 평가 결과 (기획서 14.3 지표 10개) |

## 제출물

| 항목 | 파일 | 상태 |
|---|---|---|
| 기획서 | `docs/기획서.md` | ✅ |
| **기능명세서** | `docs/기능명세서.md` | ✅ (2026-08-23 작성) |
| 평가 결과 | `docs/평가결과.md` | ✅ |
| 배포 URL | — | ❌ **미배포** |

## 배포 전 체크리스트

- [ ] `config/config.yaml: rules.allow_unverified_cards` 를 `false` 로 변경 — 개인워크아웃 한도 확인 후
- [x] 정책 카드 `verified: true` 및 `source.url` 기입 — **6개 중 5개 완료(2026-08-21)**. 개인워크아웃 1개는 총채무액 한도 출처 충돌로 `unresolved` 보존
- [ ] 실제 `ANTHROPIC_API_KEY`로 `eval/E1~E6` 재실행, `reports/metrics_summary.md` STUB_MODE 라벨 해소
- [ ] `data/redteam/attacks.yaml` 전량 통과
- [x] 업로드 원본 TTL 삭제 동작 확인 — **TTL 스위퍼를 앱 lifespan 에 배선(2026-08-23)**. 이전에는 정의만 되어 있고 호출부가 없었다
- [ ] Docker 빌드/`docker compose up` 실제 환경에서 검증 (현재 샌드박스 권한 문제로 미검증)
- [ ] T19 화면 7종 실제 브라우저(375px 포함)로 수동 워크스루
- [x] 화면 03 확인 상태 전송 — **채무가 1건이라도 있으면 `/confirm` 이 409 로 막히던 문제 수정(2026-08-23)**. 그동안은 StubClient 가 채무 0건을 반환해 우연히 통과하고 있었다

## 유의사항

본 서비스는 금융·법률 자문, 신용평가 또는 공식 자격심사를 제공하지 않는다.
최종 신청 가능 여부와 조정 조건은 신용회복위원회, 법원 등 공식기관을 통해 확인해야 한다.
