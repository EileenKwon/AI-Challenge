"""T19 — 화면 7종 렌더링 테스트.

이 테스트는 Jinja2 템플릿이 실제 세션 데이터로 예외 없이 렌더링되고 화면별
필수 요소가 HTML에 포함되는지까지만 검증한다. "모바일 뷰포트(375px)에서
가로 스크롤 없음"과 "수동 워크스루"는 실제 브라우저 렌더링 확인이 필요한데
이 환경에는 브라우저가 없어 이 테스트로는 검증하지 못한다 — CLAUDE 확인 필요.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from dn.api.deps import get_session_store
from dn.domain.enums import FieldSource, PathStatus, ProductType, SessionStage
from dn.domain.models import (
    ActionItem,
    ActionPlan,
    AnalysisResult,
    CashflowResult,
    Debt,
    ExtractionResult,
    GapReport,
    HouseholdProfile,
    IncomeProfile,
    Narrative,
    NarrativeSection,
    PathCandidate,
    PolicyRef,
    RuleEngineResult,
    ScenarioResult,
    SessionState,
    SituationFlags,
)
from dn.domain.provenance import Tracked
from dn.main import create_app
from dn.settings import get_settings


def _known(value):
    return Tracked(value=value, source=FieldSource.DOCUMENT)


def _debts():
    return (
        Debt(
            debt_id="d0",
            creditor=_known("A금융"),
            product_type=_known(ProductType.CREDIT_LOAN),
            balance=_known(Decimal("25000000")),
            overdue_days=_known(42),
            is_secured=_known(False),
            monthly_payment=_known(Decimal("620000")),
        ),
        Debt(
            debt_id="d1",
            creditor=_known("B카드"),
            product_type=_known(ProductType.CARD_LOAN),
            balance=_known(Decimal("14000000")),
            overdue_days=_known(0),
            is_secured=_known(False),
            monthly_payment=_known(Decimal("380000")),
        ),
    )


def _full_state(session_id: str) -> SessionState:
    now = datetime(2026, 8, 18)
    extraction = ExtractionResult(debts=_debts())
    cashflow = CashflowResult(
        total_debt=Decimal("39000000"),
        monthly_total_payment=Decimal("1000000"),
        monthly_available=Decimal("800000"),
        monthly_shortfall=Decimal("200000"),
        dti_ratio=Decimal("0.4"),
        max_overdue_days=42,
    )
    paths = (
        PathCandidate(
            path_id="pre_debt_adjustment",
            name="사전채무조정",
            priority=2,
            agency="신용회복위원회",
            status=PathStatus.NEEDS_INFO,
            consult_questions=("예상 납입기간은?",),
            policy_ref=PolicyRef(
                card_id="pre_debt_adjustment",
                card_version="2026-08-13.1",
                title="사전채무조정",
                policy_base_date=date(2026, 8, 13),
                verified=False,
            ),
        ),
    )
    plan = ActionPlan(
        items=(ActionItem(timing="today", order=1, text="추출된 채무 목록과 연체일수 확인"),)
    )
    narrative = Narrative(
        sections=(
            NarrativeSection(
                section="cashflow", text="매달 20만 원이 부족합니다.", generated_by_llm=False
            ),
        )
    )
    scenario = ScenarioResult(
        scenario_id="income_drop_20",
        label="소득이 20% 줄어든다면",
        before=cashflow,
        after=cashflow.model_copy(update={"monthly_shortfall": Decimal("600000")}),
    )
    analysis = AnalysisResult(
        session_id=session_id,
        analyzed_at=now,
        extraction=extraction,
        income=IncomeProfile(monthly_net_income=_known(Decimal("2000000"))),
        household=HouseholdProfile(essential_living_cost=_known(Decimal("1200000"))),
        flags=SituationFlags(),
        cashflow=cashflow,
        rules=RuleEngineResult(paths=paths, policy_base_date=date(2026, 8, 13)),
        narrative=narrative,
        plan=plan,
        gaps=GapReport(),
        scenario=scenario,
    )
    return SessionState(
        session_id=session_id,
        stage=SessionStage.S7_REPORTED,
        created_at=now,
        updated_at=now,
        extraction=extraction,
        income=IncomeProfile(monthly_net_income=_known(Decimal("2000000"))),
        household=HouseholdProfile(essential_living_cost=_known(Decimal("1200000"))),
        flags=SituationFlags(),
        analysis=analysis,
    )


def _client_with_session() -> tuple[TestClient, str]:
    client = TestClient(create_app())
    state = _full_state("web-test-session")
    get_session_store().create(state)
    return client, state.session_id


def test_intro_page_renders_required_elements() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/intro")
    assert r.status_code == 200
    assert "유의사항" in r.text
    assert "개인정보 처리" in r.text
    assert "크레딧포유" in r.text


def test_upload_page_renders_four_input_methods() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/upload")
    assert r.status_code == 200
    for marker in ("PDF 파일 업로드", "사진(이미지) 업로드", "데모용 합성 문서", "직접 입력"):
        assert marker in r.text


def test_extraction_page_shows_source_badges() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/extraction")
    assert r.status_code == 200
    assert "A금융" in r.text
    assert "문서" in r.text  # source badge label
    assert "전체 확인 완료" in r.text


def test_supplement_page_shows_five_fixed_questions() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/supplement")
    assert r.status_code == 200
    assert "모름" in r.text
    assert "월 실수령소득은 얼마인가?" in r.text


def test_result_page_shows_confirmed_numbers_and_trace() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/result")
    assert r.status_code == 200
    assert "확정 숫자" in r.text
    assert "20만 원" in r.text
    assert "이 숫자는 어디서 왔나요" in r.text


def test_result_page_shows_income_drop_scenario() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/result")
    assert r.status_code == 200
    assert "소득이 20% 줄어든다면" in r.text
    assert "60만 원" in r.text


def test_paths_page_shows_eleven_item_card() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/paths")
    assert r.status_code == 200
    assert "사전채무조정" in r.text
    assert "검토 후보 (확정 아님)" in r.text
    assert "정책 기준일" in r.text


def test_plan_page_shows_plan_and_pdf_download() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/plan")
    assert r.status_code == 200
    assert "추출된 채무 목록과 연체일수 확인" in r.text
    assert "PDF 다운로드" in r.text
    assert "포함할 항목을 선택" in r.text


def test_dev_mode_banner_hidden_under_deploy_config() -> None:
    """배포 기준 설정(allow_unverified_cards: false)에서는 개발 모드 배너가 없다."""
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/result")
    assert "개발 모드" not in r.text


def test_dev_mode_banner_shown_when_allow_unverified_cards_enabled(monkeypatch) -> None:
    """설정을 되돌리면 배너가 다시 뜬다 — 배너 렌더링 자체를 고정한다."""
    from dn.web import routes as web_routes

    base = get_settings()
    relaxed = base.model_copy(
        update={
            "config": base.config.model_copy(
                update={
                    "rules": base.config.rules.model_copy(update={"allow_unverified_cards": True})
                }
            )
        }
    )
    client, sid = _client_with_session()
    monkeypatch.setattr(web_routes, "get_settings", lambda: relaxed)
    r = client.get(f"/web/session/{sid}/result")
    assert "개발 모드" in r.text


def test_missing_session_returns_404_for_web_pages() -> None:
    client = TestClient(create_app())
    r = client.get("/web/session/does-not-exist/result")
    assert r.status_code == 404


def test_all_seven_screens_render_without_500() -> None:
    client, sid = _client_with_session()
    for path in ("intro", "upload", "extraction", "supplement", "result", "paths", "plan"):
        r = client.get(f"/web/session/{sid}/{path}")
        assert r.status_code == 200, f"{path} 화면 렌더링 실패"


# --- 02 화면 데모용 합성 문서 ---------------------------------------------------


def test_upload_page_lists_demo_documents() -> None:
    """드롭다운이 "준비 중" 안내가 아니라 실제 케이스를 보여준다."""
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/upload")
    assert r.status_code == 200
    assert "데모용 합성 문서 선택" in r.text
    assert "연체 90일 — 개인워크아웃 경계(전문상담 연결)" in r.text
    assert "설치되어 있지 않습니다 — PDF 또는 이미지 업로드를" not in r.text


def test_every_offered_demo_case_is_actually_servable() -> None:
    """드롭다운에 뜬 케이스는 전부 /demo-docs 에서 받을 수 있어야 한다.

    화면이 고를 수 있게 해놓고 서버가 못 주는 상태가 이 기능의 원래 결함이었다
    (선택지는 있는데 눌러도 "아직 준비 중"). 목록과 서빙을 함께 고정한다.
    """
    from dn.web.routes import _demo_cases

    client = TestClient(create_app())
    cases = _demo_cases(get_settings())
    assert cases, "데모 케이스가 하나도 없다"
    for case in cases:
        r = client.get(f"/demo-docs/{case['id']}.pdf")
        assert r.status_code == 200, case["id"]
        assert r.content[:5] == b"%PDF-", case["id"]


def test_demo_document_flows_through_the_normal_upload_api() -> None:
    """데모 문서도 일반 업로드 API 를 그대로 타서 S2 까지 간다."""
    client = TestClient(create_app())
    sid = client.post("/api/session").json()["session_id"]
    client.post(f"/api/session/{sid}/consent")

    doc = client.get("/demo-docs/debt_count_3.pdf")
    assert doc.status_code == 200

    r = client.post(
        f"/api/session/{sid}/document",
        files={"file": ("debt_count_3.pdf", doc.content, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "s2_extracted"


# --- 파일 업로드 호환성 버그 (2026-09-06): application/haansoftpdf ---------------


def test_upload_accepts_real_pdf_reported_as_haansoftpdf_mime() -> None:
    """버그 재현 그대로 — 정상 PDF 인데 한컴 연동 Windows 환경 MIME 으로 오면 통과해야 한다."""
    client = TestClient(create_app())
    sid = client.post("/api/session").json()["session_id"]
    client.post(f"/api/session/{sid}/consent")

    doc = client.get("/demo-docs/debt_count_3.pdf")
    assert doc.status_code == 200

    r = client.post(
        f"/api/session/{sid}/document",
        files={"file": ("debt_count_3.pdf", doc.content, "application/haansoftpdf")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "s2_extracted"


def test_upload_rejects_fake_pdf_even_with_haansoftpdf_alias_mime() -> None:
    """별칭 MIME 은 호환성일 뿐 신뢰가 아니다 — 실제 내용이 PDF 가 아니면 여전히 거부."""
    client = TestClient(create_app())
    sid = client.post("/api/session").json()["session_id"]
    client.post(f"/api/session/{sid}/consent")

    r = client.post(
        f"/api/session/{sid}/document",
        files={"file": ("fake.pdf", b"<html>not a pdf</html>", "application/haansoftpdf")},
    )
    assert r.status_code == 400
    assert "지원하지 않는 파일 형식" in r.json()["detail"]


def test_upload_rejects_hwpx_file() -> None:
    """HWPX 는 별도로 구현하지 않았으므로 PDF/이미지로 혼동해 허용하면 안 된다."""
    client = TestClient(create_app())
    sid = client.post("/api/session").json()["session_id"]
    client.post(f"/api/session/{sid}/consent")

    r = client.post(
        f"/api/session/{sid}/document",
        files={"file": ("document.hwpx", b"PK\x03\x04" + b"\x00" * 32, "application/octet-stream")},
    )
    assert r.status_code == 400
    assert "지원하지 않는 파일 형식" in r.json()["detail"]


def test_upload_page_advertises_the_same_formats_the_api_accepts() -> None:
    """UI 안내 문구와 백엔드 허용 목록이 같은 함수에서 나오는지 고정한다."""
    from dn.ingest.uploader import supported_format_label
    from dn.settings import get_settings

    client, sid = _client_with_session()
    page = client.get(f"/web/session/{sid}/upload")
    assert supported_format_label(get_settings()) in page.text


# --- PNG/JPEG 가 PDF 판독기로 잘못 전달되던 버그 (2026-09-06) ---------------------


def _png_bytes() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (20, 20), color="white").save(buf, format="PNG")
    return buf.getvalue()


def test_png_upload_dispatches_to_image_reader_not_pdf_reader(monkeypatch) -> None:
    """핵심 회귀 테스트 — PNG 는 반드시 image_reader 를 타고 pdf_reader(pypdf)는 타지 않는다."""
    import dn.api.routes_document as routes_document

    calls: dict[str, bool] = {"pdf": False, "image": False}

    def fake_pdf_read(path, *, doc_id, settings):
        calls["pdf"] = True
        raise AssertionError("PNG 파일이 pdf_reader.read() 로 전달되면 안 된다")

    def fake_image_read(path, *, doc_id):
        calls["image"] = True
        from dn.domain.models import DocumentContent, PageContent

        return DocumentContent(
            doc_id=doc_id, filename=path.name, is_scanned=True,
            pages=(PageContent(page_no=1, text="OCR 텍스트", image_path=None),),
        )

    monkeypatch.setattr(routes_document.pdf_reader, "read", fake_pdf_read)
    monkeypatch.setattr(routes_document.image_reader, "read", fake_image_read)

    client, sid = _client_with_session()
    r = client.post(
        f"/api/session/{sid}/document",
        files={"file": ("scan.png", _png_bytes(), "image/png")},
    )
    assert r.status_code == 200, r.text
    assert calls["image"] is True
    assert calls["pdf"] is False


def test_pdf_upload_dispatches_to_pdf_reader_not_image_reader(monkeypatch) -> None:
    """대칭 케이스 — PDF 는 image_reader(OCR)를 타지 않는다."""
    import dn.api.routes_document as routes_document

    calls: dict[str, bool] = {"pdf": False, "image": False}

    def fake_pdf_read(path, *, doc_id, settings):
        calls["pdf"] = True
        from dn.domain.models import DocumentContent, PageContent

        return DocumentContent(
            doc_id=doc_id, filename=path.name, is_scanned=False,
            pages=(PageContent(page_no=1, text="네이티브 텍스트", image_path=None),),
        )

    def fake_image_read(path, *, doc_id):
        calls["image"] = True
        raise AssertionError("PDF 파일이 image_reader.read() 로 전달되면 안 된다")

    monkeypatch.setattr(routes_document.pdf_reader, "read", fake_pdf_read)
    monkeypatch.setattr(routes_document.image_reader, "read", fake_image_read)

    client, sid = _client_with_session()
    doc = client.get("/demo-docs/debt_count_3.pdf")
    r = client.post(
        f"/api/session/{sid}/document",
        files={"file": ("debt_count_3.pdf", doc.content, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    assert calls["pdf"] is True
    assert calls["image"] is False


def test_png_upload_no_longer_crashes_with_pdf_error(monkeypatch) -> None:
    """버그 재현 그대로 — 실제 PNG 업로드가 "PDF 를 열 수 없습니다" 로 죽지 않는다."""
    monkeypatch.setattr("pytesseract.image_to_string", lambda img, lang=None: "채무 정보")

    client, sid = _client_with_session()
    r = client.post(
        f"/api/session/{sid}/document",
        files={"file": ("scan.png", _png_bytes(), "image/png")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "s2_extracted"


def test_corrupted_png_gets_image_specific_error_message() -> None:
    """깨진 이미지는 "PDF 를 열 수 없습니다" 가 아니라 이미지 전용 문구로 안내한다."""
    client, sid = _client_with_session()
    r = client.post(
        f"/api/session/{sid}/document",
        files={"file": ("broken.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 4, "image/png")},
    )
    assert r.status_code == 400
    assert "PDF" not in r.json()["detail"]
    assert "이미지" in r.json()["detail"]


# --- 02 화면 "문서 없이 직접 입력" ---------------------------------------------


def _consented_session() -> tuple[TestClient, str]:
    client = TestClient(create_app())
    sid = client.post("/api/session").json()["session_id"]
    client.post(f"/api/session/{sid}/consent")
    return client, sid


def test_upload_page_renders_manual_entry_form() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/upload")
    assert r.status_code == 200
    assert 'id="manual-debt-row"' in r.text
    assert "신용대출" in r.text  # 채무유형 선택지가 한국어 라벨로 나온다
    assert "아직 준비 중입니다" not in r.text


def test_manual_debts_land_in_the_same_stage_as_upload() -> None:
    """직접 입력도 문서 경로와 같은 S2 로 도착해야 이후 화면이 그대로 동작한다."""
    client, sid = _consented_session()
    r = client.post(
        f"/api/session/{sid}/manual-debts",
        json={
            "debts": [
                {
                    "creditor": "가나캐피탈",
                    "product_type": "credit_loan",
                    "balance": "12000000",
                    "overdue_days": 42,
                    "is_secured": False,
                    "executed_at": "2024-03-01",
                },
                {"creditor": "다라카드"},  # 채권자만 아는 경우
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"session_id": sid, "stage": "s2_extracted", "debt_count": 2}

    extraction = client.get(f"/api/session/{sid}/extraction").json()
    assert [d["creditor"]["source"] for d in extraction["debts"]] == ["user_input"] * 2
    # 빈 칸은 UNKNOWN 으로 남는다 — 0 이나 기본값으로 채우지 않는다
    assert extraction["debts"][1]["balance"]["value"] is None
    assert extraction["debts"][1]["balance"]["source"] == "unknown"


def test_manual_debt_gets_no_extraction_confidence() -> None:
    """직접 입력값에 추출 신뢰도를 붙이면 화면 03 이 근거 없는 경고를 띄운다."""
    client, sid = _consented_session()
    client.post(
        f"/api/session/{sid}/manual-debts",
        json={"debts": [{"creditor": "가나캐피탈", "balance": "12000000"}]},
    )
    extraction = client.get(f"/api/session/{sid}/extraction").json()
    assert extraction["debts"][0]["balance"]["confidence"] is None

    page = client.get(f"/web/session/{sid}/extraction")
    assert "확인 필요(신뢰도 낮음)" not in page.text


def test_manual_debts_rejects_empty_list() -> None:
    client, sid = _consented_session()
    r = client.post(f"/api/session/{sid}/manual-debts", json={"debts": [{"creditor": "  "}]})
    assert r.status_code == 400
    assert "최소 1건" in r.json()["detail"]


def test_manual_debts_rejects_more_than_max() -> None:
    client, sid = _consented_session()
    limit = get_settings().config.extraction.max_debts
    r = client.post(
        f"/api/session/{sid}/manual-debts",
        json={"debts": [{"creditor": f"채권자{i}"} for i in range(limit + 1)]},
    )
    assert r.status_code == 400
    assert str(limit) in r.json()["detail"]


# --- 남용 방어: 호출 빈도 제한 --------------------------------------------------


def test_document_upload_is_rate_limited_per_ip() -> None:
    """공개 URL 뒤에 한도·과금이 있는 LLM 이 붙으므로 무제한 호출을 막는다."""
    from dn.api import ratelimit

    client = TestClient(create_app())
    limit = get_settings().config.ratelimit.llm_calls_per_ip
    doc = client.get("/demo-docs/debt_count_3.pdf").content

    sid = client.post("/api/session").json()["session_id"]
    client.post(f"/api/session/{sid}/consent")

    ratelimit.reset()
    statuses = []
    for _ in range(limit + 2):
        s2 = client.post("/api/session").json()["session_id"]
        client.post(f"/api/session/{s2}/consent")
        r = client.post(
            f"/api/session/{s2}/document",
            files={"file": ("d.pdf", doc, "application/pdf")},
        )
        statuses.append(r.status_code)

    assert statuses[:limit] == [200] * limit, "한도 안에서는 전부 통과해야 한다"
    assert statuses[limit:] == [429, 429]
    ratelimit.reset()


def test_manual_entry_is_not_rate_limited() -> None:
    """직접 입력은 LLM 을 쓰지 않으므로 막을 이유가 없다."""
    from dn.api import ratelimit

    client = TestClient(create_app())
    limit = get_settings().config.ratelimit.llm_calls_per_ip
    ratelimit.reset()
    for _ in range(limit + 3):
        sid = client.post("/api/session").json()["session_id"]
        client.post(f"/api/session/{sid}/consent")
        r = client.post(
            f"/api/session/{sid}/manual-debts",
            json={"debts": [{"creditor": "가나캐피탈", "balance": "1000000"}]},
        )
        assert r.status_code == 200, r.text
    ratelimit.reset()


def test_llm_failure_degrades_to_503_with_guidance() -> None:
    """LLM 장애·한도 초과 때 500 으로 죽지 않고 다른 입력 방식으로 안내한다."""
    from dn.api.deps import get_llm_client_dep

    def _broken():
        class _Boom:
            dev_mode = False

            def complete(self, **_kwargs):
                raise RuntimeError("rate limit reached")

        return _Boom()

    app = create_app()
    app.dependency_overrides[get_llm_client_dep] = _broken
    client = TestClient(app)
    sid = client.post("/api/session").json()["session_id"]
    client.post(f"/api/session/{sid}/consent")
    doc = client.get("/demo-docs/debt_count_3.pdf").content

    r = client.post(
        f"/api/session/{sid}/document", files={"file": ("d.pdf", doc, "application/pdf")}
    )
    assert r.status_code == 503
    assert "직접 입력" in r.json()["detail"]

    # 세션은 S1 에 남아 있어야 다른 방식으로 다시 시도할 수 있다
    assert client.get(f"/api/session/{sid}/extraction").json()["debts"] == []
