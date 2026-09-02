# 채무회복 내비게이터 — 배포 이미지
#
# 주의: 이 Dockerfile 은 이 개발 환경에 docker 데몬 접근 권한이 없어
# `docker build` 로 실제 빌드 검증을 하지 못했다. WeasyPrint/pdf2image 가
# 요구하는 시스템 패키지는 이 저장소를 개발해 온 샌드박스(같은 계열의
# Debian 기반)에서 실제로 동작을 확인한 패키지명을 그대로 옮긴 것이다.

FROM python:3.11-slim

# WeasyPrint(PDF 렌더링) + pdf2image(스캔본 렌더링) + 한글 폰트 + 헬스체크용 curl.
#
# fontconfig 를 명시적으로 넣는 이유: libpango-1.0-0 이 끌어오는 건 런타임
# 라이브러리(libfontconfig1)뿐이고, fc-cache/트리거 스크립트를 가진 fontconfig
# 패키지 자체는 아니다. 이게 없으면 fonts-noto-cjk 로 설치된 폰트가 캐시에
# 제대로 등록된다는 보장이 없어, 컨테이너는 뜨지만 PDF의 한글이 깨질 수 있다.
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    fonts-noto-cjk \
    fontconfig \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libcairo2 \
    libffi-dev \
    shared-mime-info \
    curl \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY config ./config
# 데모용 합성 신용정보조회서 (약 8MB). 02 화면의 "데모용 합성 문서 선택"이
# 런타임에 /demo-docs 로 서빙한다 — 이게 빠지면 조회서 없는 사용자는
# 화면 흐름을 전혀 체험할 수 없다.
COPY data/synthetic/pdf ./data/synthetic/pdf

# ANTHROPIC_API_KEY 없이 무료로 돌리고 싶으면 --build-arg DN_EXTRAS=local 로
# llama-cpp-python 을 같이 설치한다(기본 빌드는 그대로 가볍게 유지). 모델
# 가중치(수 GB)는 이미지에 넣지 않고 ./models 를 볼륨으로 마운트해 쓴다 —
# docker-compose.local.yml, README "로컬 LLM으로 무료 실행" 참고.
ARG DN_EXTRAS=""
RUN if [ -n "$DN_EXTRAS" ]; then \
        pip install --no-cache-dir -e ".[$DN_EXTRAS]"; \
    else \
        pip install --no-cache-dir -e .; \
    fi

ENV DN_ENV=production \
    DN_UPLOAD_DIR=/app/uploads \
    DN_SESSION_DB=/app/sessions.db

RUN mkdir -p /app/uploads

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "dn.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
