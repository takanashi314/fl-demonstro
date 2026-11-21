from flask import render_template

from fl_demonstro.main import bp


@bp.get("/")
def index() -> str:
    return render_template("main/index.html")
