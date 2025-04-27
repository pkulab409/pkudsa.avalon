# author: shihuaidexianyu (refactored by AI assistant)
# date: 2025-04-25
# status: done
# description: 用户排行版块蓝图，包含排行榜和用户统计数据的路由。
# 包含页面html: ranking.html


'''
用户排行版块蓝图，包含排行榜和用户统计数据的路由。
- 上接后端数据库排行榜 database.actions 和 database.models 操作函数和模型
- 下接浏览器页面 ranking.html
'''


from flask import Blueprint, render_template, jsonify, request
from flask_login import current_user

# 导入需要的数据库操作函数和模型
from database.action import get_leaderboard, get_game_stats_by_user_id, get_user_by_id
from database.models import User  # User 模型仍然需要用于类型提示或模板

# 创建蓝图
ranking_bp = Blueprint("ranking", __name__)


@ranking_bp.route("/ranking")
def show_ranking():
    """显示排行榜页面"""
    # 获取排行榜类型
    sort_by = request.args.get("sort_by", "score")
    limit = request.args.get("limit", 100, type=int)  # 添加分页或限制参数
    min_games = request.args.get("min_games", 1, type=int)  # 添加最小场次参数

    # 获取排行榜数据 - get_leaderboard 默认按 score 排序
    leaderboard_data = get_leaderboard(limit=limit, min_games_played=min_games)

    ranking_items = []
    for idx, data in enumerate(leaderboard_data):
        ranking_items.append(
            {
                "rank": idx + 1,
                "username": data["username"],  # 直接使用用户名
                "user_id": data["user_id"],  # 传递 user_id 以便生成链接
                "score": data["elo_score"],
                "wins": data["wins"],
                "losses": data["losses"],
                "draws": data["draws"],
                "total": data["games_played"],
                "win_rate": (
                    f"{data['win_rate']:.1f}%"  # win_rate 已在 get_leaderboard 中计算
                ),
            }
        )
    return render_template(
        "ranking.html",
        ranking_items=ranking_items,
        sort_by=sort_by,
    )


@ranking_bp.route("/api/ranking")
def get_ranking_data():
    """获取排行榜数据（API）"""
    # 获取排序类型
    sort_by = request.args.get("sort_by", "score")
    limit = request.args.get("limit", 100, type=int)
    min_games = request.args.get("min_games", 1, type=int)

    # 获取排行榜数据 - get_leaderboard 默认按 score 排序
    leaderboard_data = get_leaderboard(limit=limit, min_games_played=min_games)

    ranking_list = []
    for idx, data in enumerate(leaderboard_data):
        ranking_list.append(
            {
                "rank": idx + 1,
                "user_id": data["user_id"],
                "username": data["username"],
                "score": data["elo_score"],
                "wins": data["wins"],
                "losses": data["losses"],
                "draws": data["draws"],
                "total": data["games_played"],
                "win_rate": data["win_rate"],  # 直接使用计算好的胜率
            }
        )

    return jsonify(
        {
            "sort_by": sort_by,  # 仍然返回请求的 sort_by，即使数据总是按 score 排序
            "rankings": ranking_list,
            "total": len(ranking_list),
        }
    )


@ranking_bp.route("/api/user_stats/<string:user_id>")  # 使用 string 类型匹配 UUID
def get_user_stats(user_id):
    """获取用户统计数据（API）"""
    # 使用 get_user_by_id 获取用户信息
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"success": False, "message": "用户不存在"})

    # 使用 get_game_stats_by_user_id 获取用户统计数据
    stat = get_game_stats_by_user_id(user_id)
    if not stat:
        # 如果没有统计数据，返回成功但 stats 为空
        return jsonify(
            {
                "success": True,
                "user_id": user_id,
                "username": user.username,
                "stats": {},  # 返回空字典表示无统计数据
            }
        )

    # 创建 stats 数据字典
    stats_data = {
        "score": stat.elo_score,
        "wins": stat.wins,
        "losses": stat.losses,
        "draws": stat.draws,
        "total": stat.games_played,
        "win_rate": (
            round(stat.wins / stat.games_played * 100, 1)
            if stat.games_played > 0
            else 0
        ),
    }

    return jsonify(
        {
            "success": True,
            "user_id": user_id,
            "username": user.username,
            "stats": stats_data,  # 返回包含数据的字典
        }
    )
