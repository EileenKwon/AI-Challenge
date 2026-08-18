# AGENTS.md — 채무회복 내비게이터 작업 규약

이 파일은 코딩 에이전트(Codex 등)가 이 저장소에서 작업할 때 **반드시 준수해야 하는 규약**이다.
설계 근거는 `ARCHITECTURE.md`, 서비스 요구사항은 `docs/기획서.md`에 있다.
두 문서와 충돌하는 코드는 작성하지 않는다.

---

## 0. 이 프로젝트의 성격

금융취약계층이 사용하는 서비스다. **틀린 숫자 하나가 실제 금전적 피해로 이어질 수 있다.**
따라서 "동작하는 코드"보다 "틀렸을 때 조용히 넘어가지 않는 코드"를 우선한다.
불확실한 값은 추정하지 말고 `None`으로 두고 화면에 "확인되지 않음"으로 표시한다.

---

## 1. 절대 규칙 (위반 시 해당 작업 무효)

1. **금액에 `float`를 쓰지 않는다.** `decimal.Decimal`, 원 단위 정수. 표시 단계에서만 포맷팅한다.
2. **결측값을 0이나 평균으로 대체하지 않는다.** `value or 0` 패턴 금지. `None`을 유지하고 `UNKNOWN`으로 전파한다.
3. **LLM 응답에서 나온 값을 금액 계산이나 제도 판정에 직접 사용하지 않는다.** LLM은 문서 추출값과 설명 문장만 만든다.
4. **`UNKNOWN`을 `NOT_MET`으로 취급하지 않는다.** 조건 평가는 항상 3-state(MET / NOT_MET / UNKNOWN)다.
5. **제도 조건을 파이썬 코드에 작성하지 않는다.** 전부 `config/policy_cards/**.yaml`에 둔다.
6. **조건 평가에 `eval()` / `exec()`를 쓰지 않는다.** 선언형 연산자만 사용한다.
7. **PII와 문서 원문을 로그에 남기지 않는다.** 마스킹 후 기록한다.
8. **`verified: false` 정책 카드로 사용자 결과를 생성하지 않는다.**
9. **경로·임계치를 하드코딩하지 않는다.** `config/config.yaml`에서 읽는다.
10. **`src/dn/cashflow/`와 `src/dn/rules/`는 순수 함수 모듈이다.** LLM 클라이언트, DB, 파일 I/O, 난수, 현재시각을 참조하지 않는다. (현재시각이 필요하면 인자로 받는다.)

---

## 2. 구역별 컨벤션

### 2.1 `src/dn/**` — 웹서비스 본체

```python
import logging
logger = logging.getLogger(__name__)

logger.info("extraction_completed", extra={"session_id": sid, "field_count": n})
```

- 표준 `logging` 사용. PII는 기록 전 `safety.audit.redact()`를 통과시킨다.
- 모든 공개 함수에 타입 힌트와 docstring(한국어, 1~3줄).
- 예외는 `domain/errors.py`의 도메인 예외로 래핑한다. bare `except:` 금지.
- 경로는 `settings.paths.*`로 접근한다.

### 2.2 `eval/**`, `tools/**` — 평가·데이터 생성 스크립트

```python
SEED = 42
rng = np.random.default_rng(SEED)

print("=== E1 Extraction F1 ===")
print(f"  [STAGE] loading labels from {label_dir}")
print(f"  matched: {n:,}")
print(f"RESULT_PATHS: {csv_path}, {md_path}")
print(f"[DONE] {time.time()-t0:.1f}s")
```

- `logging` 대신 `print`를 사용한다. (이 구역만 해당)
- 상단에 파일 헤더 docstring으로 **전제 파일**과 **출력 파일**을 명시한다.
- 전제 파일이 없으면 `print(f"[ERR] {reason}"); sys.exit(1)` — 조용히 계속 진행하지 않는다.
- 경로는 `eval/config.yaml`에서 읽는다.
- 출력 디렉토리는 `rdir.mkdir(parents=True, exist_ok=True)`로 보장한다.
- Markdown 리포트를 함께 생성한다: `df.to_markdown(index=False, floatfmt=".4f")`
- 나눗셈은 `numerator / np.maximum(denominator, 1)` 형태로 분모 0을 방어한다.
- 비율은 0.0~1.0으로 다룬다. 퍼센트 변환은 표시 단계에서만 한다.

### 2.3 파일 헤더 예시 (`eval/`, `tools/`)

```python
"""
E1 — 문서 추출 F1 측정

전제:
  data/synthetic/pdf/*.pdf
  data/synthetic/labels/*.json
출력:
  results/e1_extraction_f1.csv
  reports/e1_extraction_f1.md
"""
```

---

## 3. 작업 절차

각 태스크는 `CODEX_TASKS.md`에 정의되어 있다. 태스크를 수행할 때:

1. **전제 확인** — 태스크의 "전제" 항목에 적힌 파일이 실제로 존재하는지 먼저 확인한다. 없으면 작업을 중단하고 보고한다.
2. **계약 우선** — `src/dn/domain/models.py`의 타입을 먼저 읽고, 그 타입에 맞춰 구현한다. 필요하면 모델을 먼저 확장하고 이유를 커밋 메시지에 남긴다.
3. **테스트 동반** — 태스크의 "완료 조건"에 적힌 테스트를 같은 커밋에 포함한다. 테스트 없는 구현은 미완료로 간주한다.
4. **범위 준수** — 태스크에 명시되지 않은 파일을 수정하지 않는다. 필요하다고 판단되면 수정하지 말고 먼저 보고한다.
5. **정책 데이터 금지** — 제도 조건의 구체적 수치(연체일수 외)를 임의로 만들어 채우지 않는다. 근거가 없으면 `value: TODO`와 `verified: false`로 남긴다.

---

## 4. 커밋

```
<task_id>: <한 줄 요약>

- 변경 요약
- 추가된 테스트
- 남긴 TODO (있으면)
```

예: `T08: 결정론적 현금흐름 계산 모듈 구현`

---

## 5. 하지 말아야 할 것

- 기획서에 없는 기능을 추가하지 않는다. 특히 신용점수 예측, 상품 추천, 감면액 계산은 **명시적 제외 항목**이다(기획서 5.3).
- 사용자에게 "신청 가능합니다", "가장 유리합니다", "승인됩니다" 같은 확정 표현을 생성하지 않는다.
- 의도적 연체, 임의 상환 중단, 재산 은닉을 안내하는 문구를 어떤 맥락에서도 작성하지 않는다.
- 실제 개인정보를 테스트 데이터로 사용하지 않는다. 전부 합성 데이터다.
- 정책 카드의 `source.url`을 추측해서 채우지 않는다. 확인되지 않으면 `TODO`로 둔다.

---

## 6. 개발 환경

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env        # ANTHROPIC_API_KEY 설정

uvicorn dn.main:app --reload --app-dir src
pytest -q
ruff check src eval tools && ruff format --check src eval tools
```

LLM API 키가 없는 환경에서도 `pytest`가 전부 통과해야 한다. LLM 호출은 테스트에서 스텁으로 대체한다.
