# syntax=docker/dockerfile:1
# ↑ この行は必ずファイルの1行目に置く（コメントより前でないと効かない）。
#   BuildKit が、この書き方のバージョンに合わせて Dockerfile を読む。
# docker/dockerfile:1：
# Dockerfile を解釈するフロントエンドのイメージ。:1 は「1.x の最新版」で、書き方が変わる大きな変更（2.x）は入らない。

# アプリを動かすイメージを作る手順。docker compose up --build のときに上から順に実行される。
# 2段構え（マルチステージビルド）にして、1段目で依存パッケージとアプリをインストールし、
# 2段目にはその結果（/app/.venv）だけを持っていく。
# uv やビルド用のファイルが最終的なイメージに残らないので、イメージが小さく、安全になる。
# 各命令の結果はレイヤーとしてキャッシュされ、入力が変わっていない命令は次のビルドで飛ばされる。

# ===== 1段目: 依存パッケージとアプリをインストールする =====
# python:3.15-slim：
# 公式の Python イメージ。「名前:タグ」の形で、3.15 は Python のバージョン、slim は余計なパッケージを省いた小さい版（元は Debian 13）。
# タグは中身を固定しないので、3.15 の新しいパッチ版が出ると、同じタグが新しいイメージを指すようになる。
# ただし、手元にイメージがあるうちは、ビルドはそれを使い続ける（docker compose build --pull で取り直すと、新しい版になる）。
# AS builder：
# この段に builder という名前を付ける。2段目の COPY --from=builder で参照する。
FROM python:3.15-slim AS builder

# uv（パッケージ管理ツール）を公式イメージからコピーする。
# --from=ghcr.io/astral-sh/uv:0.13.5：
# ビルドコンテキスト（プロジェクトのフォルダ）ではなく、このイメージの中からコピーする。
# バージョンを固定して、いつビルドしても同じ uv を使う。
# /uv：
# コピー元。uv のイメージに入っている uv の実行ファイル（ほかには uvx しか入っていない）。
# /usr/local/bin/uv：
# コピー先。PATH に入っている場所なので、uv とだけ書けば実行できる。
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

# uv の動きを決める環境変数（この段の中だけで使う。2段目には引き継がれない）。
# UV_COMPILE_BYTECODE=1：
# インストールのときに .py を .pyc にしておく（uv の既定では、最初に import したときに作る）。
# 2段目では仮想環境の所有者が root で、app ユーザーは .pyc を書き込めない。
# ここで作っておかないと、プロセスを起動するたびにコンパイルし直すことになる。
# UV_LINK_MODE=copy：
# キャッシュからパッケージを入れる方法を、コピーにする。
# 既定の clone（コピーオンライト）やハードリンクは、同じファイルシステムの中でしかできない。
# キャッシュ（--mount=type=cache）は別のファイルシステムなので、uv は警告を出してからコピーに切り替える。
# 最初からコピーにして、その警告を出さないようにする。
# UV_PYTHON_DOWNLOADS=never：
# uv が Python を自分でダウンロードしないようにする。
# イメージの Python を使い、pyproject.toml の requires-python（==3.15.*）に合わなければ、別の Python を取ってこずに失敗する。
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# 以降の命令は /app で実行される（なければ作られる）
WORKDIR /app

# 先に依存パッケージだけ入れる（コードを変えても、ここはキャッシュが効いて速い）
# pyproject.toml と uv.lock が変わらない限り、次の RUN までキャッシュが使われる。
# ./：
# コピー先。WORKDIR の /app のこと。
# コピー元が2つ以上のときは、コピー先を / で終わるフォルダにする決まり。
COPY pyproject.toml uv.lock ./
# --mount=type=cache,target=/root/.cache/uv：
# この RUN の間だけ、BuildKit が管理するフォルダを付ける。
# type=cache：
# 中身がビルドをまたいで残るフォルダ。イメージには入らない。
# ダウンロードしたパッケージを、次のビルドで使い回す。
# target=/root/.cache/uv：
# 付ける場所。ビルド中は root で動くので、uv の既定のキャッシュの場所（~/.cache/uv）がここになる。
# id を書いていないので target が id になり、下の RUN と同じキャッシュを使う。
# uv sync：
# /app/.venv に仮想環境を作り、uv.lock のとおりにパッケージを入れる（uv.lock にないものは消す）。
# --locked：
# uv.lock が pyproject.toml と食い違っていたら失敗させる。
# （--frozen は食い違いを確かめずに uv.lock を使うので、古い uv.lock のままビルドしてしまう）
# --no-dev：
# dev グループ（pytest・flask-debugtoolbar など）は入れない。
# --no-install-project：
# アプリ自体はまだ入れない（コードの変更でこの段を作り直さないため）。
# まだ src/ と README.md をコピーしていないので、アプリはこの時点では入れられない。
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# アプリ本体を入れる
# README.md は pyproject.toml の readme で指定しているので、パッケージを作るのに要る。
COPY README.md ./
COPY src ./src
# アプリ（fl_demonstro）をパッケージにして、/app/.venv の site-packages にインストールする。
# --no-install-project を付けていないので、今度はアプリも入る。
# --mount=type=cache,target=/root/.cache/uv：
# 上の RUN と同じキャッシュ。
# --locked：
# 上の RUN と同じ。書かないと、uv.lock が古いときに書き換えてから入れてしまう。
# --no-dev：
# 上の RUN と同じ。書かないと、uv sync が環境を合わせ直すときに dev グループが足される。
# --no-editable：
# src/ を参照する形（editable）ではなく、ビルドバックエンド（uv_build）で wheel を作り、コードを site-packages にコピーする。
# そのため、2段目に src/ を持っていかなくても動く。
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


