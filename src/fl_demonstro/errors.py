"""エラー画面（404 など）を日本語のページで表示する。"""

from flask import Flask, render_template
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException, InternalServerError
from werkzeug.wrappers import Response

from fl_demonstro.extensions import db

# ステータスコードごとの（見出し, 説明）
ERROR_MESSAGES: dict[int, tuple[str, str]] = {
    400: (
        "リクエストが正しくありません",
        "送信内容を確認して、もう一度お試しください。",
    ),
    403: ("アクセスできません", "このページを表示する権限がありません。"),
    404: (
        "ページが見つかりません",
        "URL が間違っているか、ページが削除された可能性があります。",
    ),
    405: (
        "この操作はできません",
        "このページでは、その方法でのアクセスを受け付けていません。",
    ),
    413: (
        "送信データが大きすぎます",
        "送信するデータを小さくしてから、もう一度お試しください。",
    ),
    429: (
        "アクセスが多すぎます",
        "短い時間に何度も送信されました。しばらく待ってからお試しください。",
    ),
    500: (
        "サーバーでエラーが発生しました",
        "申し訳ありません。時間をおいてから、もう一度お試しください。",
    ),
}

CSRF_ERROR_MESSAGE = (
    "送信できませんでした",
    # 長い説明文を2行に分けて書いている（かっこの中の文字列は1つにつながる）
    (
        "ページの有効期限が切れたか、不正な送信の可能性があります。"
        "ページを再読み込みしてから、もう一度お試しください。"
    ),
)


def _render_error(e: HTTPException, title: str, message: str) -> Response:
    # e.get_response() を元にすると、405 の Allow ヘッダーなどが引き継がれる
    response = e.get_response()
    response.set_data(
        render_template("errors/error.html", title=title, message=message)
    )
    response.content_type = "text/html; charset=utf-8"
    return response


def init_error_handlers(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e: CSRFError) -> Response:
        return _render_error(e, *CSRF_ERROR_MESSAGE)

    @app.errorhandler(HTTPException)
    def handle_http_exception(e: HTTPException) -> Response:
        title, message = ERROR_MESSAGES.get(
            e.code or 500, (e.name, e.description or "")
        )
        return _render_error(e, title, message)

    @app.errorhandler(InternalServerError)
    def handle_internal_server_error(e: InternalServerError) -> Response:
        # 途中で失敗したデータベース操作を取り消してから画面を出す
        db.session.rollback()
        return _render_error(e, *ERROR_MESSAGES[500])
