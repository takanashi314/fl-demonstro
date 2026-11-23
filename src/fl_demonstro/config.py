"""アプリの設定。

環境（開発・本番・テスト）ごとに設定クラスを分けている。
開発用と本番用は、環境変数 APP_ENV で選ぶ（未設定なら本番用）。
テスト用は自動テストの中で直接使い、APP_ENV では選べないようにしている。

設定の読み込まれ方：
- create_app() が app.config.from_object(設定クラス) で読み込む。
  設定になるのは大文字の名前だけ（_env_bool などの小文字の名前は読まれない）。
- 子クラスは親クラスの値を引き継ぐので、変えたい値だけを書けばよい。
- クラスの中の式（os.environ.get(...) など）は、このファイルが import されたときに
  1回だけ評価される。環境変数は、そのときの値が使われる
  （flask コマンドは、アプリを読み込む前に .env の中身を環境変数に入れる）。
"""

import os
import secrets
from datetime import timedelta

from argon2.profiles import RFC_9106_LOW_MEMORY
from cachelib import SimpleCache


def _env_bool(name: str, default: bool) -> bool:
    """環境変数を True / False として読む。

    「1」「true」「yes」「on」なら True（大文字・小文字と前後の空白は問わない）。
    それ以外の値（「false」「0」や書き間違いなど）は False。未設定なら default。
    """
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    """環境変数を 0 以上の整数として読む。

    未設定・空文字なら default。整数として読めない値ならエラーにして起動を止める
    （書き間違いに気づかないまま、意図しない値で動くのを防ぐ）。
    """
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    # isdigit() は全角の数字（"２"）も数字とみなすので、isascii() で半角に限る。
    # "-1" や "1.5" は、"-" と "." が数字ではないので isdigit() が False になる。
    if not (value.isascii() and value.isdigit()):
        raise ValueError(f"{name} は 0 以上の整数にしてください（今の値: {value!r}）。")
    return int(value)


class Config:
    """全環境で共通の設定。"""

    # 署名に使う秘密の鍵。CSRF トークン（Flask-WTF）や、
    # 「ログインしたままにする」の Cookie（Flask-Login）を偽造されないようにする。
    # 必ず .env などで設定すること（未設定のときは create_app() がエラーにして起動を止める）。
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # データベースの場所。未設定なら instance フォルダの app.db（SQLite）を使う。
    # （sqlite:///app.db のような相対パスは、Flask-SQLAlchemy が
    #   instance フォルダからの位置として扱う）
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///app.db")

    # Redis の場所（セッションと送信回数の記録に使う）。未設定なら Redis を使わない。
    REDIS_URL = os.environ.get("REDIS_URL")

    # セッション（Flask-Session でサーバー側に保存する）
    # SESSION_TYPE を指定しなければ、create_app() が REDIS_URL を見て自動で選ぶ
    # （Redis があれば Redis、なければ instance/sessions フォルダ）。
    # Flask-Session は既定でセッションに期限を付ける（SESSION_PERMANENT = True）。
    # 期限はリクエストのたびに延びる（SESSION_REFRESH_EACH_REQUEST = True）ので、
    # 「最後の操作から12時間」で切れる。
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)  # 操作がなければ12時間で期限切れ
    # Redis のキーの頭に付ける文字（キーは「session:<セッション ID>」になる）
    SESSION_KEY_PREFIX = "session:"

    # セッション Cookie の設定
    SESSION_COOKIE_HTTPONLY = True  # JavaScript から読めないようにする
    # 他サイトからの POST や、画像・iframe などの読み込みには Cookie を付けない
    # （他サイトのリンクから移動してきたときの GET には付ける）
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = True  # HTTPS のときだけ Cookie を送る

    # 「ログインしたままにする」用の Cookie の設定（セッション Cookie と同じ方針）
    # Flask-Login が使う。セッションが切れても、この Cookie で14日間はログイン状態を戻せる。
    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = True

    # パスワードのハッシュ化（Argon2id）の強さ。RFC 9106 の推奨値
    # （1回あたり 64MB のメモリと数十ミリ秒の計算を使い、総当たりを難しくする）。
    # accounts/passwords.py がこの値を読んでハッシュ化する。
    # 値を強くすると、既存ユーザーは次のログイン時に自動で保存し直される。
    ARGON2_TIME_COST = RFC_9106_LOW_MEMORY.time_cost  # 3
    ARGON2_MEMORY_COST = RFC_9106_LOW_MEMORY.memory_cost  # 65536 KiB = 64MB
    ARGON2_PARALLELISM = RFC_9106_LOW_MEMORY.parallelism  # 4

    # リクエストの大きさの上限（巨大なデータを送りつけられるのを防ぐ）
    # 超えると 413 エラーになり、errors.py のエラー画面を出す。
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # 1MB

    # 送信回数の記録場所。複数ワーカーで共有するため、Redis があれば Redis を使う。
    # memory:// はプロセスごとの記録なので、gunicorn のワーカーが2つあると
    # 回数が別々に数えられ、制限が実質2倍に緩む。
    # 式の中の REDIS_URL は、このクラスを定義したときの値。子クラスで REDIS_URL だけを
    # 上書きしても、この値は変わらない（両方を書く必要がある）。
    RATELIMIT_STORAGE_URI = (
        os.environ.get("RATELIMIT_STORAGE_URI") or REDIS_URL or "memory://"
    )

    # アプリの前に置いたリバースプロキシ（nginx など、受付役のサーバー）の数。
    # 1 以上にすると、プロキシが付ける X-Forwarded-For などのヘッダーから
    # 本当の接続元の IP アドレスや https かどうかを読み取る（回数制限が正しく働く）。
    # プロキシを通さずに直接つながる状態で 1 以上にすると、ヘッダーを偽って
    # 回数制限をすり抜けられてしまうので、0（読み取らない）のままにすること。
    # 実際の読み取りは、create_app() の _trust_reverse_proxy()（ProxyFix）が行う。
    TRUSTED_PROXY_COUNT = _env_int("TRUSTED_PROXY_COUNT", 0)


