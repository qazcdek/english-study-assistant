# ---------- 1단계: 프론트엔드 빌드 ----------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- 2단계: 백엔드 ----------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir .

# 프론트엔드를 같은 오리진에서 서빙한다 (세션 쿠키가 same-site 로 유지된다)
COPY --from=web /web/dist ./static

EXPOSE 8000
# Render 등은 PORT 환경변수로 포트를 지정한다.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
