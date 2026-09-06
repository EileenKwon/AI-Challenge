# 상담용 요약서 PDF 생성 — 성능 실측 (2026-09-06)

## 방법

`time.perf_counter()` 로 4단계(`preparing_data` · `rendering_html` ·
`rendering_pdf` · 파일쓰기)를 각각 측정하고, `POST /report` 시작부터 작업이
`ready` 가 될 때까지 전체 시간도 별도로 측정했다. 로그는 단계별 소요 시간만
남기고 PII·PDF 내용은 남기지 않는다(`report_timing` 로그 라인,
`src/dn/report/jobs.py`).

## Root cause

**WeasyPrint 의 PDF 폰트 서브셋 단계가 매 렌더링마다 4.5초 넘게 걸렸다.**
`cProfile` 로 `write_pdf()` 내부를 뜯어보면 전체 시간의 약 90% 가
`fontTools.subset` 의 `_fonttools_subset()` 한 곳에 몰려 있었다:

```
7.740s  write_pdf()
  7.629s  build_fonts_dictionary → clean → subset → _fonttools_subset
    4.244s  fontTools.ttLib.ttFont.save (CFF hint 제거·재컴파일)
    189,327 회 calcBounds() 호출
```

원인은 시스템에 설치된 "Noto Sans CJK KR"가 사실 JP/KR/SC/TC/HK 5개 지역
서체를 하나의 .ttc 파일(19.5MB, 통합 글자표 수만 자)에 묶어 둔 폰트라는
점이다. 보고서 1페이지는 실제로 글자 수십~수백 자만 쓰는데도, WeasyPrint 가
PDF에 폰트를 임베드하려고 서브셋을 계산할 때마다 이 거대한 글자표 전체를
훑어야 했다.

문서 텍스트 자체(Jinja 렌더링 등)는 무관했다 — `data`/`html` 단계는 항상
5ms 미만이었다.

## 조치

1. **폰트 사전 서브셋** (`src/dn/report/fonts.py`) — 컨테이너가 뜬 뒤 첫
   렌더링 때 한 번만, 현대 한글 음절 전체(U+AC00-D7A3, 조합 가능한 모든
   한글 음절을 빠짐없이 포함) + 라틴 + 통화기호·구두점만 잘라낸 폰트
   파일(약 1.9MB)을 만들어 디스크에 캐시한다. 이후 렌더링은 이 작은 폰트
   파일을 `@font-face` 로 직접 가리켜, 매번 다시 서브셋할 글자표 자체를
   작게 만든다. 이후 값은 항상 재사용된다.
2. **비동기 작업화** (`src/dn/report/jobs.py`) — `POST /report` 가 즉시
   202 를 돌려주고 실제 렌더링은 백그라운드 스레드에서 진행한다. 이벤트
   루프·요청 스레드가 렌더링 시간 동안 막히지 않는다(10번 항목 확인 완료 —
   `create_report` 는 원래도 `def` 였지만, 이제는 응답 자체가 렌더링을
   기다리지 않는다).
3. **세션 결과 캐싱** — `(session_id, options_hash, state_hash)` 로 이미
   만든 결과를 재사용해, 같은 옵션으로 다시 요청하거나 재다운로드할 때
   렌더링을 다시 하지 않는다.

## 확인한 것 (수정하지 않음 — 이미 문제 없었음)

- **LLM 재호출 없음** — `create_report`/`summary_pdf.render()` 어디에도
  LLM 호출이 없다. `s6_planned` 에서 이미 확정된 `analysis`(cashflow·rules·
  narrative·plan)를 그대로 포맷팅만 한다. `report_timing` 로그의 `llm` 값은
  항상 `0.0`이다.
- **외부 네트워크 의존성 없음** — `src/dn/report/templates/summary.html` 은
  이미 인라인 CSS만 쓰고, Tailwind CDN·Google Fonts·외부 이미지·원격 JS를
  전혀 불러오지 않는다.
- **중복 렌더링 없음** — `write_pdf()` 는 요청당 한 번만 호출된다
  (`tests/integration/test_report_jobs.py` 의 호출 횟수 카운트 테스트로 고정).

## Before / After (같은 `TestClient` 전체 경로로 측정, `POST /report` 시작 →
`ready` 까지)

| | 평균 | p50 | max |
|---|---|---|---|
| **Before**(폰트 서브셋 없음, 5회) | 6.96s | 6.75s | 8.15s |
| **After — warm**(캐시된 서브셋 폰트 사용, 5회, 서로 다른 세션) | 1.54s | 1.51s | 1.73s |
| **After — cold**(프로세스 최초 1회, 폰트 서브셋 생성 포함) | 7.29s | — | — |
| **After — 캐시 히트**(같은 세션·같은 옵션 재요청) | <0.05s | — | — |

경고: warm 수치도 여전히 ~1.5초로, 격리된 `write_pdf()` 자체 호출(약
0.4~0.9초, 로컬 측정)보다 크다 — `TestClient` 전체 스택(라우팅·의존성
주입·상태 저장/조회·0.01초 간격 폴링) 오버헤드가 더해진 값이다. 순수 렌더링
개선폭은 약 **10배**(4.5s → 0.4~0.5s), 사용자 체감(요청 시작→완료) 개선폭은
약 **4.5배**(6.96s → 1.54s)다.

## 재현 방법

```bash
source .venv/bin/activate
python3 - <<'EOF'
import time
from pathlib import Path
from fastapi.testclient import TestClient
from dn.main import create_app

client = TestClient(create_app())
# ... (세션 생성 → consent → 업로드 → confirm → supplement → analyze → plan)
r = client.post(f"/api/session/{sid}/report")
job_id = r.json()["job_id"]
# GET .../report/status 를 job이 ready/failed 될 때까지 폴링
EOF
```
