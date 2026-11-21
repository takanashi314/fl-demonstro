"""テスト全体で使う共通の準備（フィクスチャ）。"""

import re
from collections.abc import Iterator
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from fl_demonstro import create_app
from fl_demonstro.accounts.models import User
from fl_demonstro.config import Config, TestingConfig
from fl_demonstro.extensions import db


def make_app(config_class: type[Config] = TestingConfig) -> Flask:
    """テスト用のアプリを作り、空のデータベースを用意する。"""
    app = create_app(config_class)
    with app.app_context():
        db.create_all()
    return app


@pytest.fixture
def app() -> Iterator[Flask]:
    """テスト用のアプリ。

    アプリコンテキストは開きっぱなしにしない。開いたままだとリクエスト同士で
    g（Flask-Login のログイン中ユーザーや CSRF トークンの置き場所）が共有され、
    本番では起きない結果になってしまうため。
    データベースを直接触るときは、その場で with app.app_context(): を使う。
    """
    app = make_app()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def app_ctx(app: Flask) -> Iterator[Flask]:
    """アプリコンテキストを開いた状態にする（リクエストを送らないテスト用）。"""
    with app.app_context():
        yield app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


def get_csrf_token(html: str) -> str:
    """ページの HTML から CSRF トークン（合言葉）を取り出す。"""
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match, "CSRF トークンが見つかりません"
    return match.group(1)


VALID_SIGNUP = {
    "username": "taro",
    "password": "correct-horse",
    "password_confirm": "correct-horse",
}

PASSWORD = VALID_SIGNUP["password"]


def create_user(app: Flask, username: str = "taro", password: str = PASSWORD) -> int:
    """データベースにユーザーを直接作り、その ID を返す。"""
    with app.app_context():
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


def login(
    client: FlaskClient,
    username: str = "taro",
    password: str = PASSWORD,
    **extra: Any,
) -> TestResponse:
    """ログインフォームを送信する。"""
    query = extra.pop("query", "")
    return client.post(
        f"/accounts/login{query}",
        data={"username": username, "password": password, **extra},
    )
