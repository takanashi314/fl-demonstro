from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import (
    DataRequired,
    EqualTo,
    InputRequired,
    Length,
    Regexp,
    ValidationError,
)

from fl_demonstro.accounts.models import User
from fl_demonstro.accounts.passwords import (
    PASSWORD_MAX,
    PASSWORD_MIN,
    password_policy_error,
)

USERNAME_MIN = 3
USERNAME_MAX = 32

USERNAME_TAKEN = "このユーザー名はすでに使われています。"
# どちらが間違っているかは教えない（ユーザー名が存在するかを推測されないように）
LOGIN_FAILED = "ユーザー名またはパスワードが正しくありません。"

# ユーザー名の入力欄の設定。スマートフォンが先頭の文字を勝手に大文字にしたり、
# 単語を自動で直したりしないようにする（ユーザー名は小文字だけなので）。
USERNAME_INPUT_ATTRS = {
    "autocomplete": "username",
    "autocapitalize": "none",
    "autocorrect": "off",
    "spellcheck": "false",
}


def _strip(value: str | None) -> str | None:
    """前後の空白を取り除く。"""
    return value.strip() if value else value


class SignupForm(FlaskForm):
    username = StringField(
        "ユーザー名",
        filters=[_strip],
        validators=[
            DataRequired(message="ユーザー名を入力してください。"),
            Regexp(
                rf"^[a-z0-9]{{{USERNAME_MIN},{USERNAME_MAX}}}\Z",
                message=(
                    f"ユーザー名は{USERNAME_MIN}〜{USERNAME_MAX}文字の"
                    "半角英小文字（a〜z）と数字で入力してください。"
                ),
            ),
        ],
        description=f"{USERNAME_MIN}〜{USERNAME_MAX}文字の半角英小文字（a〜z）と数字",
        render_kw=USERNAME_INPUT_ATTRS,
    )
    password = PasswordField(
        "パスワード",
        validators=[
            InputRequired(message="パスワードを入力してください。"),
            Length(
                min=PASSWORD_MIN,
                max=PASSWORD_MAX,
                message=f"パスワードは{PASSWORD_MIN}〜{PASSWORD_MAX}文字にしてください。",
            ),
        ],
        description=(
            f"{PASSWORD_MIN}〜{PASSWORD_MAX}文字。記号は不要です。"
            "よく使われるパスワードやユーザー名を含むものは使えません。"
        ),
        render_kw={"autocomplete": "new-password"},
    )
    password_confirm = PasswordField(
        "パスワード（確認）",
        validators=[
            InputRequired(message="確認用のパスワードを入力してください。"),
            EqualTo("password", message="パスワードが一致しません。"),
        ],
        render_kw={"autocomplete": "new-password"},
    )
    submit = SubmitField("登録")

    # validate_<項目名> は、その項目の基本チェックのあとに自動で呼ばれる
    def validate_username(self, field: StringField) -> None:
        if field.errors:  # 形式が正しくなければ、データベースを調べない
            return
        if User.find_by_username(field.data):
            raise ValidationError(USERNAME_TAKEN)

    def validate_password(self, field: PasswordField) -> None:
        if field.errors:
            return
        if error := password_policy_error(field.data, self.username.data):
            raise ValidationError(error)


class LoginForm(FlaskForm):
    username = StringField(
        "ユーザー名",
        filters=[_strip],
        validators=[DataRequired(message="ユーザー名を入力してください。")],
        render_kw=USERNAME_INPUT_ATTRS,
    )
    password = PasswordField(
        "パスワード",
        validators=[
            InputRequired(message="パスワードを入力してください。"),
            # 極端に長い入力でパスワード照合の負荷をかけられるのを防ぐ
            Length(max=PASSWORD_MAX, message=LOGIN_FAILED),
        ],
        render_kw={"autocomplete": "current-password"},
    )
    remember = BooleanField("ログインしたままにする")
    submit = SubmitField("ログイン")
