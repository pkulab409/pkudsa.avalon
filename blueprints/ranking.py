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
# 假设这些函数按预期工作
from database.action import get_leaderboard, get_game_stats_by_user_id, get_user_by_id
from database.models import User, GameStats # 确保 GameStats 已导入

# 创建蓝图
ranking_bp = Blueprint("ranking", __name__)

# 分页辅助类 (移至模块级别)
class Pagination:
    def __init__(self, items, page, per_page, total):
        self.items = items  # 当前页的项目
        self.page = page
        self.per_page = per_page
        self.total = total # 总项目数
        if self.per_page == 0: # 防止除以零
            self.pages = 0
        else:
            self.pages = (total - 1) // per_page + 1 if total > 0 else 0

        self.prev_num = page - 1 if page > 1 else None
        self.next_num = page + 1 if page < self.pages else None
        self.has_prev = page > 1
        self.has_next = page < self.pages

    def iter_pages(
        self, left_edge=1, left_current=2, right_current=4, right_edge=1 # 调整了默认值以适应更多页码显示
    ):
        last = 0
        for num in range(1, self.pages + 1):
            if (
                num <= left_edge
                or (self.page - left_current - 1 < num < self.page + right_current)
                or num > self.pages - right_edge
            ):
                if last + 1 != num:
                    yield None  # 生成省略号占位符
                yield num
                last = num

@ranking_bp.route("/ranking")
def show_ranking():
    """显示排行榜页面"""
    current_app.logger.debug("--- Entering show_ranking ---") # 新增日志

    page = request.args.get("page", 1, type=int)
    per_page = 15
    current_app.logger.debug(f"Request params: page={page}, per_page={per_page}") # 新增日志

    try:
        all_ranking_ids_tuples = GameStats.query.with_entities(GameStats.ranking_id).distinct().order_by(GameStats.ranking_id).all()
        all_ranking_ids = sorted([r[0] for r in all_ranking_ids_tuples])
        current_app.logger.debug(f"Fetched all_ranking_ids: {all_ranking_ids}") # 新增日志
    except Exception as e:
        current_app.logger.error(f"Error fetching all_ranking_ids: {e}")
        all_ranking_ids = [0]

    default_ranking_id = all_ranking_ids[0] if all_ranking_ids else 0
    ranking_id = request.args.get("ranking_id", default_ranking_id, type=int)
    current_app.logger.debug(f"Determined ranking_id: {ranking_id} (default was {default_ranking_id})") # 新增日志

    if ranking_id not in all_ranking_ids and all_ranking_ids:
        ranking_id = all_ranking_ids[0]
        current_app.logger.debug(f"Corrected ranking_id to: {ranking_id} (was not in all_ranking_ids)") # 新增日志
    elif not all_ranking_ids and ranking_id != 0:
        ranking_id = 0
        current_app.logger.debug(f"Corrected ranking_id to: {ranking_id} (all_ranking_ids was empty)") # 新增日志

    min_games = request.args.get("min_games", 0, type=int)
    current_app.logger.debug(f"min_games: {min_games}") # 新增日志

    try:
        current_app.logger.debug(f"Calling get_leaderboard with ranking_id={ranking_id}, limit=None, min_games_played={min_games}") # 新增日志
        full_leaderboard_raw = get_leaderboard(
            ranking_id=ranking_id,
            limit=None,
            min_games_played=min_games,
        )
        if full_leaderboard_raw is None:
            current_app.logger.warning("get_leaderboard returned None, defaulting to empty list.") # 新增日志
            full_leaderboard_raw = []
        # 打印获取到的原始数据的前几条，以及总数
        current_app.logger.debug(f"Raw data from get_leaderboard (first 3 items): {full_leaderboard_raw[:3]}") # 新增日志
        current_app.logger.debug(f"Total items from get_leaderboard: {len(full_leaderboard_raw)}") # 新增日志

    except Exception as e:
        current_app.logger.error(f"Error fetching leaderboard data for ranking_id {ranking_id}: {e}")
        full_leaderboard_raw = []

    full_leaderboard_with_rank = []
    if isinstance(full_leaderboard_raw, list): # 确保是列表才进行迭代
        for i, player_data in enumerate(full_leaderboard_raw):
            if isinstance(player_data, dict): # 确保列表元素是字典
                player_data_copy = player_data.copy()
                player_data_copy['rank'] = i + 1
                player_data_copy.setdefault('score', player_data_copy.get('elo_score', 0))
                player_data_copy.setdefault('total', player_data_copy.get('games_played', 0))
                if 'win_rate' not in player_data_copy:
                    if player_data_copy.get('total', 0) > 0:
                        player_data_copy['win_rate'] = round((player_data_copy.get('wins', 0) / player_data_copy['total']) * 100, 1)
                    else:
                        player_data_copy['win_rate'] = 0
                full_leaderboard_with_rank.append(player_data_copy)
            else:
                current_app.logger.warning(f"Item in full_leaderboard_raw is not a dict: {player_data}") # 新增日志
    else:
        current_app.logger.error(f"full_leaderboard_raw is not a list: {type(full_leaderboard_raw)}") # 新增日志

    current_app.logger.debug(f"Data after adding rank (first 3 items): {full_leaderboard_with_rank[:3]}") # 新增日志
    current_app.logger.debug(f"Total items after adding rank: {len(full_leaderboard_with_rank)}") # 新增日志

    total_items = len(full_leaderboard_with_rank)
    
    if per_page > 0 :
        total_pages = (total_items - 1) // per_page + 1 if total_items > 0 else 0
        page = max(1, min(page, total_pages if total_pages > 0 else 1)) 
    else: 
        total_pages = 0
        page = 1
    current_app.logger.debug(f"Pagination params: total_items={total_items}, total_pages={total_pages}, current_page={page}") # 新增日志

    offset = (page - 1) * per_page
    leaderboard_page_items = full_leaderboard_with_rank[offset : offset + per_page]
    current_app.logger.debug(f"Items for current page (first 3): {leaderboard_page_items[:3]}") # 新增日志
    current_app.logger.debug(f"Number of items for current page: {len(leaderboard_page_items)}") # 新增日志

    pagination = Pagination(
        items=leaderboard_page_items, 
        page=page, 
        per_page=per_page, 
        total=total_items
    )
    current_app.logger.debug(f"Pagination object created. Has_next: {pagination.has_next}, Has_prev: {pagination.has_prev}, Total pages: {pagination.pages}") # 新增日志

    sort_by = request.args.get("sort_by", "score") 
    current_app.logger.debug("--- Exiting show_ranking, rendering template ---") # 新增日志

    return render_template(
        "ranking.html",
        pagination=pagination,
        current_user=current_user,
        all_ranking_ids=all_ranking_ids,
        current_ranking_id=ranking_id,
    )

