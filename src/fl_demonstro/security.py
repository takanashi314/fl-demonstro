"""セキュリティ用の HTTP ヘッダー（ブラウザへの指示）を付ける。"""

from flask import Flask, Response
from flask_login import current_user

# 外から読み込んでよい場所（base.html の Bootstrap）。
# jsDelivr は誰でもファイルを公開できるので、サイト全体ではなく
# Bootstrap のこのバージョンの置き場所だけを許す。
# base.html の Bootstrap のバージョンを変えたら、ここも変えること
# （忘れるとテストが失敗して教えてくれる）。
BOOTSTRAP_CDN = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/"


def build_content_security_policy(allow_inline: bool = False) -> str:
    """ブラウザに「読み込んでよい場所」を伝える設定（XSS などの被害を抑える）を作る。

    allow_inline=True は HTML に直接書かれたスクリプトも許す緩い設定で、
    開発用のデバッグツールバーを使うときだけに限る。
    """
    inline = " 'unsafe-inline'" if allow_inline else ""
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' {BOOTSTRAP_CDN}{inline}",
            f"style-src 'self' {BOOTSTRAP_CDN}{inline}",
            "img-src 'self' data:",  # Bootstrap のアイコンが data: 形式の画像を使う
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


def init_security(app: Flask) -> None:
    """すべてのレスポンスにセキュリティ用ヘッダーを付ける。"""
    csp = build_content_security_policy(app.config.get("CSP_ALLOW_INLINE", False))

    @app.after_request
    def set_security_headers(response: Response) -> Response:
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if current_user.is_authenticated:
            # ログイン中のページはブラウザに保存させない
            # （共用パソコンでログアウト後に「戻る」で見られるのを防ぐ）
            response.headers["Cache-Control"] = "no-store"
        if app.config["SESSION_COOKIE_SECURE"]:
            # HTTPS で運用しているときだけ、今後も HTTPS を使うようブラウザに伝える
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response
