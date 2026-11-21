from flask import (
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
    user_loaded_from_cookie,
)
from sqlalchemy.exc import IntegrityError

from fl_demonstro.accounts import bp
from fl_demonstro.accounts.forms import (
    LOGIN_FAILED,
    USERNAME_TAKEN,
    LoginForm,
    SignupForm,
)
from fl_demonstro.accounts.models import User
from fl_demonstro.extensions import db, limiter
from fl_demonstro.utils import is_safe_redirect_url


def _is_failed_login(response: Response) -> bool:
    """ログイン失敗だけを回数制限に数える（成功するとリダイレクトになる）。"""
    return response.status_code != 302


def _regenerate_session_id() -> None:
    """セッション ID を新しくし、古い ID のセッションをサーバーから消す。

    Flask-Session の regenerate() は中身が空のセッションでは何もしないので、
    セッションに値を書いたあと（login_user() や flash() のあと）に呼ぶこと。
    """
    regenerate = getattr(current_app.session_interface, "regenerate", None)
    if regenerate is not None:
        regenerate(session)


# Flask-Login が「ログインしたままにする」の Cookie から復元するときに
# セッションへ書き込む項目（これ以外は捨てる）
_REMEMBER_LOGIN_KEYS = ("_user_id", "_fresh")


@user_loaded_from_cookie.connect
def _renew_session_on_remember_login(sender: object, user: User) -> None:
    """「ログインしたままにする」の Cookie でログイン状態が戻ったときに呼ばれる。

    フォームからのログインと同じく、それまでのセッションの中身を捨て、
    セッション ID も新しくする（セッション固定攻撃の対策）。
    中身を捨てるのは、仕込まれたセッションに入っていた CSRF の合言葉を
    攻撃者が知っているため（そのままだと、なりすまし送信ができてしまう）。
    """
    kept = {key: session[key] for key in _REMEMBER_LOGIN_KEYS if key in session}
    session.clear()
    session.update(kept)
    _regenerate_session_id()


def _login_username_key() -> str:
    """ユーザー名ごとの回数制限に使うキー（大文字・小文字は区別しない）。"""
    return "login:" + (request.form.get("username") or "").strip().lower()


@bp.route("/signup", methods=["GET", "POST"])
@limiter.limit("5 per minute;20 per hour", methods=["POST"])
def signup() -> ResponseReturnValue:
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = SignupForm()

    if not form.validate_on_submit():
        # 初めての表示（GET）は 200、入力エラー（POST）は 400 で再表示する
        status = 400 if form.is_submitted() else 200
        return render_template("accounts/signup.html", form=form), status

    user = User(username=form.username.data)
    user.set_password(form.password.data)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        # チェックの直後に同じ名前が登録された場合（ほぼ同時の登録）
        db.session.rollback()
        form.username.errors.append(USERNAME_TAKEN)
        return render_template("accounts/signup.html", form=form), 400

    # 登録成功: Redirect して完了ページを Get させる（PRG パターン）
    flash(f"{user.username} さん、登録が完了しました。", "success")
    return redirect(url_for("accounts.signup_done"))


@bp.get("/signup/done")
def signup_done() -> ResponseReturnValue:
    return render_template("accounts/signup_done.html")


@bp.route("/login", methods=["GET", "POST"])
# 同じ IP アドレスからの失敗回数を制限（総当たり攻撃の対策）
@limiter.limit(
    "5 per minute;20 per hour", methods=["POST"], deduct_when=_is_failed_login
)
# 同じユーザー名への失敗回数を制限（IP アドレスを変えながらの攻撃の対策）
@limiter.limit(
    "10 per hour",
    key_func=_login_username_key,
    methods=["POST"],
    deduct_when=_is_failed_login,
)
def login() -> ResponseReturnValue:
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.authenticate(form.username.data, form.password.data)
        if user is not None:
            next_url = request.args.get("next")
            # ログイン前のセッションを捨て、セッション ID も新しくする
            # （セッション固定攻撃の対策）
            session.clear()
            login_user(user, remember=form.remember.data)
            flash("ログインしました。", "success")
            _regenerate_session_id()
            # ログイン後は元のページへ。ただし外部サイトへは飛ばさない
            if not is_safe_redirect_url(next_url):
                next_url = url_for("main.index")
            return redirect(next_url)
        form.form_errors.append(LOGIN_FAILED)

    status = 400 if form.is_submitted() else 200
    return render_template("accounts/login.html", form=form), status


@bp.post("/logout")  # GET で受けると、リンクを踏ませるだけでログアウトさせられるため
@login_required
def logout() -> ResponseReturnValue:
    # 先にセッションを空にしてから logout_user() を呼ぶ
    # （logout_user() は「ログインしたまま」の Cookie を消す指示をセッションに書くため）
    session.clear()
    logout_user()
    flash("ログアウトしました。", "info")
    _regenerate_session_id()
    return redirect(url_for("main.index"))