@ranking_bp.route("/api/ranking")
def get_ranking_data():
    """获取排行榜数据（API）"""
    limit = request.args.get("limit", 100, type=int)
    min_games = request.args.get("min_games", 1, type=int)
    ranking_id = request.args.get("ranking_id", 0, type=int)
    # sort_by 参数当前未实际用于排序逻辑，但可以接收
    sort_by = request.args.get("sort_by", "score")

    try:
        leaderboard_data_raw = get_leaderboard(
            ranking_id=ranking_id, limit=limit, min_games_played=min_games
        )
        if leaderboard_data_raw is None:
            leaderboard_data_raw = []
    except Exception as e:
        current_app.logger.error(f"API Error fetching leaderboard data for ranking_id {ranking_id}: {e}")
        leaderboard_data_raw = []

    ranking_list_api = []
    for idx, data in enumerate(leaderboard_data_raw):
        # API也需要明确的字段
        entry = {
            "rank": idx + 1, # API 中的排名通常是基于当前查询结果的
            "user_id": data.get("user_id"),
            "username": data.get("username"),
            "score": data.get("elo_score", data.get("score", 0)),
            "wins": data.get("wins", 0),
            "losses": data.get("losses", 0),
            "draws": data.get("draws", 0),
            "total": data.get("games_played", data.get("total",0)),
        }
        if 'win_rate' in data:
            entry['win_rate'] = data['win_rate']
        elif entry['total'] > 0:
            entry['win_rate'] = round((entry['wins'] / entry['total']) * 100, 1)
        else:
            entry['win_rate'] = 0
        ranking_list_api.append(entry)
        
    return jsonify(
        {
            "ranking_id": ranking_id,
            "sort_by": sort_by, 
            "rankings": ranking_list_api,
            "count": len(ranking_list_api), # 返回当前获取到的数量
            # 如果需要总数，需要修改 get_leaderboard 或额外查询
            # "total_players_in_ranking": total_items_for_this_ranking_id (需要额外逻辑)
        }
    )

