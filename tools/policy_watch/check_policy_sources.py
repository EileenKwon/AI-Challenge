"""정책 카드 출처 페이지 변경 감지 — 월 1회 실행, 바뀌었으면 GitHub 이슈로 알린다.

`config/policy_cards/**.yaml` 각 카드의 `source.url` 을 가져와 이전에 저장해 둔
스냅샷(해시)과 비교한다. 페이지 내용이 달라졌으면 "출처가 바뀐 것 같으니
확인하라"고만 알리고, 카드 YAML 은 이 스크립트가 절대 고치지 않는다 — 연체일수
경계·소득 요건 같은 실제 조건값 해석은 반드시 사람이 확인해야 한다
(AGENTS.md 절대 규칙: 정책 카드 자동 반영 금지, source.url 을 추측해 채우지 않음).

알림을 보낸 뒤에는 스냅샷을 최신 상태로 갱신한다 — "같은 변경을 매달 계속
재촉"하는 게 아니라 "페이지가 실제로 바뀔 때마다 한 번씩 알림"이 목적이다.
사람이 아직 그 변경을 검토·반영하지 않았어도, 페이지 자체가 그 뒤로 또
바뀌지 않는 한 다음 달에 같은 알림을 반복하지 않는다.

실행:
    python tools/policy_watch/check_policy_sources.py

변경이 있으면 이 스크립트가 실행된 디렉터리에 `policy_change_report.md` 를
쓴다(GitHub Actions 워크플로가 그 파일로 이슈를 만든다). 변경이 없으면
그 파일을 만들지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from dn.rules.policy_card import load_all_cards  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
_SNAPSHOT_PATH = _ROOT / "config" / "policy_cards" / "_source_snapshots.json"
_REPORT_PATH = _ROOT / "policy_change_report.md"

_TIMEOUT_S = 20.0
_USER_AGENT = "debt-recovery-navigator-policy-watch/1.0 (+https://github.com/)"


def _load_snapshots() -> dict[str, dict[str, str]]:
    if not _SNAPSHOT_PATH.exists():
        return {}
    return json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))


def _save_snapshots(snapshots: dict[str, dict[str, str]]) -> None:
    _SNAPSHOT_PATH.write_text(
        json.dumps(snapshots, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


_TAG_STRIP_RE = re.compile(r"(?is)<(script|style|noscript).*?</\1>")
_COMMENT_STRIP_RE = re.compile(r"(?s)<!--.*?-->")
_ANY_TAG_RE = re.compile(r"(?s)<[^>]+>")


def _visible_text(html: str) -> str:
    """HTML 에서 사람이 실제로 읽는 텍스트만 남긴다.

    실측(2026-09-06): 정부·공공기관 페이지 다수가 매 요청마다 CSRF 토큰·세션
    값 등을 hidden input/meta/script 태그에 새로 심어 응답한다 — 원문 HTML을
    그대로 해싱하면 실제 내용이 전혀 안 바뀌었는데도 매번 "변경"으로 오탐된다
    (신용회복위원회 3개 카드에서 재현 확인). 태그를 걷어내고 방문자가 보는
    텍스트만 비교하면 이 노이즈가 사라지고, 실제 문구 변경만 잡힌다.
    """
    html = _TAG_STRIP_RE.sub(" ", html)
    html = _COMMENT_STRIP_RE.sub(" ", html)
    text = _ANY_TAG_RE.sub(" ", html)
    return " ".join(text.split())


def _fetch_hash(url: str) -> str | None:
    """페이지의 가시 텍스트 sha256. 네트워크 오류·4xx/5xx 면 `None`(판단 보류, 경고만)."""
    try:
        response = httpx.get(
            url, timeout=_TIMEOUT_S, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"::warning::출처 확인 실패({url}): {exc}", file=sys.stderr)
        return None
    return hashlib.sha256(_visible_text(response.text).encode("utf-8")).hexdigest()


def main() -> int:
    cards = load_all_cards()
    snapshots = _load_snapshots()
    today = date.today().isoformat()

    changed: list[dict[str, str]] = []
    for card in cards:
        url = card.source.get("url")
        if not url:
            continue
        new_hash = _fetch_hash(url)
        if new_hash is None:
            continue  # 이번 실행에서 그 카드는 판단하지 않는다 — 오탐(사이트 일시 장애) 방지

        previous = snapshots.get(card.id)
        if previous is not None and previous.get("hash") != new_hash:
            changed.append(
                {
                    "id": card.id,
                    "name": card.name,
                    "agency": card.agency,
                    "url": url,
                    "last_checked_at": previous.get("checked_at", "기록 없음"),
                }
            )
        snapshots[card.id] = {"hash": new_hash, "url": url, "checked_at": today}

    _save_snapshots(snapshots)

    if changed:
        lines = [
            f"정책 카드 출처 페이지 변경 감지 ({today})",
            "",
            "아래 카드의 출처 페이지 내용이 지난 확인 시점과 달라졌습니다.",
            "실제 제도 조건이 바뀌었는지 사람이 직접 열어서 확인하고, 바뀌었다면",
            "`config/policy_cards/` 의 해당 YAML(조건값·`verified`·`changelog`)을",
            "갱신해 주세요. 이 스크립트는 카드 내용을 자동으로 고치지 않습니다.",
            "",
        ]
        for item in changed:
            lines.append(f"- **{item['name']}** (`{item['id']}`, {item['agency']})")
            lines.append(f"  - 출처: {item['url']}")
            lines.append(f"  - 마지막 확인(변경 전): {item['last_checked_at']}")
        _REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"변경 감지: {len(changed)}건 — {_REPORT_PATH} 작성함")
    else:
        print("변경 없음")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
