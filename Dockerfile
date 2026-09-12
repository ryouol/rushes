FROM node:22-bookworm-slim AS web-build
WORKDIR /build/web
ENV NEXT_TELEMETRY_DISABLED=1
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/app ./app
COPY web/components ./components
COPY web/lib ./lib
COPY web/public ./public
COPY web/next.config.mjs web/next-env.d.ts web/postcss.config.mjs web/tsconfig.json ./
# Render supplies matching service environment variables as build arguments.
# These are public page values; credentials must never be added to this list.
ARG RUSHES_ORIGIN
ARG RENDER_EXTERNAL_URL
ARG RUSHES_CONTACT_EMAIL
ARG RUSHES_CONTACT_PHONE
ARG RUSHES_CONTACT_ADDRESS
ARG RUSHES_LEGAL_ENTITY
ARG RUSHES_GA_MEASUREMENT_ID
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.12.8 AS uv
FROM python:3.12-slim-bookworm AS temporal-build
ARG TARGETARCH
COPY scripts/install_temporal_server.py /tmp/install_temporal_server.py
RUN python /tmp/install_temporal_server.py --arch "$TARGETARCH" --output /opt/temporal

FROM python:3.12-slim-bookworm AS python-build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY backend ./backend
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home rushes \
    && mkdir -p /var/data/storage /var/data/exports /var/data/models \
    && chown -R rushes:rushes /var/data
WORKDIR /app
COPY --from=python-build /app/.venv /app/.venv
COPY --from=temporal-build /opt/temporal /opt/temporal
COPY --from=web-build /build/web/out ./web/out
COPY scripts/serve.py ./scripts/serve.py
COPY scripts/bootstrap_workflow_db.py ./scripts/bootstrap_workflow_db.py
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RUSHES_STORAGE_ROOT=/var/data/storage \
    RUSHES_OUTPUT_ROOT=/var/data/exports \
    HF_HOME=/var/data/models/huggingface \
    FASTEMBED_CACHE_PATH=/var/data/models/fastembed
USER rushes
EXPOSE 10000
CMD ["python", "scripts/serve.py"]
