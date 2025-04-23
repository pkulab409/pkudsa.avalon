from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from database.models import User, GameStats, Battle, db

# 创建蓝图
profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/profile")
@profile_bp.route("/profile/<username>")
@login_required
def profile(username=None):
    """显示用户个人资料页面"""
    # 如果未指定用户名，显示当前登录用户的资料
    if username is None:
        user = current_user
    else:
        # 查找指定用户名的用户
        user = User.query.filter_by(username=username).first_or_404()

    # 获取用户的游戏统计数据
    from database.action import get_player_stats

    game_stats = get_player_stats(user.id)

    # 获取用户最近的对战记录
    # 注意参数传递：paginate=False 以获取Battle对象列表而非元组
    from database.action import get_user_battles

    recent_battles = get_user_battles(user.id, page=1, per_page=5, paginate=False)

    return render_template(
        "profile/profile.html",
        user=user,
        game_stats=game_stats,
        recent_battles=recent_battles,
        is_self=(user.id == current_user.id),
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
        total_pages=total_pages,
        total_battles=total,
    )
