# author: shihuaidexianyu (refactored by AI assistant)
# date: 2025-04-25
# status: done
# description: 用户排行版块蓝图，包含排行榜和用户统计数据的路由。
# 包含页面html: ranking.html


"""
用户排行版块蓝图，包含排行榜和用户统计数据的路由。
- 上接后端数据库排行榜 database.actions 和 database.models 操作函数和模型
- 下接浏览器页面 ranking.html
"""


from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import current_user

# 导入需要的数据库操作函数和模型
from database.action import get_leaderboard, get_game_stats_by_user_id, get_user_by_id
from database.models import User  # User 模型仍然需要用于类型提示或模板

# 创建蓝图
ranking_bp = Blueprint("ranking", __name__)


@ranking_bp.route("/ranking")
def show_ranking():
    """显示排行榜页面"""
    # 获取分页参数
    page = request.args.get("page", 1, type=int)
    per_page = 15  # 固定每页20条

    # 获取其他参数
    sort_by = request.args.get("sort_by", "score")
    min_games = request.args.get("min_games", 1, type=int)
    ranking_id = request.args.get("ranking_id", 0, type=int)

    # 获取完整排行榜数据
    full_leaderboard = get_leaderboard(
        ranking_id=ranking_id,
        limit=None,  # 获取全部数据用于分页
        min_games_played=min_games,
    )

    # 手动实现分页逻辑
    total = len(full_leaderboard)
    pages = (total - 1) // per_page + 1  # 计算总页数
    page = max(min(page, pages), 1)  # 限制页码范围
    offset = (page - 1) * per_page
    leaderboard_data = full_leaderboard[offset : offset + per_page]

    # 在 blueprints/ranking.py 中修改分页类
    class Pagination:
        def __init__(self, items, page, per_page, total):
            self.items = items
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = (total - 1) // per_page + 1
            self.prev_num = page - 1 if page > 1 else None
            self.next_num = page + 1 if page < self.pages else None
            self.has_prev = page > 1
            self.has_next = page < self.pages

        # 新增迭代页码范围的方法
        def iter_pages(
            self, left_edge=2, left_current=2, right_current=4, right_edge=2
        ):
            last = 0
            for num in range(1, self.pages + 1):
                if (
                    num <= left_edge
                    or (
                        num > self.page - left_current - 1
                        and num < self.page + right_current
                    )
                    or num > self.pages - right_edge
                ):
                    if last + 1 != num:
                        yield None  # 生成省略号占位符
                    yield num
                    last = num

    # 生成分页数据
    ranking_items = []
    for idx, data in enumerate(leaderboard_data):
        ranking_items.append(
            {
                "rank": offset + idx + 1,  # 保持全局排名
                "username": data["username"],
                "user_id": data["user_id"],
                "score": data["elo_score"],
                "wins": data["wins"],
                "losses": data["losses"],
                "draws": data["draws"],
                "total": data["games_played"],
                "win_rate": data["win_rate"],
            }
        )

    # 创建分页对象
    pagination = Pagination(
        items=ranking_items, page=page, per_page=per_page, total=total
    )

    return render_template(
        "ranking.html",
        pagination=pagination,
        sort_by=sort_by,
        current_ranking_id=ranking_id,
        # 保持向下兼容
        ranking_items=ranking_items,  # 可选，建议模板迁移到使用pagination
    )


@ranking_bp.route("/api/ranking")
def get_ranking_data():
    """获取排行榜数据（API）"""
    # 获取排序类型
    sort_by = request.args.get("sort_by", "score")  # sort_by 当前未实际用于排序逻辑
    limit = request.args.get("limit", 100, type=int)
    min_games = request.args.get("min_games", 1, type=int)
    ranking_id = request.args.get("ranking_id", 0, type=int)  # 新增 ranking_id 参数

    # 获取排行榜数据
    leaderboard_data = get_leaderboard(
        ranking_id=ranking_id, limit=limit, min_games_played=min_games
    )

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

    ranking_id = request.args.get("ranking_id", 0, type=int)  # 新增 ranking_id 参数

    # 使用 get_game_stats_by_user_id 获取用户统计数据
    stat = get_game_stats_by_user_id(user_id, ranking_id=ranking_id)  # 传递 ranking_id
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
