# syntax=docker/dockerfile:1

# ===== 1段目: 依存パッケージとアプリをインストールする =====
FROM python:3.15-slim AS builder

# uv（パッケージ管理ツール）を公式イメージからコピー
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# 先に依存パッケージだけ入れる（コードを変えても、ここはキャッシュが効いて速い）
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# アプリ本体を入れる
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


# ===== 2段目: 実行用の小さなイメージ =====
FROM python:3.15-slim

# root ではない専用ユーザーで動かす（乗っ取られたときの被害を小さくする）
RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY migrations ./migrations
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# instance フォルダ（SQLite のデータベースを置く場所）
RUN mkdir -p /app/instance && chown app:app /app/instance

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=fl_demonstro \
    APP_ENV=production \
    INSTANCE_PATH=/app/instance

USER app

EXPOSE 8000

ENTRYPOINT ["entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "fl_demonstro:create_app()"]
