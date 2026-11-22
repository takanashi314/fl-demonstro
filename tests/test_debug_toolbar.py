"""デバッグツールバー（開発用）のテスト。"""

from flask.testing import FlaskClient

from fl_demonstro.config import DevelopmentConfig, ProductionConfig, TestingConfig
from tests.conftest import MakeApp


class DebugConfig(DevelopmentConfig):
    DEBUG = True  # FLASK_DEBUG=1 と同じ状態
    SECRET_KEY = TestingConfig.SECRET_KEY
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SESSION_TYPE = TestingConfig.SESSION_TYPE
    SESSION_CACHELIB = TestingConfig.SESSION_CACHELIB


class ProductionTestConfig(ProductionConfig):
    SECRET_KEY = TestingConfig.SECRET_KEY
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SESSION_TYPE = TestingConfig.SESSION_TYPE
    SESSION_CACHELIB = TestingConfig.SESSION_CACHELIB


def test_toolbar_is_shown_in_debug_mode(make_app: MakeApp) -> None:
    response = make_app(DebugConfig).test_client().get("/")

    assert "flDebug" in response.get_data(as_text=True)
    # ツールバーが動くよう、開発時だけ CSP が緩くなっている
    assert "'unsafe-inline'" in response.headers["Content-Security-Policy"]


def test_toolbar_does_not_intercept_redirects(make_app: MakeApp) -> None:
    response = (
        make_app(DebugConfig)
        .test_client()
        .post("/accounts/login", data={"username": "nobody", "password": "x"})
    )

    # 途中で止まらず、普段どおりの応答が返る
    assert response.status_code in (400, 302)


def test_toolbar_is_not_shown_in_production(make_app: MakeApp) -> None:
    response = make_app(ProductionTestConfig).test_client().get("/")

    assert "flDebug" not in response.get_data(as_text=True)
    assert "'unsafe-inline'" not in response.headers["Content-Security-Policy"]


def test_toolbar_is_not_shown_in_tests(client: FlaskClient) -> None:
    response = client.get("/")

    assert "flDebug" not in response.get_data(as_text=True)
    assert "'unsafe-inline'" not in response.headers["Content-Security-Policy"]
