from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import current_user
from database.action import get_leaderboard, get_game_stats_by_user_id, get_user_by_id
from database.models import User, GameStats
from functools import lru_cache
import time  # 确保导入time模块

ranking_bp = Blueprint("ranking", __name__)

# 添加缓存字典和访问时间管理
_cache = {}
_cache_last_access = {}  # 新增：记录缓存项的最后访问时间
CACHE_TIMEOUT = 300  # 缓存过期阈值：5分钟
RANKING_IDS = [0, 1, 2, 3, 4, 5, 6, 11, 21]


def get_cached_data(key, fetch_func, timeout=CACHE_TIMEOUT):
    """获取缓存数据或者重新获取并缓存

    基于最后访问时间的缓存策略：当距离上次访问超过timeout秒时才更新
    """
    current_time = time.time()

    # 检查缓存是否存在
    if key in _cache:
        # 获取上次访问时间
        last_access_time = _cache_last_access.get(key, 0)
        time_since_last_access = current_time - last_access_time

        # 如果距离上次访问未超过timeout，直接返回缓存数据
        if time_since_last_access < timeout:
            # 更新最后访问时间
            _cache_last_access[key] = current_time
            current_app.logger.debug(
                f"Cache hit for key: {key}, accessed {time_since_last_access:.1f}s ago"
            )
            return _cache[key]
        else:
            current_app.logger.debug(
                f"Cache expired for key: {key}, last accessed {time_since_last_access:.1f}s ago"
            )

    # 缓存不存在或已过期，获取新数据
    current_app.logger.debug(f"Fetching fresh data for key: {key}")
    data = fetch_func()

    # 更新缓存和最后访问时间
    _cache[key] = data
    _cache_last_access[key] = current_time

    return data


@lru_cache(maxsize=8)
def get_all_ranking_ids():
    """获取所有排行榜ID，使用LRU缓存优化"""
    try:
        all_ranking_ids_tuples = (
            GameStats.query.with_entities(GameStats.ranking_id)
            .distinct()
            .order_by(GameStats.ranking_id)
            .all()
        )
        return sorted([r[0] for r in all_ranking_ids_tuples])
    except Exception as e:
        current_app.logger.error(f"Error fetching all_ranking_ids: {e}")
        return [0]


