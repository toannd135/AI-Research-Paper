FROM node:22-slim AS render-assets
WORKDIR /render-assets
COPY app/pipeline/export/assets/package*.json ./
RUN npm ci --omit=dev --no-audit --no-fund

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=1000 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-constraints.txt ./

# Tận dụng BuildKit cache mount để lưu lại các file .whl đã tải
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt -c requirements-constraints.txt

# Chromium cho xuất PDF (render Mermaid/KaTeX)
RUN playwright install --with-deps chromium

COPY --from=render-assets /render-assets/node_modules/mermaid/dist/mermaid.min.js /opt/paperai/render-assets/mermaid.min.js
COPY --from=render-assets /render-assets/node_modules/mermaid/LICENSE /opt/paperai/render-assets/mermaid.LICENSE
COPY --from=render-assets /render-assets/node_modules/katex/dist /opt/paperai/render-assets/katex
COPY --from=render-assets /render-assets/node_modules/katex/LICENSE /opt/paperai/render-assets/katex.LICENSE

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
