import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

from fl_demonstro.accounts.models import User
from fl_demonstro.extensions import db


def add_user(username: str, password: str = "correct-horse") -> User:
    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def test_password_hashing(app_ctx: Flask) -> None:
    user = add_user("taro")

    assert user.check_password("correct-horse")
    assert not user.check_password("wrong-password")


def test_find_by_username_ignores_case_of_input(app_ctx: Flask) -> None:
    taro = add_user("taro")

    assert User.find_by_username("taro") is taro
    assert User.find_by_username("TARO") is taro
    assert User.find_by_username("hanako") is None


def test_database_rejects_duplicate_username(app_ctx: Flask) -> None:
    # フォームのチェックをすり抜けても、データベースが重複を防ぐ
    add_user("taro")

    with pytest.raises(IntegrityError):
        add_user("taro")


@pytest.mark.parametrize("username", ["Taro", "TARO"])
def test_username_with_uppercase_cannot_be_stored(
    app_ctx: Flask, username: str
) -> None:
    # フォームを通らずに作っても、大文字の混ざった名前は保存できない
    with pytest.raises(ValueError, match="小文字"):
        User(username=username)


def test_created_at_is_set(app_ctx: Flask) -> None:
    assert add_user("taro").created_at is not None


def test_authenticate(app_ctx: Flask) -> None:
    taro = add_user("taro")

    assert User.authenticate("taro", "correct-horse") is taro
    assert User.authenticate("Taro", "correct-horse") is taro
    assert User.authenticate("taro", "wrong-password") is None
    assert User.authenticate("nobody", "correct-horse") is None


def test_user_is_flask_login_compatible(app_ctx: Flask) -> None:
    user = add_user("taro")

    assert user.is_authenticated
    assert user.is_active
    assert user.get_id() == str(user.id)


def test_load_user(app_ctx: Flask) -> None:
    from fl_demonstro.accounts.models import load_user

    user = add_user("taro")

    assert load_user(str(user.id)) == user
    assert load_user("9999") is None
    assert load_user("not-a-number") is None
