"""テスト全体で使う共通の準備（フィクスチャ）。

conftest.py は、pytest が自動で読み込むファイル。

- フィクスチャ（@pytest.fixture を付けた関数）は、import しなくても、テスト関数の引数に
  同じ名前を書くだけで使える。pytest がテストの前に呼び、戻り値を引数に渡す。
- フィクスチャ同士も、引数に名前を書けば使える（app フィクスチャは make_app を使う）。
- フィクスチャはテストごとに作り直されるので、あるテストの状態は次のテストに残らない。
- 補助関数（get_csrf_token・create_user・login）と定数は、普通に import して使う。
"""

import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from fl_demonstro import create_app
from fl_demonstro.accounts.models import User
from fl_demonstro.config import Config, TestingConfig
from fl_demonstro.extensions import db

# make_app フィクスチャが返す関数の型（設定クラスを受け取り、アプリを返す）
MakeApp = Callable[[type[Config]], Flask]


@pytest.fixture
def make_app() -> Iterator[MakeApp]:
    """テスト用のアプリを作る関数。アプリごとに空のデータベースを用意する。

    テストが終わったら、作ったアプリのデータベースを片付ける。
    engine.dispose() で接続を閉じないと、接続は GC に回収されるまで残り、
    そのとき ResourceWarning が出る（docs/04.md）。
    """
    apps: list[Flask] = []  # このテストで作ったアプリ（後片付けのために覚えておく）

    def _make_app(config_class: type[Config]) -> Flask:
        app = create_app(config_class)
        # モデルから直接テーブルを作る（マイグレーションは使わない。
        # マイグレーションが正しいかは test_migrations.py で別に確かめる）
        with app.app_context():
            db.create_all()
        apps.append(app)
        return app

    # yield の前が準備、後ろが後片付け。yield した値（アプリを作る関数）がテストに渡る。
    # 後片付けは、テストが失敗しても実行される。
    yield _make_app

    for app in apps:
        with app.app_context():
            db.session.remove()  # セッションを閉じ、使っていた接続をプールに返す
            db.drop_all()  # テーブルを消す
            db.engine.dispose()  # 接続を閉じる（in-memory の DB もここで消える）


@pytest.fixture
def app(make_app: MakeApp) -> Flask:
    """テスト用のアプリ。

    アプリコンテキストは開きっぱなしにしない。開いたままだとリクエスト同士で
    g（Flask-Login のログイン中ユーザーや CSRF トークンの置き場所）が共有され、
    本番では起きない結果になってしまうため。
    データベースを直接触るときは、その場で with app.app_context(): を使う。
    """
    # 後片付けは make_app フィクスチャがするので、ここでは作るだけ
    return make_app(TestingConfig)


@pytest.fixture
def app_ctx(app: Flask) -> Iterator[Flask]:
    """アプリコンテキストを開いた状態にする（リクエストを送らないテスト用）。

    with の中で yield するので、テストの間はコンテキストが開いたままになり、
    テストが終わると with を抜けて閉じる。
    """
    with app.app_context():
        yield app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """テスト用のクライアント。サーバーを起動せずにリクエストを送れる。

    同じクライアントで送ったリクエストの間では、Cookie（セッションなど）が引き継がれる。
    """
    return app.test_client()


def get_csrf_token(html: str) -> str:
    """ページの HTML から CSRF トークン（合言葉）を取り出す。"""
    # <input ... name="csrf_token" ... value="トークン"> の value の中身を取り出す。
    # [^>]* は「同じタグの中の、ほかの属性」、([^"]+) が取り出す値。
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    # 見つからなければ、ここでテストを失敗させる（文字列は失敗したときに表示される）
    assert match, "CSRF トークンが見つかりません"
    return match.group(1)


# サインアップのフォームに通る入力（パスワードはポリシーを満たし、確認欄と一致する）
VALID_SIGNUP = {
    "username": "taro",
    "password": "correct-horse",
    "password_confirm": "correct-horse",
}

# テストで使うパスワード（create_user() と login() の既定値）
PASSWORD = VALID_SIGNUP["password"]


def create_user(app: Flask, username: str = "taro", password: str = PASSWORD) -> int:
    """データベースにユーザーを直接作り、その ID を返す。"""
    # set_password() は設定（ARGON2_*）を current_app から読むので、
    # アプリコンテキストの中で呼ぶ
    with app.app_context():
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        # User オブジェクトではなく ID を返す。with を抜けるとセッションが閉じ、
        # オブジェクトの属性を読むとエラー（DetachedInstanceError）になることがあるため。
        return user.id


def login(
    client: FlaskClient,
    username: str = "taro",
    password: str = PASSWORD,
    **extra: Any,
) -> TestResponse:
    """ログインフォームを送信する。

    extra にはフォームに足す項目（remember="y" など）を渡す。
    query だけは特別で、URL に付ける文字（"?next=/..." など）として使う。
    """
    # query はフォームの項目ではないので、extra から取り出しておく
    query = extra.pop("query", "")
    return client.post(
        f"/accounts/login{query}",
        data={"username": username, "password": password, **extra},
    )
