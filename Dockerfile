FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Cloud Run은 PORT 환경변수(기본 8080)를 주입합니다.
# gunicorn + UvicornWorker: 프로세스 기반 동시성 + async 이벤트 루프 유지
# -w 2: Cloud Run 인스턴스당 2개 워커 (CPU 2코어 기준)
# --timeout 300: Gemini 호출 최대 응답 시간 대비
CMD ["sh", "-c", \
     "gunicorn app.main:app \
      -w 2 \
      -k uvicorn.workers.UvicornWorker \
      --bind 0.0.0.0:${PORT:-8000} \
      --timeout 300 \
      --log-level info"]
