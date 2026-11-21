from flask import Blueprint

bp = Blueprint("accounts", __name__, url_prefix="/accounts")

from fl_demonstro.accounts import views  # noqa: E402, F401  (ルートを登録するために読み込む)