# ===== 2段目: 実行用の小さなイメージ =====
# もう一度まっさらな Python イメージから始める（1段目の中身はここで捨てる）。
# AS を付けていないが、最後の段なので、これが出来上がるイメージになる。
FROM python:3.15-slim

# root ではない専用ユーザーで動かす（乗っ取られたときの被害を小さくする）
# groupadd --system：
# システム用のグループを作る。GID は 1000 未満から選ばれる（今は 999）。
# useradd --system：
# システム用のユーザーを作る。UID は 1000 未満から選ばれる（今は 999）。
# ホームディレクトリは作られない。
# --gid app：
# 主グループを、上で作った app にする。
# 書かないと、useradd がユーザーと同じ名前のグループを作ろうとし、app はもうあるので失敗する。
# --create-home：
# --system では作られないホームディレクトリ /home/app を作る。
# gunicorn が管理用のソケット（~/.gunicorn/gunicorn.ctl）を置くのに使う。
RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

# 1段目で作った仮想環境（依存パッケージとアプリ）だけを持ってくる。
# 1段目と同じ python:3.15-slim なので、仮想環境の中の python が指す先（イメージの Python）がそのまま使える。
# --from=builder：
# 1段目（AS builder）の中からコピーする。
# --chown を付けていないので、所有者は root のまま。app ユーザーはコードを書き換えられない。
COPY --from=builder /app/.venv /app/.venv
# マイグレーション（flask db upgrade で使う）。site-packages には入らないので、別にコピーする。
COPY migrations ./migrations
# コンテナを起動するたびに最初に実行するスクリプト（下の ENTRYPOINT）
# COPY はファイルの実行権限をそのまま持ってくるので、Git で実行権限（755）を付けてある。
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# instance フォルダ（SQLite のデータベースを置く場所）
# 所有者を app にしておく。compose.yaml でここに名前付きボリュームを付けると、
# 新しく作ったボリュームにはこのフォルダの所有者もコピーされるので、app ユーザーが書き込める。
# mkdir -p：
# 途中のフォルダもまとめて作る。すでにあってもエラーにしない。
# chown app:app：
# 所有者を「ユーザー:グループ」の形で、app ユーザー・app グループにする。
RUN mkdir -p /app/instance && chown app:app /app/instance

# コンテナの中の環境変数（compose.yaml の environment: と合わせたものがアプリに届く）
# PATH="/app/.venv/bin:$PATH"：
# 先頭に /app/.venv/bin を足す。$PATH は、ビルドのときに元のイメージの PATH に置き換わる。
# gunicorn・flask がこの仮想環境のものになるので、uv run を通さなくても仮想環境のパッケージで動く（実行用のイメージに uv は入っていない）。
# PYTHONDONTWRITEBYTECODE=1：
# 実行中に .pyc を書かない。
# 仮想環境の .pyc は1段目で作ってあり、ほかの場所（migrations/ など）も root の持ち物で、app ユーザーはどのみち書けない。
# PYTHONUNBUFFERED=1：
# 標準出力・標準エラーをためずにすぐ出す。
# 出力先が端末でないと、Python はためてからまとめて出すので、docker compose logs に出るのが遅れる。
# FLASK_APP=fl_demonstro：
# flask コマンド（entrypoint.sh の flask db upgrade）が読み込むアプリ。
# APP_ENV=production：
# 本番用の設定（ProductionConfig）を選ぶ。手元の .env の APP_ENV はここには届かない。
# INSTANCE_PATH=/app/instance：
# instance フォルダの場所。パッケージが site-packages にあるので、
# 既定の計算（プロジェクト直下の instance/）が使えず、ここで指定する。
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
# 8000：
# プロトコルを書いていないので tcp になる（8000/tcp と同じ）。
EXPOSE 8000

# 起動時の流れ：entrypoint.sh が flask db upgrade でデータベースを最新の形にしてから、
# exec で CMD（gunicorn）に置き換わる。gunicorn がコンテナの PID 1 になり、停止の合図を直接受け取る。
# ["entrypoint.sh"]：
# JSON の配列で書く形（exec 形式）。シェル（/bin/sh -c）を通さずに直接実行するので、entrypoint.sh が PID 1 になる。
# 文字列だけで書く形（シェル形式）にすると、/bin/sh -c が PID 1 になり、CMD も無視される。
# entrypoint.sh は、PATH の /usr/local/bin から見つかる。
ENTRYPOINT ["entrypoint.sh"]
# CMD は、起動時に ENTRYPOINT の後ろに引数として付く（entrypoint.sh gunicorn --bind ...）。
# gunicorn（本番用の Web サーバー）の設定：
# --bind 0.0.0.0:8000：
# コンテナのすべてのアドレスの 8000 番で待つ。
# パソコンからの通信は、Docker のネットワークを通ってコンテナのアドレス（172.18.0.3 など）に届く。
# gunicorn の既定の 127.0.0.1:8000 では、コンテナの外からの通信を受け取れない。
# --workers 2：
# ワーカーを2つ使う（既定は1）。ワーカーごとに create_app() が呼ばれ、別々のアプリになるので、
# セッションと送信回数の記録は Redis で共有する（compose.yaml の REDIS_URL）。
# --access-logfile -：
# アクセスログを標準出力に出す（- は標準出力のこと）。書かないと、アクセスログは出ない。
# "fl_demonstro:create_app()"：
# 「モジュール:名前」の形。() を付けると関数として呼び、戻り値をアプリにする。
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "fl_demonstro:create_app()"]
