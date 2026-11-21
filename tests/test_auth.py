"""ログイン・ログアウトのテスト。"""

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_login import current_user
from werkzeug.test import TestResponse

from fl_demonstro.accounts.forms import LOGIN_FAILED
from tests.conftest import PASSWORD, create_user, login


def is_logged_in(client: FlaskClient) -> bool:
    with client.session_transaction() as session:
        return "_user_id" in session


def remember_cookie_header(response: TestResponse) -> str | None:
    for header in response.headers.getlist("Set-Cookie"):
        if header.startswith("remember_token="):
            return header
    return None


# ---------- ログイン画面 ----------


def test_login_page_shows_form(client: FlaskClient) -> None:
    response = client.get("/accounts/login")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="username"' in html
    assert 'autocomplete="current-password"' in html
    assert 'name="remember"' in html
    assert 'autocapitalize="none"' in html


# ---------- ログイン成功 ----------


def test_login_success_redirects_to_index(app: Flask, client: FlaskClient) -> None:
    create_user(app)
    response = login(client)

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert is_logged_in(client)


def test_login_success_shows_message_and_username(
    app: Flask, client: FlaskClient
) -> None:
    create_user(app)
    html = client.get(login(client).headers["Location"]).get_data(as_text=True)

    assert "ログインしました。" in html
    assert "ようこそ、taro さん" in html
    assert "ログアウト" in html
    assert 'href="/accounts/login"' not in html  # ログイン中はログインリンクを出さない


def test_login_ignores_username_case(app: Flask, client: FlaskClient) -> None:
    # スマートフォンで先頭が大文字になってしまっても、ログインできる
    create_user(app)

    assert login(client, "Taro").status_code == 302


def test_current_user_is_loaded_from_session(app: Flask, client: FlaskClient) -> None:
    user_id = create_user(app)
    login(client)

    with client:
        client.get("/")
        assert current_user.is_authenticated
        assert current_user.id == user_id


# ---------- ログイン失敗 ----------


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("taro", "wrong-password"),  # パスワード違い
        ("hanako", PASSWORD),  # 存在しないユーザー
    ],
)
def test_login_failure_shows_same_message(
    app: Flask, client: FlaskClient, username: str, password: str
) -> None:
    create_user(app)
    response = login(client, username, password)

    # どちらが間違っていても同じメッセージ（ユーザー名の存在を推測させない）
    assert response.status_code == 400
    assert LOGIN_FAILED in response.get_data(as_text=True)
    assert not is_logged_in(client)


@pytest.mark.parametrize(
    ("username", "password", "message"),
    [
        ("", PASSWORD, "ユーザー名を入力してください。"),
        ("taro", "", "パスワードを入力してください。"),
        ("taro", "x" * 129, LOGIN_FAILED),
    ],
)
def test_login_validation(
    app: Flask, client: FlaskClient, username: str, password: str, message: str
) -> None:
    create_user(app)
    response = login(client, username, password)

    assert response.status_code == 400
    assert message in response.get_data(as_text=True)
    assert not is_logged_in(client)


def test_password_is_not_echoed_back(app: Flask, client: FlaskClient) -> None:
    create_user(app)
    response = login(client, password="wrong-password")

    assert "wrong-password" not in response.get_data(as_text=True)


# ---------- ログイン後の移動先（?next=） ----------


def test_login_redirects_to_safe_next(app: Flask, client: FlaskClient) -> None:
    create_user(app)
    response = login(client, query="?next=/accounts/signup/done")

    assert response.headers["Location"] == "/accounts/signup/done"


@pytest.mark.parametrize(
    "next_url",
    [
        "https://evil.example.com/",
        "//evil.example.com/",
        "/\\evil.example.com/",
        "javascript:alert(1)",
    ],
)
def test_login_ignores_unsafe_next(
    app: Flask, client: FlaskClient, next_url: str
) -> None:
    create_user(app)
    response = client.post(
        "/accounts/login",
        query_string={"next": next_url},
        data={"username": "taro", "password": PASSWORD},
    )

    assert response.headers["Location"] == "/"


def test_login_form_keeps_next_parameter(client: FlaskClient) -> None:
    html = client.get("/accounts/login?next=/somewhere").get_data(as_text=True)

    assert 'action="/accounts/login?next=/somewhere"' in html


# ---------- ログインしたままにする ----------


def test_remember_me_sets_cookie(app: Flask, client: FlaskClient) -> None:
    create_user(app)
    response = login(client, remember="y")

    cookie = remember_cookie_header(response)
    assert cookie is not None
    assert "HttpOnly" in cookie


def test_without_remember_me_no_cookie(app: Flask, client: FlaskClient) -> None:
    create_user(app)

    assert remember_cookie_header(login(client)) is None


# ---------- ログイン中の人への対応 ----------


@pytest.mark.parametrize("path", ["/accounts/login", "/accounts/signup"])
def test_logged_in_user_is_redirected_from_login_and_signup(
    app: Flask, client: FlaskClient, path: str
) -> None:
    create_user(app)
    login(client)
    response = client.get(path)

    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_logged_in_pages_are_not_cached(app: Flask, client: FlaskClient) -> None:
    create_user(app)
    assert "no-store" not in client.get("/").headers.get("Cache-Control", "")

    login(client)

    assert client.get("/").headers["Cache-Control"] == "no-store"


# ---------- ログアウト ----------


def test_logout(app: Flask, client: FlaskClient) -> None:
    create_user(app)
    login(client)
    response = client.post("/accounts/logout")

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert not is_logged_in(client)
    html = client.get("/").get_data(as_text=True)
    assert "ログアウトしました。" in html
    assert 'href="/accounts/login"' in html


def test_logout_clears_remember_cookie(app: Flask, client: FlaskClient) -> None:
    create_user(app)
    login(client, remember="y")
    response = client.post("/accounts/logout")

    # remember_token を消す（有効期限切れにする）指示が出ている
    cookie = remember_cookie_header(response)
    assert cookie is not None
    assert "Expires=Thu, 01 Jan 1970" in cookie
    assert client.get_cookie("remember_token") is None
    assert "ようこそ、taro さん" not in client.get("/").get_data(as_text=True)


def test_logout_requires_post(app: Flask, client: FlaskClient) -> None:
    create_user(app)
    login(client)

    assert client.get("/accounts/logout").status_code == 405
    assert is_logged_in(client)


def test_logout_requires_login(client: FlaskClient) -> None:
    response = client.post("/accounts/logout")

    # ログインしていなければログイン画面へ（元のページを next に付けて）
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/accounts/login?next=")
    html = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "このページを見るにはログインしてください。" in html


# ---------- サインアップからの流れ ----------


def test_signup_then_login(client: FlaskClient) -> None:
    client.post(
        "/accounts/signup",
        data={"username": "jiro", "password": PASSWORD, "password_confirm": PASSWORD},
    )
    done = client.get("/accounts/signup/done").get_data(as_text=True)
    assert 'href="/accounts/login"' in done

    assert login(client, "jiro").status_code == 302
