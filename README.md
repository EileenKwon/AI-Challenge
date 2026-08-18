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

## 문서

| 파일 | 내용 |
|---|---|
| `ARCHITECTURE.md` | 시스템 아키텍처, 불변식, 모듈 설계 |
| `AGENTS.md` | 코딩 에이전트 작업 규약 (절대 규칙 10개) |
| `CODEX_TASKS.md` | T00~T23 순차 구현 지시서 |
| `docs/기획서.md` | 서비스 기획서 (원본) |

## 배포 전 체크리스트

- [ ] `config/config.yaml: rules.allow_unverified_cards` 를 `false` 로 변경
- [ ] 모든 정책 카드의 `verified: true` 및 `source.url` 기입 완료
- [ ] `eval/E1~E6` 전량 실행, `reports/metrics_summary.md` 생성
- [ ] `data/redteam/attacks.yaml` 전량 통과
- [ ] 업로드 원본 TTL 삭제 동작 확인

## 유의사항

본 서비스는 금융·법률 자문, 신용평가 또는 공식 자격심사를 제공하지 않는다.
최종 신청 가능 여부와 조정 조건은 신용회복위원회, 법원 등 공식기관을 통해 확인해야 한다.
