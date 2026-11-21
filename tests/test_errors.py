from typing import NoReturn

import pytest
from flask import abort
from flask.testing import FlaskClient

from fl_demonstro.config import TestingConfig
from tests.conftest import make_app


def test_404_page_is_japanese_with_navbar(client: FlaskClient) -> None:
    response = client.get("/no-such-page")

    assert response.status_code == 404
    html = response.get_data(as_text=True)
    assert "ページが見つかりません" in html
    assert "navbar" in html


def test_405_keeps_allow_header(client: FlaskClient) -> None:
    response = client.post("/")

    assert response.status_code == 405
    assert "この操作はできません" in response.get_data(as_text=True)
    assert "GET" in response.headers["Allow"]


def test_413_when_request_is_too_large(client: FlaskClient) -> None:
    response = client.post("/accounts/signup", data={"username": "a" * (1024 * 1024)})

    assert response.status_code == 413
    assert "送信データが大きすぎます" in response.get_data(as_text=True)


class NoPropagateConfig(TestingConfig):
    # テスト中もエラーを外に投げず、本番と同じように 500 画面を出す
    PROPAGATE_EXCEPTIONS = False


@pytest.mark.parametrize("code", [403, 500])
def test_other_error_pages(code: int) -> None:
    app = make_app(NoPropagateConfig)

    @app.get("/raise")
    def raise_error() -> NoReturn:
        abort(code)

    response = app.test_client().get("/raise")

    assert response.status_code == code
    assert "alert-danger" in response.get_data(as_text=True)


def test_unexpected_exception_shows_500_page() -> None:
    app = make_app(NoPropagateConfig)

    @app.get("/boom")
    def boom() -> NoReturn:
        raise RuntimeError("予期しないエラー")

    response = app.test_client().get("/boom")

    assert response.status_code == 500
    html = response.get_data(as_text=True)
    assert "サーバーでエラーが発生しました" in html
    assert "予期しないエラー" not in html  # 内部の情報を画面に出さない
