from flask import Blueprint, render_template, jsonify, request
from flask_login import current_user
from database.models import GameStats
from database.action import get_leaderboard
import redis
from config.config import Config
from database.models import User, db
from sqlalchemy import func
import json
from utils.redis_utils import get_redis_client

# 创建蓝图
ranking_bp = Blueprint("ranking", __name__)


@ranking_bp.route("/ranking")
def show_ranking():
    """显示排行榜页面"""
    # 获取游戏类型
    game_type = request.args.get("game_type", "default")

    # 获取排行榜类型
    sort_by = request.args.get("sort_by", "score")

    # 获取该游戏类型的排行榜数据
    if sort_by == "score":
        leaderboard_data = get_leaderboard(game_type)
        ranking_items = []

        for idx, (stats, user) in enumerate(leaderboard_data):
            ranking_items.append(
                {
                    "rank": idx + 1,
                    "user": user,
                    "score": stats.score,
                    "wins": stats.games_won,
                    "losses": stats.games_lost,
                    "draws": stats.games_draw,
                    "total": stats.games_played,
                    "win_rate": (
                        f"{(stats.games_won / stats.games_played * 100):.1f}%"
                        if stats.games_played > 0
                        else "0%"
                    ),
                }
            )
    else:
        # 其他排序方式
        ranking_items = []

    # 获取支持的游戏类型列表
    game_types = [
        {"id": "default", "name": "默认游戏"},
    ]

    return render_template(
        "ranking.html",
        ranking_items=ranking_items,
        game_type=game_type,
        sort_by=sort_by,
        game_types=game_types,
    )


@ranking_bp.route("/api/ranking/<game_type>")
def get_ranking_data(game_type):
    """获取特定游戏类型的排行榜数据（API）"""
    # 获取排序类型
    sort_by = request.args.get("sort_by", "score")

    # 获取该游戏类型的排行榜数据
    leaderboard_data = get_leaderboard(game_type)

    ranking_list = []
    for idx, (stats, user) in enumerate(leaderboard_data):
        ranking_list.append(
            {
                "rank": idx + 1,
                "user_id": user.id,
                "username": user.username,
                "score": stats.score,
                "wins": stats.games_won,
                "losses": stats.games_lost,
                "draws": stats.games_draw,
                "total": stats.games_played,
                "win_rate": (
                    round(stats.games_won / stats.games_played * 100, 1)
                    if stats.games_played > 0
                    else 0
                ),
            }
        )

    return jsonify(
        {
            "game_type": game_type,
            "sort_by": sort_by,
            "rankings": ranking_list,
            "total": len(ranking_list),
        }
    )


@ranking_bp.route("/api/user_stats/<int:user_id>")
def get_user_stats(user_id):
    """获取用户在各游戏的统计数据（API）"""
    redis_client = get_redis_client()
    from database.action import get_player_stats

    # 获取用户信息
    user = User.query.get(user_id)
    if not user:
        return jsonify({"success": False, "message": "用户不存在"})

    # 获取用户在各游戏的统计数据
    player_stats = get_player_stats(user_id)

    stats_data = []
    for stat in player_stats:
        stats_data.append(
            {
                "game_type": stat.game_type,
                "score": stat.score,
                "wins": stat.games_won,
                "losses": stat.games_lost,
                "draws": stat.games_draw,
                "total": stat.games_played,
                "win_rate": (
                    round(stat.games_won / stat.games_played * 100, 1)
                    if stat.games_played > 0
                    else 0
                ),
                "last_played": (
                    stat.last_played.isoformat() if stat.last_played else None
                ),
            }
        )

    return jsonify(
        {
            "success": True,
            "user_id": user_id,
            "username": user.username,
            "stats": stats_data,
        }
    )
