from flask import Blueprint, render_template

bp = Blueprint("main", __name__)


@bp.route("/")
def landing():
    return render_template("landing.html")