"""Flask 拡張機能。

ここで作っておき、create_app() の中でアプリと結びつける。
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# 制約やインデックスの名前の付け方を決めておく。
# 名前が毎回同じになるので、マイグレーション（テーブルの形の変更）が安定する。
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
csrf = CSRFProtect()  # CSRF（なりすまし送信）対策
limiter = Limiter(key_func=get_remote_address)  # 送信回数の制限
server_session = Session()  # セッションをサーバー側に保存する

# ログイン状態の管理
login_manager = LoginManager()
login_manager.login_view = "accounts.login"  # ログインが必要なページで飛ばす先
login_manager.login_message = "このページを見るにはログインしてください。"
login_manager.login_message_category = "info"
