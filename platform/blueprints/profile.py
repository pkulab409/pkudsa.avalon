# author: shihuaidexianyu (refactored by AI assistant)
# date: 2025-04-25
# status: done
# description: 用户个人资料蓝图，包含用户资料和对战历史的路由。
# 包含页面html: profile/profile.html, profile/battle_history.html

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from database.models import User, GameStats, Battle, db
from database.action import (
    get_game_stats_by_user_id,
    get_user_battle_history as db_get_user_battle_history,
    get_user_by_username,
)

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
        # 使用数据库函数查找用户
        user = get_user_by_username(username)
        if not user:
            # 如果找不到用户，返回404错误
            from flask import abort

            abort(404)

    # 使用数据库函数查询用户的游戏统计数据
    game_stats = get_game_stats_by_user_id(user.id)

    # 判断当前用户是否在查看自己的资料
    is_self = current_user.is_authenticated and current_user.id == user.id

    # 检查当前用户是否为管理员
    is_admin = current_user.is_authenticated and current_user.is_admin

    return render_template(
        "profile/profile.html",
        user=user,
        game_stats=game_stats,
        is_self=is_self,
        is_admin=is_admin,
    )


@profile_bp.route("/battle-history")
@login_required
def battle_history():
    """显示用户完整对战历史"""
    page = request.args.get("page", 1, type=int)
    per_page = 10

    # 使用正确的数据库函数获取用户的对战记录 (此部分已在之前修改过，保持不变)
    # from database.action import get_user_battle_history as db_get_user_battle_history # 移到文件顶部

    battles, total = db_get_user_battle_history(
        current_user.id, page=page, per_page=per_page
    )

    # 计算总页数
    total_pages = (total + per_page - 1) // per_page

    return render_template(
        "profile/battle_history.html",
        battles=battles,
        current_page=page,
        total_pages=total_pages,
        total_battles=total,
    )
