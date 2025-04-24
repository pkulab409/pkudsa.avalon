from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from database.models import User, GameStats, Battle, db
from database.action import get_user_battles

# 创建蓝图
profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/profile")
@profile_bp.route("/profile/<username>")
def profile(username=None):
    """显示用户个人资料页面"""
    # 如果未指定用户名，显示当前登录用户的资料
    if username is None:
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        user = current_user
    else:
        # 查找指定用户名的用户
        user = User.query.filter_by(username=username).first_or_404()

    # 查询用户的游戏统计数据
    game_stats = GameStats.query.filter_by(user_id=user.id).first()

    # 判断当前用户是否在查看自己的资料
    is_self = current_user.is_authenticated and current_user.id == user.id

    return render_template(
        "profile/profile.html",
        user=user,
        game_stats=game_stats,  # 现在是单个对象，不是列表
        is_self=is_self,
    )


@profile_bp.route("/battle-history")
@login_required
def battle_history():
    """显示用户完整对战历史"""
    page = request.args.get("page", 1, type=int)
    per_page = 10

    # 获取用户的对战记录
    from database.action import get_user_battles

    battles, total = get_user_battles(
        current_user.id, page=page, per_page=per_page, paginate=True
    )

    # 计算总页数
    total_pages = (total + per_page - 1) // per_page

    return render_template(
        "profile/battle_history.html",
        battles=battles,
        page=page,
        total_pages=total,
        total_battles=total,
    )