@ranking_bp.route("/api/user_stats/<string:user_id>")
def get_user_stats(user_id):
    """获取用户统计数据（API）"""
    try:
        user = get_user_by_id(user_id)
    except Exception as e:
        current_app.logger.error(f"API Error fetching user {user_id}: {e}")
        return jsonify({"success": False, "message": "获取用户信息时出错"}), 500

    if not user:
        return jsonify({"success": False, "message": "用户不存在"}), 404

    # 获取 ranking_id，这里可以决定API是查询特定榜单还是所有榜单的汇总
    # 为简单起见，我们假设它查询特定榜单的统计，与模板行为一致
    ranking_id = request.args.get("ranking_id", 0, type=int) 

    try:
        stat = get_game_stats_by_user_id(user_id, ranking_id=ranking_id)
    except Exception as e:
        current_app.logger.error(f"API Error fetching game stats for user {user_id}, ranking_id {ranking_id}: {e}")
        return jsonify({"success": False, "message": "获取用户统计时出错"}), 500

    if not stat:
        return jsonify(
            {
                "success": True, # 操作成功，但无数据
                "user_id": user_id,
                "username": user.username,
                "ranking_id": ranking_id,
                "stats": {}, 
                "message": "该用户在此榜单无统计数据"
            }
        )

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
            "ranking_id": ranking_id,
            "stats": stats_data,
        }
    )

# # author: shihuaidexianyu (refactored by AI assistant)
# # date: 2025-04-25
# # status: done
# # description: 用户排行版块蓝图，包含排行榜和用户统计数据的路由。
# # 包含页面html: ranking.html


# """
# 用户排行版块蓝图，包含排行榜和用户统计数据的路由。
# - 上接后端数据库排行榜 database.actions 和 database.models 操作函数和模型
# - 下接浏览器页面 ranking.html
# """


# from flask import Blueprint, render_template, jsonify, request, current_app
# from flask_login import current_user

# # 导入需要的数据库操作函数和模型
# from database.action import get_leaderboard, get_game_stats_by_user_id, get_user_by_id
# from database.models import User  # User 模型仍然需要用于类型提示或模板

# # 创建蓝图
# ranking_bp = Blueprint("ranking", __name__)


# @ranking_bp.route("/ranking")
# def show_ranking():
#     """显示排行榜页面"""
#     # 获取分页参数
#     page = request.args.get("page", 1, type=int)
#     per_page = 15  # 固定每页20条

#     # 获取其他参数
#     sort_by = request.args.get("sort_by", "score")
#     min_games = request.args.get("min_games", 1, type=int)
#     ranking_id = request.args.get("ranking_id", 0, type=int)
    
#     # 获取所有存在的ranking_id
#     from database.models import GameStats
#     all_ranking_ids = [r[0] for r in 
#         GameStats.query.with_entities(GameStats.ranking_id).distinct().all()]

#     # 获取完整排行榜数据
#     full_leaderboard = get_leaderboard(
#         ranking_id=ranking_id,
#         limit=None,  # 获取全部数据用于分页
#         min_games_played=min_games,
#     )

#     # 手动实现分页逻辑
#     total = len(full_leaderboard)
#     pages = (total - 1) // per_page + 1  # 计算总页数
#     page = max(min(page, pages), 1)  # 限制页码范围
#     offset = (page - 1) * per_page
#     leaderboard_data = full_leaderboard[offset : offset + per_page]

#     # 在 blueprints/ranking.py 中修改分页类
#     class Pagination:
#         def __init__(self, items, page, per_page, total):
#             self.items = items
#             self.page = page
#             self.per_page = per_page
#             self.total = total
#             self.pages = (total - 1) // per_page + 1
#             self.prev_num = page - 1 if page > 1 else None
#             self.next_num = page + 1 if page < self.pages else None
#             self.has_prev = page > 1
#             self.has_next = page < self.pages

