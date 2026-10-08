# Website Performance Monitor — production image (Render, Hugging Face Docker Space or any Docker host).
# Stage 1 builds the React frontend; stage 2 runs FastAPI (which also serves the UI) on :7860.

FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FRONTEND_DIST=/app/frontend_dist \
    TZ=Asia/Kolkata

# Hugging Face runs containers as uid 1000.
RUN useradd --create-home --uid 1000 user
WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY --chown=user backend/app ./app
COPY --chown=user backend/alembic ./alembic
COPY --chown=user backend/alembic.ini ./alembic.ini
COPY --from=frontend --chown=user /build/dist ./frontend_dist

USER user
EXPOSE 7860

HEALTHCHECK --interval=60s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/api/health' % __import__('os').getenv('PORT', '7860'), timeout=4).status == 200 else 1)"

# One worker: manual-test progress and the in-process timer live in memory, and the
# database lease locks make scheduled runs safe even if a second container appears.
# PORT is provided by Render/Railway/Cloud Run; Hugging Face uses the default 7860.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1 --proxy-headers --forwarded-allow-ips '*' --timeout-graceful-shutdown 20 --no-server-header"]
