from datetime import UTC, datetime

from flask_login import UserMixin
from sqlalchemy import String, select
from sqlalchemy.orm import Mapped, mapped_column, validates

from fl_demonstro.accounts.passwords import (
    hash_password,
    needs_rehash,
    verify_dummy_password,
    verify_password,
)
from fl_demonstro.extensions import db, login_manager


# db.Model は実行時に作られるクラスなので、mypy には中身が分からない
class User(UserMixin, db.Model):  # type: ignore[name-defined]
    # UserMixin は Flask-Login が必要とする is_authenticated などを用意してくれる

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # ユーザー名は小文字だけで保存する（同じ名前は登録できない）
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    @validates("username")
    def _validate_username(self, key: str, username: str) -> str:
        """保存する前に、ユーザー名が小文字だけかを確かめる（最後の守り）。

        入力の形式はフォームで確かめているが、フォームを通らずに作られた場合でも、
        大文字の混ざった名前（Taro と taro の両方）が保存されないようにする。
        """
        if username != username.lower():
            raise ValueError("ユーザー名は小文字で保存してください。")
        return username

    def set_password(self, password: str) -> None:
        """パスワードを元に戻せない形（Argon2id のハッシュ）にして保存する。"""
        self.password_hash = hash_password(password)

    def check_password(self, password: str) -> bool:
        """入力されたパスワードが正しいか確かめる。"""
        return verify_password(self.password_hash, password)

    @classmethod
    def find_by_username(cls, username: str) -> User | None:
        """ユーザー名で探す。

        保存されている名前はすべて小文字なので、小文字にしてから探す
        （ログインで「Taro」と入力されても taro さんが見つかる）。
        """
        return db.session.scalar(select(cls).where(cls.username == username.lower()))

    @classmethod
    def authenticate(cls, username: str, password: str) -> User | None:
        """ユーザー名とパスワードが正しければ、そのユーザーを返す。

        ユーザーが存在しないときもダミーのパスワード照合を行い、
        応答時間の差から「そのユーザー名が存在するか」を推測されないようにする。
        """
        user = cls.find_by_username(username)
        if user is None:
            verify_dummy_password(password)
            return None
        if not user.check_password(password):
            return None
        if needs_rehash(user.password_hash):
            # 古い方式（scrypt）や弱い設定で保存されていたら、正しいパスワードが
            # 分かっているこのタイミングで、今の方式で保存し直す
            user.set_password(password)
            db.session.commit()
        return user

    def __repr__(self) -> str:
        return f"<User {self.username}>"


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    """セッションに保存された ID から、ログイン中のユーザーを読み込む。"""
    try:
        return db.session.get(User, int(user_id))
    except ValueError:
        return None
