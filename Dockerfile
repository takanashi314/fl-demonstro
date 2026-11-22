# syntax=docker/dockerfile:1
# ↑ この行は必ずファイルの1行目に置く（コメントより前でないと効かない）。
#   BuildKit が、この書き方のバージョンに合わせて Dockerfile を読む。

# アプリを動かすイメージを作る手順。docker compose up --build のときに上から順に実行される。
# 2段構え（マルチステージビルド）にして、1段目で依存パッケージとアプリをインストールし、
# 2段目にはその結果（/app/.venv）だけを持っていく。
# uv やビルド用のファイルが最終的なイメージに残らないので、イメージが小さく、安全になる。
# 各命令の結果はレイヤーとしてキャッシュされ、入力が変わっていない命令は次のビルドで飛ばされる。

# ===== 1段目: 依存パッケージとアプリをインストールする =====
# 公式の Python イメージ（slim は余計なパッケージを省いた小さい版）。
# AS builder で名前を付け、2段目から COPY --from=builder で参照する。
FROM python:3.15-slim AS builder

# uv（パッケージ管理ツール）を公式イメージからコピー
# （バージョンを固定して、いつビルドしても同じ uv を使う。uv の実行ファイル1つだけを持ってくる）
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

# UV_COMPILE_BYTECODE=1：インストールのときに .pyc を作っておき、起動を速くする。
# UV_LINK_MODE=copy：キャッシュ（--mount=type=cache）は別のファイルシステムなので、
#   ハードリンクではなくコピーでインストールする。
# UV_PYTHON_DOWNLOADS=never：イメージの Python を使い、uv が別の Python を取ってこないようにする。
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# 以降の命令は /app で実行される（なければ作られる）
WORKDIR /app

# 先に依存パッケージだけ入れる（コードを変えても、ここはキャッシュが効いて速い）
# pyproject.toml と uv.lock が変わらない限り、次の RUN までキャッシュが使われる。
COPY pyproject.toml uv.lock ./
# --mount=type=cache：ダウンロードしたパッケージを、ビルドをまたいで使い回す（イメージには入らない）。
# --locked：uv.lock が pyproject.toml と食い違っていたら失敗させる。
# --no-dev：dev グループ（pytest・flask-debugtoolbar など）は入れない。
# --no-install-project：アプリ自体はまだ入れない（コードの変更でこの段を作り直さないため）。
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# アプリ本体を入れる
# README.md は pyproject.toml の readme で指定しているので、パッケージを作るのに要る。
COPY README.md ./
COPY src ./src
# アプリ（fl_demonstro）をパッケージにして、/app/.venv の site-packages にインストールする。
# --no-editable：src/ を参照する形ではなく、コードを site-packages にコピーする。
#   そのため、2段目に src/ を持っていかなくても動く。
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


# ===== 2段目: 実行用の小さなイメージ =====
# もう一度まっさらな Python イメージから始める（1段目の中身はここで捨てる）。
FROM python:3.15-slim

# root ではない専用ユーザーで動かす（乗っ取られたときの被害を小さくする）
# --system：システム用のユーザー（uid は 1000 未満）。
# --create-home：ホームディレクトリ /home/app も作る（gunicorn が管理用のソケットを置くのに使う）。
RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

# 1段目で作った仮想環境（依存パッケージとアプリ）だけを持ってくる。
# 1段目と同じ python:3.15-slim なので、仮想環境の中の python が指す先（イメージの Python）がそのまま使える。
COPY --from=builder /app/.venv /app/.venv
# マイグレーション（flask db upgrade で使う）。site-packages には入らないので、別にコピーする。
COPY migrations ./migrations
# コンテナを起動するたびに最初に実行するスクリプト（下の ENTRYPOINT）
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# instance フォルダ（SQLite のデータベースを置く場所）
# 所有者を app にしておく。compose.yaml でここに名前付きボリュームを付けると、
# 新しく作ったボリュームにはこのフォルダの所有者もコピーされるので、app ユーザーが書き込める。
RUN mkdir -p /app/instance && chown app:app /app/instance

# コンテナの中の環境変数（compose.yaml の environment: と合わせたものがアプリに届く）
# PATH：先頭に /app/.venv/bin を足す。gunicorn・flask がこの仮想環境のものになるので、
#   uv run を通さなくても仮想環境のパッケージで動く（実行用のイメージに uv は入っていない）。
# PYTHONDONTWRITEBYTECODE=1：実行中に .pyc を書かない（1段目で作ってある）。
# PYTHONUNBUFFERED=1：出力をためずにすぐ出す（docker compose logs ですぐ見える）。
# FLASK_APP：flask コマンド（entrypoint.sh の flask db upgrade）が読み込むアプリ。
# APP_ENV：本番用の設定（ProductionConfig）を選ぶ。手元の .env の APP_ENV はここには届かない。
# INSTANCE_PATH：instance フォルダの場所。パッケージが site-packages にあるので、
#   既定の計算（プロジェクト直下の instance/）が使えず、ここで指定する。
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=fl_demonstro \
    APP_ENV=production \
    INSTANCE_PATH=/app/instance

# 以降（コンテナの中のプロセス）は app ユーザーで動く
USER app

# このポートを使うという宣言（文書の役割だけ）。
# 実際にパソコンから開けるようにするのは、compose.yaml の ports。
EXPOSE 8000

# 起動時の流れ：entrypoint.sh が flask db upgrade でデータベースを最新の形にしてから、
# exec で CMD（gunicorn）に置き換わる。gunicorn がコンテナの PID 1 になり、停止の合図を直接受け取る。
ENTRYPOINT ["entrypoint.sh"]
# gunicorn（本番用の Web サーバー）の設定：
# --bind 0.0.0.0:8000：コンテナのすべてのアドレスの 8000 番で待つ。
# --workers 2：ワーカーを2つ使う。ワーカーごとに create_app() が呼ばれ、別々のアプリになるので、
#   セッションと送信回数の記録は Redis で共有する（compose.yaml の REDIS_URL）。
# --access-logfile -：アクセスログを標準出力に出す。
# "fl_demonstro:create_app()"：fl_demonstro パッケージの create_app() を呼んでアプリを作る。
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "fl_demonstro:create_app()"]