@ranking_bp.route("/")
def show_ranking():
    """显示排行榜页面"""
    current_app.logger.debug("--- Entering show_ranking ---")

    page = request.args.get("page", 1, type=int)
    per_page = 15  # 每页15个项目
    min_games = request.args.get("min_games", 0, type=int)
    is_ajax = request.args.get("ajax", 0, type=int)  # 新增: 检查是否为AJAX请求

    # 获取排行榜ID
    # all_ranking_ids = get_cached_data("all_ranking_ids", get_all_ranking_ids)
    all_ranking_ids = RANKING_IDS
    default_ranking_id = all_ranking_ids[0] if all_ranking_ids else 0
    ranking_id = request.args.get("ranking_id", default_ranking_id, type=int)

    # 修正无效的排行榜ID
    if ranking_id not in all_ranking_ids and all_ranking_ids:
        ranking_id = all_ranking_ids[0]
    elif not all_ranking_ids and ranking_id != 0:
        ranking_id = 0

    current_app.logger.debug(
        f"Request params: page={page}, per_page={per_page}, ranking_id={ranking_id}, min_games={min_games}, is_ajax={is_ajax}"
    )

    # 创建缓存键，包含分页信息
    cache_key = f"ranking_page:{ranking_id}:{page}:{per_page}:{min_games}"

    def fetch_ranking_page_data():
        try:
            # 使用数据库层面的分页获取排行榜数据
            items_for_current_page, total_items_in_db = get_leaderboard(
                ranking_id=ranking_id,
                page=page,
                per_page=per_page,
                min_games_played=min_games,
            )

            if items_for_current_page is None:
                current_app.logger.warning(
                    "get_leaderboard returned None for items, defaulting to empty list."
                )
                return [], 0  # 修复：返回空列表和0，而不是没有返回值

            # 预处理排行榜数据，添加必要信息
            processed_items = []
            for i, player_data in enumerate(items_for_current_page):
                if isinstance(player_data, dict):
                    player_data_copy = player_data.copy()
                    # 计算排名，数据库返回的数据已经是按排名排序的
                    player_data_copy["rank"] = (page - 1) * per_page + i + 1

                    # 确保必要字段存在
                    player_data_copy.setdefault(
                        "score", player_data_copy.get("elo_score", 0)
                    )
                    player_data_copy.setdefault(
                        "total", player_data_copy.get("games_played", 0)
                    )

                    # 计算胜率（如果未提供）
                    if "win_rate" not in player_data_copy:
                        total_games = player_data_copy.get("total", 0)
                        wins = player_data_copy.get("wins", 0)
                        player_data_copy["win_rate"] = (
                            round((wins / total_games) * 100, 1)
                            if total_games > 0
                            else 0
                        )

                    processed_items.append(player_data_copy)
                else:
                    current_app.logger.warning(
                        f"Item in leaderboard is not a dict: {player_data}"
                    )

            return processed_items, total_items_in_db

        except Exception as e:
            current_app.logger.error(f"Error fetching leaderboard data: {e}")
            return [], 0

    # 从缓存获取数据或重新获取
    leaderboard_items, total_count = get_cached_data(
        cache_key, fetch_ranking_page_data, timeout=60
    )

    # 计算分页相关信息
    pages = (total_count - 1) // per_page + 1 if total_count > 0 else 0
    has_prev = page > 1
    has_next = page < pages
    prev_num = page - 1 if has_prev else None
    next_num = page + 1 if has_next else None

    # 如果是 AJAX 请求，返回 JSON 数据
    if is_ajax:
        current_app.logger.debug(
            f"Processing AJAX request for ranking_id={ranking_id}, page={page}"
        )
        pagination_data = {
            "page": page,
            "pages": pages,
            "has_prev": has_prev,
            "has_next": has_next,
            "prev_num": prev_num,
            "next_num": next_num,
            "total": total_count,
        }
        return jsonify(
            {
                "items": leaderboard_items,
                "pagination": pagination_data,
                "ranking_id": ranking_id,
            }
        )

    current_app.logger.debug("--- Exiting show_ranking, rendering template ---")

    return render_template(
        "ranking.html",
        items=leaderboard_items,
        page=page,
        per_page=per_page,
        total=total_count,
        pages=pages,
        has_prev=has_prev,
        has_next=has_next,
        prev_num=prev_num,
        next_num=next_num,
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
    sort_by = request.args.get("sort_by", "score")

    # 限制最大查询数量，防止过大查询
    if limit > 500:
        limit = 500

    cache_key = f"ranking:{ranking_id}:{min_games}:{limit}:{sort_by}"

    def fetch_ranking_data():
        try:
            # 获取排行榜数据，如果失败则返回空列表
            leaderboard_data_raw, _ = get_leaderboard(
                ranking_id=ranking_id, limit=limit, min_games_played=min_games
            ) or ([], 0)

            # 处理数据并添加必要字段
            ranking_list_api = []
            for idx, data in enumerate(leaderboard_data_raw):
                # 预先计算胜率，避免重复计算
                total = data.get("games_played", data.get("total", 0))
                win_rate = data.get("win_rate", 0)
                if "win_rate" not in data and total > 0:
                    win_rate = round((data.get("wins", 0) / total) * 100, 1)

                entry = {
                    "rank": idx + 1,
                    "user_id": data.get("user_id"),
                    "username": data.get("username"),
                    "score": data.get("elo_score", data.get("score", 0)),
                    "wins": data.get("wins", 0),
                    "losses": data.get("losses", 0),
                    "draws": data.get("draws", 0),
                    "total": total,
                    "win_rate": win_rate,
                }
                ranking_list_api.append(entry)

            return {
                "ranking_id": ranking_id,
                "sort_by": sort_by,
                "rankings": ranking_list_api,
                "count": len(ranking_list_api),
            }
        except Exception as e:
            current_app.logger.error(f"Error in get_ranking_data: {e}")
            return {
                "ranking_id": ranking_id,
                "sort_by": sort_by,
                "rankings": [],
                "count": 0,
                "error": str(e),
            }

    result = get_cached_data(
        cache_key, fetch_ranking_data, timeout=120
    )  # 排行榜数据缓存2分钟
    return jsonify(result)


@ranking_bp.route("/api/user_stats/<string:user_id>")
def get_user_stats(user_id):
    """获取用户统计数据（API）"""
    ranking_id = request.args.get("ranking_id", 0, type=int)

    # 使用缓存键包含用户ID和排行榜ID
    cache_key = f"user_stats:{user_id}:{ranking_id}"

    def fetch_user_stats():
        try:
            # 同时获取用户和统计数据，避免分两次查询
            user = get_user_by_id(user_id)
            if not user:
                return {"success": False, "message": "用户不存在"}, 404

            stat = get_game_stats_by_user_id(user_id, ranking_id=ranking_id)

            if not stat:
                return {
                    "success": True,
                    "user_id": user_id,
                    "username": user.username,
                    "ranking_id": ranking_id,
                    "stats": {},
                    "message": "该用户在此榜单无统计数据",
                }

            # 计算一次胜率，避免重复计算
            win_rate = (
                round(stat.wins / stat.games_played * 100, 1)
                if stat.games_played > 0
                else 0
            )

            return {
                "success": True,
                "user_id": user_id,
                "username": user.username,
                "ranking_id": ranking_id,
                "stats": {
                    "score": stat.elo_score,
                    "wins": stat.wins,
                    "losses": stat.losses,
                    "draws": stat.draws,
                    "total": stat.games_played,
                    "win_rate": win_rate,
                },
            }
        except Exception as e:
            current_app.logger.error(f"Error in user_stats: {e}")
            return {"success": False, "message": "获取用户统计时出错"}, 500

    # 获取缓存的结果或新查询的结果
    result = get_cached_data(
        cache_key, fetch_user_stats, timeout=60
    )  # 用户数据缓存时间短一些

    # 如果结果是元组（表示有HTTP状态码），则需要正确返回
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    return jsonify(result)