#         # 新增迭代页码范围的方法
#         def iter_pages(
#             self, left_edge=2, left_current=2, right_current=4, right_edge=2
#         ):
#             last = 0
#             for num in range(1, self.pages + 1):
#                 if (
#                     num <= left_edge
#                     or (
#                         num > self.page - left_current - 1
#                         and num < self.page + right_current
#                     )
#                     or num > self.pages - right_edge
#                 ):
#                     if last + 1 != num:
#                         yield None  # 生成省略号占位符
#                     yield num
#                     last = num

#     # 生成分页数据
#     ranking_items = []
#     for idx, data in enumerate(leaderboard_data):
#         ranking_items.append(
#             {
#                 "rank": offset + idx + 1,  # 保持全局排名
#                 "username": data["username"],
#                 "user_id": data["user_id"],
#                 "score": data["elo_score"],
#                 "wins": data["wins"],
#                 "losses": data["losses"],
#                 "draws": data["draws"],
#                 "total": data["games_played"],
#                 "win_rate": data["win_rate"],
#             }
#         )

#     # 创建分页对象
#     pagination = Pagination(
#         items=ranking_items, page=page, per_page=per_page, total=total
#     )

#     return render_template(
#         "ranking.html",
#         pagination=pagination,
#         sort_by=sort_by,
#         current_ranking_id=ranking_id,
#         all_ranking_ids=all_ranking_ids,
#         ranking_items=ranking_items,
#     )


# @ranking_bp.route("/api/ranking")
# def get_ranking_data():
#     """获取排行榜数据（API）"""
#     # 获取排序类型
#     sort_by = request.args.get("sort_by", "score")  # sort_by 当前未实际用于排序逻辑
#     limit = request.args.get("limit", 100, type=int)
#     min_games = request.args.get("min_games", 1, type=int)
#     ranking_id = request.args.get("ranking_id", 0, type=int)  # 新增 ranking_id 参数

#     # 获取排行榜数据
#     leaderboard_data = get_leaderboard(
#         ranking_id=ranking_id, limit=limit, min_games_played=min_games
#     )

#     ranking_list = []
#     for idx, data in enumerate(leaderboard_data):
#         ranking_list.append(
#             {
#                 "rank": idx + 1,
#                 "user_id": data["user_id"],
#                 "username": data["username"],
#                 "score": data["elo_score"],
#                 "wins": data["wins"],
#                 "losses": data["losses"],
#                 "draws": data["draws"],
#                 "total": data["games_played"],
#                 "win_rate": data["win_rate"],  # 直接使用计算好的胜率
#             }
#         )

#     return jsonify(
#         {
#             "sort_by": sort_by,  # 仍然返回请求的 sort_by，即使数据总是按 score 排序
#             "rankings": ranking_list,
#             "total": len(ranking_list),
#         }
#     )


# @ranking_bp.route("/api/user_stats/<string:user_id>")  # 使用 string 类型匹配 UUID
# def get_user_stats(user_id):
#     """获取用户统计数据（API）"""
#     # 使用 get_user_by_id 获取用户信息
#     user = get_user_by_id(user_id)
#     if not user:
#         return jsonify({"success": False, "message": "用户不存在"})

#     ranking_id = request.args.get("ranking_id", 0, type=int)  # 新增 ranking_id 参数

#     # 使用 get_game_stats_by_user_id 获取用户统计数据
#     stat = get_game_stats_by_user_id(user_id, ranking_id=ranking_id)  # 传递 ranking_id
#     if not stat:
#         # 如果没有统计数据，返回成功但 stats 为空
#         return jsonify(
#             {
#                 "success": True,
#                 "user_id": user_id,
#                 "username": user.username,
#                 "stats": {},  # 返回空字典表示无统计数据
#             }
#         )

#     # 创建 stats 数据字典
#     stats_data = {
#         "score": stat.elo_score,
#         "wins": stat.wins,
#         "losses": stat.losses,
#         "draws": stat.draws,
#         "total": stat.games_played,
#         "win_rate": (
#             round(stat.wins / stat.games_played * 100, 1)
#             if stat.games_played > 0
#             else 0
#         ),
#     }

#     return jsonify(
#         {
#             "success": True,
#             "user_id": user_id,
#             "username": user.username,
#             "stats": stats_data,  # 返回包含数据的字典
#         }
#     )