# ===== 開発・本番・テストの違い =====
# 3つとも Config を継承し、
# 変えたい設定だけを書き換えている（書いていない設定は Config と同じ）。
# 違いには、クラスで決まるものと、環境変数（.env・compose.yaml）で決まるものがある。
# 以下は、このプロジェクトのふつうの動かし方
# （開発は手元で flask run、本番は docker compose up、テストは pytest）での違い。
#
# - 選ばれ方
#     開発：.env の APP_ENV=development（flask コマンドが .env を読む）
#     本番：Dockerfile の ENV APP_ENV=production。APP_ENV が未設定のときも本番になる
#     テスト：APP_ENV では選べない。テストが make_app(TestingConfig) のように直接渡す
# - Cookie の Secure（HTTPS のときだけ Cookie を送る）
#     開発：なし（http://localhost で動かすため）
#     本番：あり。
#           ただし compose.yaml では、手元で http のまま試すために false にしている
#     テスト：なし
# - データベース
#     開発：instance/app.db（Config のまま）
#     本番：/app/instance/app.db（Config のまま。
#           場所は INSTANCE_PATH、ファイルはボリュームに残る）
#     テスト：メモリ上の SQLite（テストごとに作って捨てる）
# - セッションと送信回数の記録の置き場所
#     開発：.env に REDIS_URL がないので、
#           セッションは instance/sessions のファイル、回数はメモリ
#     本番：compose.yaml の REDIS_URL で、
#           どちらも Redis（gunicorn のワーカー2つで共有する）
#     テスト：どちらもメモリ（Redis もファイルも使わない）
# - CSRF 対策と送信回数の制限
#     開発・本番：有効
#     テスト：無効（確かめるテストだけ、このクラスを継承して有効にする）
# - パスワードのハッシュ化の強さ
#     開発・本番：RFC 9106 の推奨値（Config のまま）
#     テスト：最小（テストを速くするため）
# - SECRET_KEY
#     開発：.env の値
#     本番：.env の値を、compose.yaml が環境変数として渡す
#     テスト：起動のたびに作る乱数
# - デバッグ
#     開発：.env の FLASK_DEBUG=1 で、flask run がデバッグモードになり、
#           デバッグツールバーも出る
#     本番：なし（gunicorn で動かし、デバッグツールバーはイメージに入っていない）
#     テスト：TESTING=True。ビューで起きた例外を、そのままテストに伝える


