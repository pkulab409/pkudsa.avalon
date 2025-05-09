#!/usr/bin/env python
# dmcnczy 25/4/28
"""提供文档页面"""


from flask import Blueprint, render_template

# 创建蓝图
docs_bp = Blueprint("docs", __name__)


@docs_bp.route("/")
def index():
    return render_template("/docs/docs.html", docname="README")


@docs_bp.route("/code_submission_guide")
def index2():
    return render_template("/docs/docs.html", docname="code_submission_guide")


@docs_bp.route("/elo")
def index3():
    return render_template("/docs/docs.html", docname="elo")


@docs_bp.route("/server_func")
def index4():
    return render_template("/docs/docs.html", docname="server_func")
