import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import func, select
from werkzeug.test import TestResponse

from fl_demonstro.accounts.models import User
from fl_demonstro.extensions import db
from tests.conftest import VALID_SIGNUP


def user_count(app: Flask) -> int:
    with app.app_context():
        return db.session.execute(select(func.count()).select_from(User)).scalar_one()


def stored_username(app: Flask, username: str) -> str | None:
    """データベースに保存されているユーザー名を返す（なければ None）。"""
    with app.app_context():
        user = User.find_by_username(username)
        return user.username if user else None


def signup(client: FlaskClient, **overrides: str) -> TestResponse:
    return client.post("/accounts/signup", data={**VALID_SIGNUP, **overrides})


def test_signup_page_shows_form(client: FlaskClient) -> None:
    response = client.get("/accounts/signup")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="username"' in html
    assert 'autocomplete="new-password"' in html
    # スマートフォンで先頭の文字が勝手に大文字にならないようにしている
    assert 'autocapitalize="none"' in html


def test_signup_success_redirects_to_done_page(app: Flask, client: FlaskClient) -> None:
    response = signup(client)

    # PRG: 成功したら完了ページへリダイレクトする
    assert response.status_code == 302
    assert response.headers["Location"] == "/accounts/signup/done"

    with app.app_context():
        user = User.find_by_username("taro")
        assert user is not None
        assert user.password_hash != VALID_SIGNUP["password"]  # そのまま保存しない
        assert user.check_password(VALID_SIGNUP["password"])


def test_done_page_shows_success_message(client: FlaskClient) -> None:
    response = signup(client, username="hanako")
    html = client.get(response.headers["Location"]).get_data(as_text=True)

    assert "hanako さん、登録が完了しました。" in html
    assert "alert-success" in html


def test_username_is_stripped(app: Flask, client: FlaskClient) -> None:
    signup(client, username="  jiro  ")

    assert stored_username(app, "jiro") == "jiro"


@pytest.mark.parametrize("username", ["abc", "taro2026", "123", "a" * 32])
def test_username_with_lowercase_letters_and_digits_is_accepted(
    app: Flask, client: FlaskClient, username: str
) -> None:
    assert signup(client, username=username).status_code == 302
    assert stored_username(app, username) == username


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"username": ""}, "ユーザー名を入力してください。"),
        ({"username": "ab"}, "3〜32文字"),
        ({"username": "a" * 33}, "3〜32文字"),
        ({"username": "taro yamada"}, "3〜32文字"),
        ({"username": "たろう"}, "3〜32文字"),
        # 大文字・記号・全角は使えない（半角英小文字と数字だけ）
        ({"username": "Taro"}, "半角英小文字（a〜z）と数字"),
        ({"username": "TARO"}, "半角英小文字（a〜z）と数字"),
        ({"username": "taro_1"}, "半角英小文字（a〜z）と数字"),
        ({"username": "taro.y"}, "半角英小文字（a〜z）と数字"),
        ({"username": "taro-1"}, "半角英小文字（a〜z）と数字"),
        ({"username": "ｔａｒｏ"}, "半角英小文字（a〜z）と数字"),
        ({"username": "taro\n"}, None),  # 改行は前後の空白として取り除かれ、登録できる
        (
            {"password": "short", "password_confirm": "short"},
            "パスワードは8〜128文字",
        ),
        (
            {"password": "x" * 129, "password_confirm": "x" * 129},
            "パスワードは8〜128文字",
        ),
        ({"password_confirm": "different-pass"}, "パスワードが一致しません。"),
        (
            {
                "password": "TaroTaro",
                "password_confirm": "TaroTaro",
                "username": "tarotaro",
            },
            "ユーザー名を含むパスワードは使えません。",
        ),
        (
            {"password": "Password123", "password_confirm": "Password123"},
            "よく使われているパスワードのため使えません。",
        ),
    ],
)
def test_signup_validation(
    app: Flask, client: FlaskClient, overrides: dict[str, str], message: str | None
) -> None:
    response = signup(client, **overrides)

    if message is None:
        assert response.status_code == 302
        return
    assert response.status_code == 400
    assert message in response.get_data(as_text=True)
    assert user_count(app) == 0


def test_duplicate_username_is_rejected(app: Flask, client: FlaskClient) -> None:
    signup(client, username="taro")
    response = signup(client, username="taro")

    assert response.status_code == 400
    assert "このユーザー名はすでに使われています。" in response.get_data(as_text=True)
    assert user_count(app) == 1


def test_password_is_not_echoed_back_on_error(client: FlaskClient) -> None:
    response = signup(client, username="")

    assert VALID_SIGNUP["password"] not in response.get_data(as_text=True)


def test_username_is_echoed_back_on_error(client: FlaskClient) -> None:
    response = signup(client, password_confirm="different-pass")

    assert 'value="taro"' in response.get_data(as_text=True)
