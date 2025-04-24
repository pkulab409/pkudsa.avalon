from flask import Blueprint, render_template, jsonify, request
from flask_login import current_user
from database.models import GameStats
from database.action import get_leaderboard
from config.config import Config
from database.models import User, db
from sqlalchemy import func
import json

# 创建蓝图
ranking_bp = Blueprint("ranking", __name__)


@ranking_bp.route("/ranking")
def show_ranking():
    """显示排行榜页面"""
    # 获取排行榜类型
    sort_by = request.args.get("sort_by", "score")

    # 获取排行榜数据
    if sort_by == "score":
        leaderboard_data = get_leaderboard()
        # 记录日志，查看返回数据
        print(f"排行榜数据: {leaderboard_data}")
        ranking_items = []

        for idx, data in enumerate(leaderboard_data):
            user = User.query.get(data["user_id"])
            if user:
                ranking_items.append(
                    {
                        "rank": idx + 1,
                        "user": user,
                        "score": data["elo_score"],
                        "wins": data["wins"],
                        "losses": data["losses"],
                        "draws": data["draws"],
                        "total": data["games_played"],
                        "win_rate": (
                            f"{data['win_rate']:.1f}%"
                            if data["games_played"] > 0
                            else "0%"
                        ),
                    }
                )
    else:
        # 其他排序方式
        ranking_items = []

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

    # 获取排行榜数据
    leaderboard_data = get_leaderboard()

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
                "win_rate": data["win_rate"],
            }
        )

    return jsonify(
        {
            "sort_by": sort_by,
            "rankings": ranking_list,
            "total": len(ranking_list),
        }
    )


@ranking_bp.route("/api/user_stats/<int:user_id>")
def get_user_stats(user_id):
    """获取用户统计数据（API）"""
    from database.action import get_player_stats

    # 获取用户信息
    user = User.query.get(user_id)
    if not user:
        return jsonify({"success": False, "message": "用户不存在"})

    # 获取用户统计数据
    stat = get_player_stats(user_id)
    if not stat:
        return jsonify(
            {
                "success": True,
                "user_id": user_id,
                "username": user.username,
                "stats": {},
            }
        )

    # 创建单个stats对象
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
        )
    }

    return jsonify(
        {
            "success": True,
            "user_id": user_id,
            "username": user.username,
            "stats": stats_data,
        }
    )
