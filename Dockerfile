FROM python:3.12-slim as base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

FROM base as builder
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-workspace --no-dev
RUN --mount=type=bind,source=app/scripts/download_model.py,target=download_model.py \
    /app/.venv/bin/python download_model.py

FROM base as runner
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /root/.EasyOCR /root/.EasyOCR
RUN apt-get update && apt-get install -y libgl-dev libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY app app
COPY alembic alembic
COPY pyproject.toml uv.lock bot-cmd.sh alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH"
ENV DATA_DIR=/data
ENV HOST=0.0.0.0

EXPOSE 8000
