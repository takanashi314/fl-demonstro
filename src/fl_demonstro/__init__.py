"""fl_demonstro パッケージの入口。アプリを組み立てる create_app() を置く。

create_app() はアプリケーションファクトリ（呼ぶたびに新しい Flask アプリを作って返す関数）。
アプリをモジュールの変数として1つだけ作らず、関数にしているので、
設定を変えたアプリをいくつでも作れる（テストは設定クラスを渡して毎回作り直す）。

create_app() を呼ぶところ：
- flask コマンド：FLASK_APP=fl_demonstro のとき、このパッケージから
  create_app という名前の関数を探して呼ぶ（flask run・flask db upgrade など）。
- gunicorn（本番の Docker）："fl_demonstro:create_app()" を指定して呼ぶ（Dockerfile）。
- テスト：tests/conftest.py の make_app フィクスチャが設定クラスを渡して呼ぶ。
"""

import os
from pathlib import Path

from cachelib import FileSystemCache
from flask import Flask
from redis import Redis
from werkzeug.middleware.proxy_fix import ProxyFix

from fl_demonstro.config import Config, get_config
from fl_demonstro.errors import init_error_handlers
from fl_demonstro.extensions import (
    csrf,
    db,
    limiter,
    login_manager,
    migrate,
    server_session,
)
from fl_demonstro.security import init_security


def _instance_path() -> str:
    """instance フォルダ（データベースなどを置く場所）の絶対パスを返す。

    環境変数 INSTANCE_PATH があればそれを使う（Docker ではこちら）。
    なければプロジェクト直下の instance/ を使う。
    """
    # Flask の既定に任せると、src/ レイアウトでは src/instance になってしまうので、
    # ここで場所を決めて Flask(instance_path=...) に渡す。
    if path := os.environ.get("INSTANCE_PATH"):
        return str(Path(path).resolve())
    # src/fl_demonstro/__init__.py から2つ上がプロジェクト直下
    # （Docker ではパッケージが site-packages に入り、この計算が当てはまらないので
    #   INSTANCE_PATH を設定している）
    return str(Path(__file__).resolve().parents[2] / "instance")


def _configure_session_storage(app: Flask) -> None:
    """セッションの保存先を決める（設定で指定されていればそれを使う）。"""
    # Flask-Session は init_app() のときに SESSION_TYPE を読んで保存先を決めるので、
    # create_app() では server_session.init_app() より前に呼ぶ。
    if app.config.get("SESSION_TYPE"):
        return  # テスト用の設定などで指定済み
    if redis_url := app.config.get("REDIS_URL"):
        # Redis に保存する（複数のワーカーでセッションを共有できる）
        app.config["SESSION_TYPE"] = "redis"
        app.config["SESSION_REDIS"] = Redis.from_url(redis_url)
    else:
        # instance/sessions フォルダのファイルに保存する（開発用）
        # threshold：ファイルがこの数を超えると、期限切れのもの → 古いものの順に消す
        app.config["SESSION_TYPE"] = "cachelib"
        app.config["SESSION_CACHELIB"] = FileSystemCache(
            str(Path(app.instance_path) / "sessions"), threshold=1000
        )


def _trust_reverse_proxy(app: Flask) -> None:
    """リバースプロキシの後ろで動かすとき、本当の接続元の情報を読み取るようにする。

    プロキシを通すと、アプリからは全員が「プロキシの IP アドレス」から来たように見え、
    IP アドレスごとの回数制限が全員で1つになってしまう。
    TRUSTED_PROXY_COUNT が 1 以上なら、プロキシが付けるヘッダー
    （X-Forwarded-For / -Proto / -Host）から、接続元の IP アドレス・https かどうか・
    ホスト名を読み取る。
    """
    count = app.config["TRUSTED_PROXY_COUNT"]
    if count:
        # ProxyFix は WSGI アプリ（app.wsgi_app）を包むミドルウェア。リクエストが Flask に
        # 届く前に request.remote_addr などを書き換えるので、回数制限（get_remote_address）や
        # url_for(_external=True) は書き換えた後の値を使う。
        # x_for=count：X-Forwarded-For の右から count 個目を接続元として信頼する
        # （それより左は、利用者が偽って付けられるので信頼しない）。
        # Flask の公式ドキュメントどおりの書き方（mypy はメソッドへの代入とみなすので除外）
        app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
            app.wsgi_app, x_for=count, x_proto=count, x_host=count
        )


