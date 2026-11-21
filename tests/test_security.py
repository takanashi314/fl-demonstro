import re
from urllib.parse import urlsplit

from flask import Flask, request
from flask.testing import FlaskClient

from fl_demonstro.config import ProductionConfig, TestingConfig
from tests.conftest import VALID_SIGNUP, create_user, get_csrf_token, login, make_app


class CSRFEnabledConfig(TestingConfig):
    WTF_CSRF_ENABLED = True


class RateLimitEnabledConfig(TestingConfig):
    RATELIMIT_ENABLED = True


class BehindProxyConfig(RateLimitEnabledConfig):
    TRUSTED_PROXY_COUNT = 1  # リバースプロキシが1つ前にある


class ProductionTestConfig(ProductionConfig):
    SECRET_KEY = TestingConfig.SECRET_KEY
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    WTF_CSRF_ENABLED = False  # Cookie の確認に集中するため（CSRF は別のテストで確認）
    RATELIMIT_STORAGE_URI = "memory://"
    SESSION_TYPE = TestingConfig.SESSION_TYPE  # セッションはメモリ上に保存
    SESSION_CACHELIB = TestingConfig.SESSION_CACHELIB


def test_security_headers(client: FlaskClient) -> None:
    response = client.get("/")

    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    # http で動かすテスト環境では HSTS を付けない
    assert "Strict-Transport-Security" not in response.headers


def _csp_external_sources(csp: str) -> list[str]:
    return [word for word in csp.replace(";", " ").split() if word.startswith("https:")]


def test_csp_allows_only_specific_paths_of_external_sites(client: FlaskClient) -> None:
    # 外部のサイトは丸ごと許さず、決まった場所（パス）だけを許す
    # （jsDelivr のように誰でもファイルを置けるサイトを丸ごと許すと、守りが弱くなる）
    csp = client.get("/").headers["Content-Security-Policy"]
    sources = _csp_external_sources(csp)

    assert sources
    for source in sources:
        assert urlsplit(source).path not in ("", "/"), source


def test_external_files_in_page_are_allowed_by_csp(client: FlaskClient) -> None:
    # base.html で読み込んでいる外部のファイルが、すべて CSP で許されているか
    # （Bootstrap のバージョンを変えて CSP を直し忘れると、ここで気づける）
    response = client.get("/")
    urls = re.findall(
        r'(?:src|href)="(https://[^"]+)"', response.get_data(as_text=True)
    )
    sources = _csp_external_sources(response.headers["Content-Security-Policy"])

    assert urls
    for url in urls:
        assert any(url.startswith(source) for source in sources), url


def test_hsts_and_secure_cookie_in_production() -> None:
    app = make_app(ProductionTestConfig)
    create_user(app)
    response = login(app.test_client())  # ログインするとセッション Cookie が発行される

    assert "Strict-Transport-Security" in response.headers
    cookie = next(
        h for h in response.headers.getlist("Set-Cookie") if h.startswith("session=")
    )
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_post_without_csrf_token_is_rejected() -> None:
    client = make_app(CSRFEnabledConfig).test_client()
    response = client.post("/accounts/signup", data=VALID_SIGNUP)

    assert response.status_code == 400
    assert "送信できませんでした" in response.get_data(as_text=True)


def test_post_with_csrf_token_succeeds() -> None:
    client = make_app(CSRFEnabledConfig).test_client()
    token = get_csrf_token(client.get("/accounts/signup").get_data(as_text=True))
    response = client.post(
        "/accounts/signup", data={**VALID_SIGNUP, "csrf_token": token}
    )

    assert response.status_code == 302


def test_signup_is_rate_limited() -> None:
    client = make_app(RateLimitEnabledConfig).test_client()
    statuses = [
        client.post("/accounts/signup", data={"username": ""}).status_code
        for _ in range(6)
    ]

    assert statuses == [400] * 5 + [429]


def test_rate_limit_does_not_apply_to_get() -> None:
    client = make_app(RateLimitEnabledConfig).test_client()
    statuses = {client.get("/accounts/signup").status_code for _ in range(10)}

    assert statuses == {200}


# ---------- ログインの回数制限 ----------


def _rate_limited_app_with_user() -> Flask:
    app = make_app(RateLimitEnabledConfig)
    create_user(app)
    return app


def test_login_failures_are_rate_limited_per_ip() -> None:
    client = _rate_limited_app_with_user().test_client()
    statuses = [
        login(client, f"user{i}", "wrong-password").status_code for i in range(6)
    ]

    assert statuses == [400] * 5 + [429]


def test_login_success_is_not_counted() -> None:
    client = _rate_limited_app_with_user().test_client()
    for _ in range(6):
        assert login(client).status_code == 302
        client.post("/accounts/logout")


def test_login_failures_are_rate_limited_per_username() -> None:
    client = _rate_limited_app_with_user().test_client()
    statuses = []
    for i in range(11):
        # 別々の IP アドレスから同じユーザー名を狙う
        response = client.post(
            "/accounts/login",
            data={"username": "TARO", "password": "wrong-password"},
            environ_base={"REMOTE_ADDR": f"10.0.0.{i}"},
        )
        statuses.append(response.status_code)

    assert statuses == [400] * 10 + [429]


# ---------- リバースプロキシの後ろで動かすとき ----------

PROXY_ADDR = {"REMOTE_ADDR": "10.0.0.1"}  # アプリから見える接続元（プロキシ）


def _signup_from(client: FlaskClient, forwarded_for: str) -> int:
    response = client.post(
        "/accounts/signup",
        data={"username": ""},
        headers={"X-Forwarded-For": forwarded_for},
        environ_base=PROXY_ADDR,
    )
    return response.status_code


def test_rate_limit_uses_real_client_ip_behind_proxy() -> None:
    client = make_app(BehindProxyConfig).test_client()

    statuses = [_signup_from(client, "203.0.113.1") for _ in range(6)]
    assert statuses == [400] * 5 + [429]
    # 同じプロキシを通っていても、別の人（別の IP アドレス）は制限されない
    assert _signup_from(client, "203.0.113.2") == 400


def test_forwarded_header_is_ignored_without_proxy_setting() -> None:
    # プロキシの設定がなければ X-Forwarded-For を信じない
    # （偽のヘッダーを付けて、回数制限をすり抜けられないようにする）
    client = make_app(RateLimitEnabledConfig).test_client()
    statuses = [_signup_from(client, f"203.0.113.{i}") for i in range(6)]

    assert statuses == [400] * 5 + [429]


def test_https_is_detected_behind_proxy() -> None:
    app = make_app(BehindProxyConfig)

    @app.get("/scheme")
    def scheme() -> str:
        return request.scheme

    response = app.test_client().get(
        "/scheme", headers={"X-Forwarded-Proto": "https"}, environ_base=PROXY_ADDR
    )

    assert response.get_data(as_text=True) == "https"


# ---------- 本番設定での Cookie ----------


def test_remember_cookie_is_secure_in_production() -> None:
    app = make_app(ProductionTestConfig)
    create_user(app)
    response = login(app.test_client(), remember="y")

    cookie = next(
        h
        for h in response.headers.getlist("Set-Cookie")
        if h.startswith("remember_token=")
    )
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
