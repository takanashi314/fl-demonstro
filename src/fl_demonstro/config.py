"""アプリの設定。

環境（開発・本番・テスト）ごとに設定クラスを分けている。
開発用と本番用は、環境変数 APP_ENV で選ぶ（未設定なら本番用）。
テスト用は自動テストの中で直接使い、APP_ENV では選べないようにしている。
"""

import os
import secrets
from datetime import timedelta

from argon2.profiles import RFC_9106_LOW_MEMORY
from cachelib import SimpleCache


def _env_bool(name: str, default: bool) -> bool:
    """環境変数を True / False として読む。"""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    """環境変数を 0 以上の整数として読む。"""
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    if not (value.isascii() and value.isdigit()):
        raise ValueError(f"{name} は 0 以上の整数にしてください（今の値: {value!r}）。")
    return int(value)


class Config:
    """全環境で共通の設定。"""

    # セッションや CSRF トークンの署名に使う秘密の鍵。必ず .env などで設定すること。
    # （未設定のときは create_app() がエラーにして起動を止める）
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # データベースの場所。未設定なら instance フォルダの app.db（SQLite）を使う。
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///app.db")

    # Redis の場所（セッションと送信回数の記録に使う）。未設定なら Redis を使わない。
    REDIS_URL = os.environ.get("REDIS_URL")

    # セッション（Flask-Session でサーバー側に保存する）
    # SESSION_TYPE を指定しなければ、create_app() が REDIS_URL を見て自動で選ぶ
    # （Redis があれば Redis、なければ instance/sessions フォルダ）。
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)  # 操作がなければ12時間で期限切れ
    SESSION_KEY_PREFIX = "session:"

    # セッション Cookie の設定
    SESSION_COOKIE_HTTPONLY = True  # JavaScript から読めないようにする
    SESSION_COOKIE_SAMESITE = "Lax"  # 他サイトからの送信に Cookie を付けない
    SESSION_COOKIE_SECURE = True  # HTTPS のときだけ Cookie を送る

    # 「ログインしたままにする」用の Cookie の設定（セッション Cookie と同じ方針）
    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = True

    # パスワードのハッシュ化（Argon2id）の強さ。RFC 9106 の推奨値
    # （1回あたり 64MB のメモリと数十ミリ秒の計算を使い、総当たりを難しくする）。
    # 値を強くすると、既存ユーザーは次のログイン時に自動で保存し直される。
    ARGON2_TIME_COST = RFC_9106_LOW_MEMORY.time_cost  # 3
    ARGON2_MEMORY_COST = RFC_9106_LOW_MEMORY.memory_cost  # 65536 KiB = 64MB
    ARGON2_PARALLELISM = RFC_9106_LOW_MEMORY.parallelism  # 4

    # リクエストの大きさの上限（巨大なデータを送りつけられるのを防ぐ）
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # 1MB

    # 送信回数の記録場所。複数ワーカーで共有するため、Redis があれば Redis を使う。
    RATELIMIT_STORAGE_URI = (
        os.environ.get("RATELIMIT_STORAGE_URI") or REDIS_URL or "memory://"
    )

    # アプリの前に置いたリバースプロキシ（nginx など、受付役のサーバー）の数。
    # 1 以上にすると、プロキシが付ける X-Forwarded-For などのヘッダーから
    # 本当の接続元の IP アドレスや https かどうかを読み取る（回数制限が正しく働く）。
    # プロキシを通さずに直接つながる状態で 1 以上にすると、ヘッダーを偽って
    # 回数制限をすり抜けられてしまうので、0（読み取らない）のままにすること。
    TRUSTED_PROXY_COUNT = _env_int("TRUSTED_PROXY_COUNT", 0)


class DevelopmentConfig(Config):
    """開発用（自分のパソコンの http://localhost で動かす）。"""

    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False

    # デバッグツールバー（FLASK_DEBUG=1 のときだけ表示される）
    # リダイレクトのたびに止まると PRG の流れが分かりにくいので、止めない
    DEBUG_TB_INTERCEPT_REDIRECTS = False


class ProductionConfig(Config):
    """本番用。"""

    # HTTPS で公開するのが前提。ローカルの Docker で http のまま試すときだけ
    # 環境変数 SESSION_COOKIE_SECURE=false で無効にできる。
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", True)
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE


class TestingConfig(Config):
    """自動テスト用。

    CSRF 対策や回数制限を切ってあるので、本番では絶対に使わないこと
    （APP_ENV では選べないようにしてある）。
    """

    TESTING = True
    # 起動のたびに作るランダムな鍵（コードに書いた鍵は、コードを見た人に知られてしまう）
    SECRET_KEY = secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"  # 使い捨てのデータベース
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = False  # CSRF のテストでは個別に有効にする
    RATELIMIT_ENABLED = False  # 回数制限のテストでは個別に有効にする
    RATELIMIT_STORAGE_URI = "memory://"
    # テストを速くするため、ハッシュ化を最小限の強さにする（本番では使わないこと）
    ARGON2_TIME_COST = 1
    ARGON2_MEMORY_COST = 8
    ARGON2_PARALLELISM = 1
    # セッションはメモリ上に保存（ファイルや Redis を使わない）
    SESSION_TYPE = "cachelib"
    SESSION_CACHELIB = SimpleCache()


# APP_ENV で選べる設定。TestingConfig は、まちがって本番で使われないように入れていない
# （テストでは create_app(TestingConfig) のように直接渡す）。
CONFIGS: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    """名前（未指定なら環境変数 APP_ENV）から設定クラスを返す。"""
    name = name or os.environ.get("APP_ENV", "production")
    try:
        return CONFIGS[name]
    except KeyError:
        choices = ", ".join(CONFIGS)
        raise ValueError(
            f"APP_ENV の値 '{name}' は使えません（{choices} のどれか）。"
        ) from None