def _init_debug_toolbar(app: Flask) -> None:
    """デバッグモードのときだけ、デバッグツールバーを表示する。

    開発用の道具なので、本番（Docker）には入っていない。入っていなければ何もしない。
    """
    # app.debug は FLASK_DEBUG=1 のとき True。テスト中（app.testing）は出さない。
    if not app.debug or app.testing:
        return
    try:
        # 開発用の依存（dev グループ）なので、関数の中で import する。
        # 本番のイメージには入っていないので、ImportError になったら何もしない。
        from flask_debugtoolbar import DebugToolbarExtension
    except ImportError:
        return
    DebugToolbarExtension(app)
    # ツールバーは HTML に直接書かれたスクリプトを使うため、CSP を少し緩める
    # （init_security() はこの値を呼ばれたときに1回だけ読むので、それより前に設定する）
    app.config["CSP_ALLOW_INLINE"] = True


def create_app(config_class: type[Config] | None = None) -> Flask:
    """アプリケーションファクトリ：Flask アプリを作って返す。

    config_class を省略すると、環境変数 APP_ENV に合った設定を使う。
    """
    # __name__（"fl_demonstro"）から、テンプレート（templates/）と静的ファイル（static/）の
    # 場所が決まる（このパッケージのフォルダの中を探す）。
    app = Flask(__name__, instance_path=_instance_path())
    # 設定クラスの大文字の属性を app.config に読み込む
    app.config.from_object(config_class or get_config())

    # 鍵がないまま起動すると、最初に CSRF トークンを作るリクエストで初めてエラーになるので、
    # 起動の時点で止める（拡張機能の初期化より前なので、DB のエンジンなども作られない）
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY が設定されていません。.env に SECRET_KEY=... を書いてください。"
        )

    _trust_reverse_proxy(app)

    # 拡張機能をアプリと結びつける
    # （extensions.py で作っておいた拡張機能に、このアプリを登録する。
    #   拡張機能の多くは、ここでリクエストの前後に動く処理（フック）をアプリに登録する）
    #
    # 登録した順番が、リクエストの前後の処理の順番になる：
    # - リクエストの前（before_request）は登録順：CSRF の確認 → 回数制限の確認。
    #   CSRF トークンのない POST は、回数として数える前に 400 で止まる。
    # - レスポンスの後（after_request）は登録の逆順：セキュリティ用ヘッダー（init_security）
    #   → 「ログインしたままにする」の Cookie（Flask-Login）→ 回数制限の加算とヘッダー（Flask-Limiter）。
    #   ログインの回数制限は deduct_when で、失敗したとき（レスポンスを見て）だけ数える。
    db.init_app(app)  # エンジンを作る。アプリコンテキストの終わりにセッションを閉じる
    migrate.init_app(app, db)  # flask db コマンド（マイグレーション）を使えるようにする
    csrf.init_app(app)  # before_request：POST などの CSRF トークンを確かめる
    limiter.init_app(app)  # before_request：回数を確かめる／after_request：数える
    login_manager.init_app(app)  # after_request：「ログインしたままにする」の Cookie
    _configure_session_storage(app)  # server_session.init_app() より前に決める
    server_session.init_app(app)  # セッションの保存先を差し替える（session_interface）
    _init_debug_toolbar(app)  # init_security() より前に呼ぶ（CSP の設定を変えるため）

    init_security(app)  # after_request：セキュリティ用ヘッダー
    init_error_handlers(app)  # 400・404・413・500 などのエラー画面

    # ブループリントの登録
    # （accounts を読み込むとモデルも読み込まれ、Flask-Migrate がテーブルを見つけられる）
    # 関数の中で import するのは、パッケージを読み込んだだけ（import fl_demonstro.config など）で
    # ビューやモデルまで読み込まれないようにするため。Flask のアプリケーションファクトリで、
    # 循環 import を避けるためによく使う書き方。
    from fl_demonstro.accounts import bp as accounts_bp
    from fl_demonstro.main import bp as main_bp

    app.register_blueprint(main_bp)  # トップページ（/）
    app.register_blueprint(accounts_bp)  # /accounts/ 以下（サインアップ・ログインなど）

    return app
