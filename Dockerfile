# 채무회복 내비게이터 — 배포 이미지
#
# 2026-09-02 `docker compose build` 실행으로 검증했다.
#
# 베이스 이미지에 OS 코드명을 붙여 고정한 이유: `python:3.11-slim` 은 떠 있는
# 태그라 어느 날 Debian 이 올라가면 패키지 이름이 바뀐다. 실제로 이 프로젝트가
# 그랬다 — trixie(Debian 13)로 올라가면서 `libgdk-pixbuf2.0-0` 이
# `libgdk-pixbuf-2.0-0` 으로 바뀌어 빌드가 통째로 실패했다. 마감을 앞두고
# 베이스가 움직여 빌드가 깨지는 일이 없도록 코드명을 명시한다.

FROM python:3.11-slim-trixie

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
    libgdk-pixbuf-2.0-0 \
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

# 가변 상태는 /app/var 한 곳에 모은다. 코드(/app/src, /app/config)는 root 소유로
# 두고 이 디렉터리만 앱 사용자에게 준다 — 실행 중 프로세스가 자기 코드를 덮어쓸 수
# 없게 하기 위해서다. SQLite 는 -wal/-shm 을 같은 디렉터리에 만들므로 파일이 아니라
# 디렉터리에 쓰기 권한이 필요하다.
ENV DN_ENV=production \
    DN_UPLOAD_DIR=/app/var/uploads \
    DN_SESSION_DB=/app/var/sessions.db

# root 로 돌리지 않는다. 업로드 원본과 세션 DB 를 다루는 서비스라 컨테이너가
# 뚫렸을 때의 권한을 좁혀 둔다. uid 1000 으로 고정한 것은 여러 무료 호스팅
# (Hugging Face Spaces 등)이 컨테이너를 uid 1000 으로 실행하기 때문이다 —
# 그 환경에서도 /app/var 에 그대로 쓸 수 있다.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/var/uploads \
    && chown -R app:app /app/var
USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "dn.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
