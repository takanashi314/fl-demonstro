from flask import Blueprint

bp = Blueprint("main", __name__)

from fl_demonstro.main import views  # noqa: E402, F401  (ルートを登録するために読み込む)
