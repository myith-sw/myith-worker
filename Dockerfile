# PART O-2: 반드시 저장소 루트의 `Dockerfile`. 이름·위치를 옮기면 배포가 깨진다.
# 타깃은 EC2 t3.small x86 → linux/amd64 (O-1). 빌드 명령에 --platform 을 붙인다 (O-4).
#
# 멀티스테이지: builder에서 빌드 도구로 wheel 설치 → 최종 이미지에서 도구 제거
# (디스크 20GB, O-6). kiwipiepy/PyMuPDF/pdfplumber가 slim에서 실패하기 쉬워
# build-essential·cmake를 안전망으로 둔다 (대개는 manylinux wheel로 해결됨).

# ── builder ─────────────────────────────────────────────────
FROM --platform=linux/amd64 python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── runtime ─────────────────────────────────────────────────
FROM --platform=linux/amd64 python:3.11-slim

# curl: O-8 헬스체크에서 사용. 빌드 도구는 넣지 않는다.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8000

# --host 0.0.0.0 필수. 127.0.0.1이면 컨테이너 밖에서 접근 불가 (O-2).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