class DevelopmentConfig(Config):
    """開発用（自分のパソコンの http://localhost で動かす）。

    手元で flask run するときに使う（.env の APP_ENV=development で選ばれる）。
    Config から変えているのは、Cookie の Secure を切ることと、
    デバッグツールバーの設定だけ。
    データベース・セッション・回数制限などは Config のままなので、
    .env に DATABASE_URL や REDIS_URL を書かなければ、instance フォルダとメモリを使う。
    """

    # http で動かすので、Secure（HTTPS のときだけ送る）を切る
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False

    # デバッグツールバー（FLASK_DEBUG=1 のときだけ表示される）
    # リダイレクトのたびに止まると PRG（POST → リダイレクト → GET）の流れが
    # 分かりにくいので、止めない
    DEBUG_TB_INTERCEPT_REDIRECTS = False


class ProductionConfig(Config):
    """本番用。

    Docker（gunicorn）で動かすときに使う
    （Dockerfile の APP_ENV=production で選ばれる。APP_ENV が未設定のときもこれ）。
    ほとんど Config のままで、変えているのは、
    Cookie の Secure を環境変数で切り替えられるようにすることだけ。
    秘密の鍵（SECRET_KEY）や Redis の場所（REDIS_URL）は、
    compose.yaml から環境変数で受け取る。
    """

    # HTTPS で公開するのが前提。ローカルの Docker で http のまま試すときだけ
    # 環境変数 SESSION_COOKIE_SECURE=false で無効にできる。
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", True)
    # 「ログインしたままにする」の Cookie も、上の行と同じ値にそろえる
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE


class TestingConfig(Config):
    """自動テスト用。

    pytest で使う。
    APP_ENV では選べず、テストが make_app(TestingConfig) のように直接渡す。
    テストを速く、外のもの（Redis・ファイル）に頼らず、
    毎回同じ結果になるようにするため、多くの設定を変えている。
    CSRF 対策や回数制限を切ってあるので、本番では絶対に使わないこと
    （APP_ENV では選べないようにしてある）。
    CSRF や回数制限を確かめるテストは、このクラスを継承して、その設定だけを有効にする
    （tests/test_security.py の CSRFEnabledConfig など）。
    """

    # Flask のテストモード。ビューで起きた例外を 500 画面にせず、そのままテストに伝える
    # （PROPAGATE_EXCEPTIONS を指定しないとき）。デバッグツールバーも出さない。
    TESTING = True
    # 起動のたびに作るランダムな鍵（コードに書いた鍵は、コードを見た人に知られてしまう）
    # import されたときに1回だけ作られるので、1回のテスト実行の中では同じ値になる。
    # テスト用に設定クラスを作るときも、この値（TestingConfig.SECRET_KEY）を使う。
    SECRET_KEY = secrets.token_hex(32)
    # 使い捨てのデータベース（接続の中にだけあり、接続を閉じると消える。docs/04.md）
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
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
    # SimpleCache() はクラスを定義したときに1つだけ作られ、TestingConfig（と子クラス）で
    # 作ったすべてのアプリで共有される。セッション ID はランダムなので、
    # テスト同士でセッションが混ざることはない。
    SESSION_TYPE = "cachelib"
    SESSION_CACHELIB = SimpleCache()


# APP_ENV で選べる設定。TestingConfig は、まちがって本番で使われないように入れていない
# （テストでは make_app(TestingConfig) のように直接渡す）。
CONFIGS: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    """名前（未指定なら環境変数 APP_ENV）から設定クラスを返す。"""
    # name が空文字のときも、未指定と同じく APP_ENV を見る
    name = name or os.environ.get("APP_ENV", "production")
    try:
        return CONFIGS[name]
    except KeyError:
        choices = ", ".join(CONFIGS)
        # from None：元の KeyError を表示せず、分かりやすい ValueError だけを見せる
        raise ValueError(
            f"APP_ENV の値 '{name}' は使えません（{choices} のどれか）。"
        ) from None
