# author: shihuaidexianyu (refactored by AI assistant)
# date: 2025-04-25
# status: done
# description: 主页蓝图，包含主页路由。


from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    return render_template("index.html")
