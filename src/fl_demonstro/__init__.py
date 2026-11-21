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
    if path := os.environ.get("INSTANCE_PATH"):
        return str(Path(path).resolve())
    # src/fl_demonstro/__init__.py から2つ上がプロジェクト直下
    return str(Path(__file__).resolve().parents[2] / "instance")


def _configure_session_storage(app: Flask) -> None:
    """セッションの保存先を決める（設定で指定されていればそれを使う）。"""
    if app.config.get("SESSION_TYPE"):
        return
    if redis_url := app.config.get("REDIS_URL"):
        app.config["SESSION_TYPE"] = "redis"
        app.config["SESSION_REDIS"] = Redis.from_url(redis_url)
    else:
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
        # Flask の公式ドキュメントどおりの書き方（mypy はメソッドへの代入とみなすので除外）
        app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
            app.wsgi_app, x_for=count, x_proto=count, x_host=count
        )


def _init_debug_toolbar(app: Flask) -> None:
    """デバッグモードのときだけ、デバッグツールバーを表示する。

    開発用の道具なので、本番（Docker）には入っていない。入っていなければ何もしない。
    """
    if not app.debug or app.testing:
        return
    try:
        from flask_debugtoolbar import DebugToolbarExtension
    except ImportError:
        return
    DebugToolbarExtension(app)
    # ツールバーは HTML に直接書かれたスクリプトを使うため、CSP を少し緩める
    app.config["CSP_ALLOW_INLINE"] = True


def create_app(config_class: type[Config] | None = None) -> Flask:
    """アプリケーションファクトリ：Flask アプリを作って返す。

    config_class を省略すると、環境変数 APP_ENV に合った設定を使う。
    """
    app = Flask(__name__, instance_path=_instance_path())
    app.config.from_object(config_class or get_config())

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY が設定されていません。.env に SECRET_KEY=... を書いてください。"
        )

    _trust_reverse_proxy(app)

    # 拡張機能をアプリと結びつける
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    _configure_session_storage(app)
    server_session.init_app(app)
    _init_debug_toolbar(app)

    init_security(app)
    init_error_handlers(app)

    # ブループリントの登録
    # （accounts を読み込むとモデルも読み込まれ、Flask-Migrate がテーブルを見つけられる）
    from fl_demonstro.accounts import bp as accounts_bp
    from fl_demonstro.main import bp as main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(accounts_bp)

    return app
