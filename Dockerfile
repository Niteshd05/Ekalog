# EKALOG single image: the UI is built once (needs the internet for npm + fonts at BUILD time only),
# then served by the Python API from the same port. The runtime image has no Node and makes no outbound calls.

# ---------- stage 1: static UI ----------
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN EKALOG_EXPORT=1 npx next build

# ---------- stage 2: runtime ----------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    EKALOG_UI_DIR=/app/web/out EKALOG_STATE_DIR=/app/state
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/data ./data
COPY --from=web /web/out /app/web/out
RUN useradd -r -u 10001 ekalog && mkdir -p /app/state && chown -R ekalog /app/state /app/backend/data
USER ekalog
EXPOSE 8000 5514/udp
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
