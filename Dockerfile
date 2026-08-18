# 채무회복 내비게이터 — 배포 이미지
#
# 주의: 이 Dockerfile 은 이 개발 환경에 docker 데몬 접근 권한이 없어
# `docker build` 로 실제 빌드 검증을 하지 못했다. WeasyPrint/pdf2image 가
# 요구하는 시스템 패키지는 이 저장소를 개발해 온 샌드박스(같은 계열의
# Debian 기반)에서 실제로 동작을 확인한 패키지명을 그대로 옮긴 것이다.

FROM python:3.11-slim

# WeasyPrint(PDF 렌더링) + pdf2image(스캔본 렌더링) + 한글 폰트 + 헬스체크용 curl.
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    fonts-noto-cjk \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libcairo2 \
    libffi-dev \
    shared-mime-info \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY config ./config

RUN pip install --no-cache-dir -e .

ENV DN_ENV=production \
    DN_UPLOAD_DIR=/app/uploads \
    DN_SESSION_DB=/app/sessions.db

RUN mkdir -p /app/uploads

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "dn.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
