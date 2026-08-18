# 기여 가이드

이 프로젝트는 금융취약계층을 대상으로 하므로 속도보다 안전성과 검증 가능성을 우선한다. 기여 전에 `AGENTS.md`, `ARCHITECTURE.md`, `CODEX_TASKS.md`를 읽어야 한다.

## 작업 시작

```bash
git switch main
git pull --ff-only
git switch -c feat/<issue-number>-<short-topic>
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

`.env`, 실제 개인정보, 업로드 원문, API 키는 커밋하지 않는다. 테스트에는 합성 데이터만 사용한다.

## 브랜치와 커밋

- 브랜치: `feat/12-rule-engine`, `fix/31-pii-redaction`, `docs/8-api-guide`
- 커밋: `<task_id>: <한 줄 요약>` 형식을 사용한다.
- 하나의 PR은 하나의 Issue 또는 `CODEX_TASKS.md`의 하나의 태스크를 원칙으로 한다.
- 정책 수치나 출처는 추측하지 않고, 근거가 없으면 `TODO`와 `verified: false`로 남긴다.

## 품질 검사

```bash
pytest -q
ruff check src tests eval
ruff format --check src tests eval
```

변경한 행동에 대한 테스트를 같이 추가한다. LLM 호출은 스텁으로 대체하여 API 키 없이도 전체 테스트가 통과해야 한다.

## Pull Request

- PR 본문에 Issue를 `Closes #<number>`로 연결한다.
- 변경 이유, 테스트 결과, 보안·PII 영향, 남은 TODO를 적는다.
- 자신의 코드를 먼저 자체 리뷰한 뒤 팀원을 reviewer로 지정한다.
- `main`에 직접 push하지 않고 PR로 병합한다.

## Issue 선점

중복 작업을 막기 위해 Issue에 담당자를 지정하고, 변경 예정 파일과 완료 조건을 적은 후 시작한다.
