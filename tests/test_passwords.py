"""パスワードの保存（Argon2id）とパスワードポリシーのテスト。"""

import pytest
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash

from fl_demonstro.accounts.models import User
from fl_demonstro.accounts.passwords import (
    common_passwords,
    hash_password,
    needs_rehash,
    password_policy_error,
    verify_password,
)
from fl_demonstro.config import Config, TestingConfig
from fl_demonstro.extensions import db
from tests.conftest import PASSWORD, create_user, login

# ---------- 保存（ハッシュ化） ----------


def test_password_is_hashed_with_argon2id(app_ctx: Flask) -> None:
    password_hash = hash_password(PASSWORD)

    assert password_hash.startswith("$argon2id$")
    assert PASSWORD not in password_hash


def test_same_password_gives_different_hashes(app_ctx: Flask) -> None:
    # ソルトが毎回ランダムに付くので、同じパスワードでも保存される値は違う
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_verify_password(app_ctx: Flask) -> None:
    password_hash = hash_password(PASSWORD)

    assert verify_password(password_hash, PASSWORD)
    assert not verify_password(password_hash, "wrong-password")


@pytest.mark.parametrize("broken", ["", "not-a-hash", "$argon2id$broken", "scrypt:x"])
def test_verify_password_with_broken_hash_returns_false(
    app_ctx: Flask, broken: str
) -> None:
    assert not verify_password(broken, PASSWORD)


def test_production_uses_recommended_argon2_strength() -> None:
    # RFC 9106 の推奨値（64MB・3回・並列4）。OWASP の最低基準（19MB・2回）を上回る
    assert Config.ARGON2_MEMORY_COST == 65536
    assert Config.ARGON2_TIME_COST == 3
    assert Config.ARGON2_PARALLELISM == 4


def test_stronger_settings_need_rehash(app: Flask) -> None:
    class StrongerConfig(TestingConfig):
        ARGON2_TIME_COST = TestingConfig.ARGON2_TIME_COST + 1

    with app.app_context():
        old_hash = hash_password(PASSWORD)
        assert not needs_rehash(old_hash)

    app.config.from_object(StrongerConfig)
    with app.app_context():
        assert needs_rehash(old_hash)


# ---------- 以前の方式（scrypt）からの移行 ----------


def _create_legacy_user(app: Flask, username: str = "taro") -> int:
    """以前の方式（Werkzeug の scrypt）で保存されたユーザーを作る。"""
    with app.app_context():
        user = User(username=username, password_hash=generate_password_hash(PASSWORD))
        db.session.add(user)
        db.session.commit()
        return user.id


def _stored_hash(app: Flask, user_id: int) -> str:
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user is not None
        return user.password_hash


def test_legacy_scrypt_hash_still_works(app_ctx: Flask) -> None:
    legacy = generate_password_hash(PASSWORD)

    assert legacy.startswith("scrypt:")
    assert verify_password(legacy, PASSWORD)
    assert not verify_password(legacy, "wrong-password")
    assert needs_rehash(legacy)


def test_legacy_hash_is_upgraded_on_login(app: Flask, client: FlaskClient) -> None:
    user_id = _create_legacy_user(app)

    assert login(client).status_code == 302
    new_hash = _stored_hash(app, user_id)
    assert new_hash.startswith("$argon2id$")

    # 保存し直したあとも同じパスワードでログインできる
    client.post("/accounts/logout")
    assert login(client).status_code == 302


def test_legacy_hash_is_not_upgraded_on_failed_login(
    app: Flask, client: FlaskClient
) -> None:
    user_id = _create_legacy_user(app)
    before = _stored_hash(app, user_id)

    assert login(client, password="wrong-password").status_code == 400
    assert _stored_hash(app, user_id) == before


def test_current_hash_is_not_rewritten_on_login(
    app: Flask, client: FlaskClient
) -> None:
    user_id = create_user(app)
    before = _stored_hash(app, user_id)

    login(client)

    assert _stored_hash(app, user_id) == before


# ---------- パスワードポリシー ----------


def test_common_password_list_is_loaded() -> None:
    passwords = common_passwords()

    assert len(passwords) > 40000
    assert "password123" in passwords
    assert all(len(p) >= 8 for p in list(passwords)[:1000])


@pytest.mark.parametrize(
    ("password", "username", "message"),
    [
        ("password123", None, "よく使われているパスワード"),
        (
            "PASSWORD123",
            None,
            "よく使われているパスワード",
        ),  # 大文字・小文字は区別しない
        ("qwertyuiop", None, "よく使われているパスワード"),
        ("iloveyou", None, "よく使われているパスワード"),
        ("taro2024!", "taro", "ユーザー名を含む"),
        ("my-TARO-pass", "Taro", "ユーザー名を含む"),
        ("zzzzzzzz", None, "単純なパスワード"),
        ("abababab", None, "単純なパスワード"),
        ("bcdefghij", None, "連続した文字"),
        ("98765432", None, "連続した文字"),
    ],
)
def test_weak_passwords_are_rejected(
    password: str, username: str | None, message: str
) -> None:
    error = password_policy_error(password, username)

    assert error is not None
    assert message in error


@pytest.mark.parametrize(
    "password",
    [
        PASSWORD,  # correct-horse
        "blue whale sings",  # 空白を含む文章のようなパスワードも使える
        "とても長い日本語のパスワード",  # 日本語も使える
        "Tr0ub4dor&3x",
    ],
)
def test_good_passwords_are_accepted(password: str) -> None:
    assert password_policy_error(password, "taro") is None


def test_signup_rejects_common_password(app: Flask, client: FlaskClient) -> None:
    response = client.post(
        "/accounts/signup",
        data={
            "username": "hanako",
            "password": "iloveyou",
            "password_confirm": "iloveyou",
        },
    )

    assert response.status_code == 400
    assert "よく使われているパスワード" in response.get_data(as_text=True)


def test_signup_page_explains_policy(client: FlaskClient) -> None:
    html = client.get("/accounts/signup").get_data(as_text=True)

    assert "記号は不要です" in html
    assert "よく使われるパスワード" in html
