"""サーバー側セッション（Flask-Session）のテスト。"""

from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from fl_demonstro import create_app
from fl_demonstro.config import TestingConfig
from tests.conftest import PASSWORD, MakeApp, create_user, get_csrf_token, login


class CSRFEnabledConfig(TestingConfig):
    WTF_CSRF_ENABLED = True  # GET でセッションが作られるようにする


def session_cookie(client: FlaskClient) -> str | None:
    cookie = client.get_cookie("session")
    return cookie.value if cookie else None


def shows_logged_in(client: FlaskClient, username: str = "taro") -> bool:
    return f"ようこそ、{username} さん" in client.get("/").get_data(as_text=True)


def test_cookie_holds_only_session_id(app: Flask, client: FlaskClient) -> None:
    create_user(app)
    login(client)

    # Cookie にはランダムな ID だけが入り、ユーザー ID などの中身は入らない
    value = session_cookie(client)
    assert value is not None
    assert "." not in value  # Flask 標準の「署名付きの中身」の形ではない
    assert len(value) >= 40


def _plant_attacker_session(app: Flask) -> tuple[FlaskClient, FlaskClient, str]:
    """攻撃者がサイトを訪れて「本物のセッション ID」を手に入れ、
    それを利用者のブラウザに仕込んだ状況を作る。"""
    attacker = app.test_client()
    attacker.get("/accounts/login")  # CSRF トークンがセッションに保存される
    attacker_sid = session_cookie(attacker)
    assert attacker_sid is not None

    victim = app.test_client()
    victim.set_cookie("session", attacker_sid)
    return attacker, victim, attacker_sid


def _login_with_csrf(client: FlaskClient) -> TestResponse:
    token = get_csrf_token(client.get("/accounts/login").get_data(as_text=True))
    return client.post(
        "/accounts/login",
        data={"username": "taro", "password": PASSWORD, "csrf_token": token},
    )


def test_session_id_changes_on_login(make_app: MakeApp) -> None:
    app = make_app(CSRFEnabledConfig)
    create_user(app)
    _, victim, attacker_sid = _plant_attacker_session(app)

    assert _login_with_csrf(victim).status_code == 302
    assert session_cookie(victim) != attacker_sid


def test_attacker_session_is_not_logged_in_after_victim_login(
    make_app: MakeApp,
) -> None:
    # セッション固定攻撃：ID を新しくしないと、攻撃者もログイン状態になってしまう
    app = make_app(CSRFEnabledConfig)
    create_user(app)
    attacker, victim, _ = _plant_attacker_session(app)

    assert _login_with_csrf(victim).status_code == 302
    assert shows_logged_in(victim)
    assert not shows_logged_in(attacker)


def _remember_cookie_value(app: Flask) -> str:
    """「ログインしたままにする」でログインし、その Cookie の値を返す。"""
    client = app.test_client()
    token = get_csrf_token(client.get("/accounts/login").get_data(as_text=True))
    client.post(
        "/accounts/login",
        data={
            "username": "taro",
            "password": PASSWORD,
            "remember": "y",
            "csrf_token": token,
        },
    )
    cookie = client.get_cookie("remember_token")
    assert cookie is not None
    return cookie.value


def _victim_with_remember_cookie_and_planted_session(
    make_app: MakeApp,
) -> tuple[FlaskClient, FlaskClient, str]:
    """被害者のセッションは期限切れで「ログインしたままにする」の Cookie だけがあり、
    そこへ攻撃者のセッション ID が仕込まれた状況を作る。"""
    app = make_app(CSRFEnabledConfig)
    create_user(app)
    remember = _remember_cookie_value(app)
    attacker, victim, attacker_sid = _plant_attacker_session(app)
    victim.set_cookie("remember_token", remember)
    return attacker, victim, attacker_sid


def test_session_id_changes_on_remember_cookie_login(make_app: MakeApp) -> None:
    _, victim, attacker_sid = _victim_with_remember_cookie_and_planted_session(make_app)

    assert shows_logged_in(victim)  # Cookie からログイン状態が戻る
    assert session_cookie(victim) != attacker_sid


def test_attacker_session_is_not_logged_in_after_remember_cookie_login(
    make_app: MakeApp,
) -> None:
    attacker, victim, _ = _victim_with_remember_cookie_and_planted_session(make_app)

    assert shows_logged_in(victim)
    assert not shows_logged_in(attacker)


def test_planted_csrf_token_is_discarded_on_remember_cookie_login(
    make_app: MakeApp,
) -> None:
    # 攻撃者は、仕込んだセッションの CSRF の合言葉を知っている
    attacker, victim, _ = _victim_with_remember_cookie_and_planted_session(make_app)
    attacker_token = get_csrf_token(
        attacker.get("/accounts/login").get_data(as_text=True)
    )

    assert shows_logged_in(victim)
    # その合言葉では、被害者になりすまして送信（ここではログアウト）できない
    response = victim.post("/accounts/logout", data={"csrf_token": attacker_token})
    assert response.status_code == 400
    assert shows_logged_in(victim)


def test_logout_invalidates_stolen_session_cookie(app: Flask) -> None:
    create_user(app)
    owner = app.test_client()
    login(owner)

    # Cookie を盗まれた状況：盗んだ人もログイン状態になってしまう
    thief = app.test_client()
    stolen = session_cookie(owner)
    assert stolen is not None
    thief.set_cookie("session", stolen)
    assert shows_logged_in(thief)

    # 本人がログアウトすると、サーバー側のセッションが消えるので盗んだ Cookie も無効になる
    owner.post("/accounts/logout")
    assert not shows_logged_in(thief)


@pytest.mark.parametrize(
    ("redis_url", "expected"),
    [
        (None, "cachelib"),
        ("redis://localhost:6379/0", "redis"),
    ],
)
def test_session_storage_is_chosen_from_redis_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    redis_url: str | None,
    expected: str,
) -> None:
    class Config(TestingConfig):
        # 自動で選ばせるため、わざと未設定にする
        SESSION_TYPE = None  # type: ignore[assignment]
        SESSION_CACHELIB = None  # type: ignore[assignment]
        REDIS_URL = redis_url

    # instance フォルダを一時フォルダにして、実際のフォルダを汚さない
    monkeypatch.setenv("INSTANCE_PATH", str(tmp_path))
    app = create_app(Config)

    assert app.config["SESSION_TYPE"] == expected
