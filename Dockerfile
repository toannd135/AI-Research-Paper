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

# Tectonic (XeTeX + BibTeX) cho xuất PDF chuẩn LaTeX IEEEtran.
# Biên dịch docker/latex-warmup (cùng preamble với app) một lần để tải sẵn gói + font vào image -> chạy được khi offline.
ARG TECTONIC_VERSION=0.15.0
# Chọn bản theo kiến trúc CPU (Linux/Windows x86_64 hoặc Mac Apple Silicon arm64)
RUN case "$(uname -m)" in \
        x86_64|amd64) TT_ARCH=x86_64 ;; \
        aarch64|arm64) TT_ARCH=aarch64 ;; \
        *) echo "Tectonic không hỗ trợ kiến trúc $(uname -m)" >&2; exit 1 ;; \
    esac \
    && curl -fsSL "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${TECTONIC_VERSION}/tectonic-${TECTONIC_VERSION}-${TT_ARCH}-unknown-linux-musl.tar.gz" \
        | tar -xz -C /usr/local/bin tectonic \
    && tectonic --version
COPY docker/latex-warmup /tmp/latex-warmup
RUN cd /tmp/latex-warmup && tectonic -X compile paper.tex && test -s paper.pdf && rm -rf /tmp/latex-warmup

COPY --from=render-assets /render-assets/node_modules/mermaid/dist/mermaid.min.js /opt/paperai/render-assets/mermaid.min.js
COPY --from=render-assets /render-assets/node_modules/mermaid/LICENSE /opt/paperai/render-assets/mermaid.LICENSE
COPY --from=render-assets /render-assets/node_modules/katex/dist /opt/paperai/render-assets/katex
COPY --from=render-assets /render-assets/node_modules/katex/LICENSE /opt/paperai/render-assets/katex.LICENSE

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
