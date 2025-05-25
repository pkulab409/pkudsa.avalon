from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import current_user
from database.action import get_leaderboard, get_game_stats_by_user_id, get_user_by_id
from database.models import User, GameStats

ranking_bp = Blueprint("ranking", __name__)


class Pagination:
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        if self.per_page == 0:
            self.pages = 0
        else:
            self.pages = (total - 1) // per_page + 1 if total > 0 else 0

        self.prev_num = page - 1 if page > 1 else None
        self.next_num = page + 1 if page < self.pages else None
        self.has_prev = page > 1
        self.has_next = page < self.pages

    def iter_pages(
        self,
        left_edge=1,
        left_current=2,
        right_current=4,
        right_edge=1,
    ):
        last = 0
        for num in range(1, self.pages + 1):
            if (
                num <= left_edge
                or (self.page - left_current - 1 < num < self.page + right_current)
                or num > self.pages - right_edge
            ):
                if last + 1 != num:
                    yield None
                yield num
                last = num


@ranking_bp.route("/ranking")
def show_ranking():
    """显示排行榜页面"""
    current_app.logger.debug("--- Entering show_ranking ---")

    page = request.args.get("page", 1, type=int)
    per_page = 15  # 每页15个项目
    current_app.logger.debug(f"Request params: page={page}, per_page={per_page}")

    try:
        all_ranking_ids_tuples = (
            GameStats.query.with_entities(GameStats.ranking_id)
            .distinct()
            .order_by(GameStats.ranking_id)
            .all()
        )
        all_ranking_ids = sorted([r[0] for r in all_ranking_ids_tuples])
        current_app.logger.debug(f"Fetched all_ranking_ids: {all_ranking_ids}")
    except Exception as e:
        current_app.logger.error(f"Error fetching all_ranking_ids: {e}")
        all_ranking_ids = [0]

    default_ranking_id = all_ranking_ids[0] if all_ranking_ids else 0
    ranking_id = request.args.get("ranking_id", default_ranking_id, type=int)
    current_app.logger.debug(
        f"Determined ranking_id: {ranking_id} (default was {default_ranking_id})"
    )

    if ranking_id not in all_ranking_ids and all_ranking_ids:
        ranking_id = all_ranking_ids[0]
        current_app.logger.debug(
            f"Corrected ranking_id to: {ranking_id} (was not in all_ranking_ids)"
        )
    elif (
        not all_ranking_ids and ranking_id != 0
    ):  # Ensure ranking_id is 0 if no other IDs exist
        ranking_id = 0
        current_app.logger.debug(
            f"Corrected ranking_id to: {ranking_id} (all_ranking_ids was empty or invalid initial ranking_id)"
        )

    min_games = request.args.get("min_games", 0, type=int)
    current_app.logger.debug(f"min_games: {min_games}")

    paged_leaderboard_items = []
    actual_total_db_items = 0

    try:
        current_app.logger.debug(
            f"Calling get_leaderboard with ranking_id={ranking_id}, page={page}, per_page={per_page}, min_games_played={min_games}"
        )
        # Assumption: get_leaderboard returns items for the current page and the total count across all pages for that ranking_id.
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
            items_for_current_page = []
        actual_total_db_items = (
            total_items_in_db if total_items_in_db is not None else 0
        )

        current_app.logger.debug(
            f"Data from get_leaderboard: {len(items_for_current_page)} items for current page. Total items in DB for ranking: {actual_total_db_items}"
        )
        paged_leaderboard_items = items_for_current_page

    except Exception as e:
        current_app.logger.error(
            f"Error fetching leaderboard data for ranking_id {ranking_id}: {e}"
        )
        # paged_leaderboard_items remains []
        # actual_total_db_items remains 0

    # Process items for the current page, adding correct global rank
    leaderboard_page_items_with_global_rank = []
    if isinstance(paged_leaderboard_items, list):
        for i, player_data in enumerate(paged_leaderboard_items):
            if isinstance(player_data, dict):
                player_data_copy = player_data.copy()
                # Calculate global rank based on current page and item index on page
                player_data_copy["rank"] = (page - 1) * per_page + i + 1

                player_data_copy.setdefault(
                    "score", player_data_copy.get("elo_score", 0)
                )
                player_data_copy.setdefault(
                    "total", player_data_copy.get("games_played", 0)
                )

                if (
                    "win_rate" not in player_data_copy
                ):  # Calculate win_rate if not present
                    total_games = player_data_copy.get("total", 0)
                    wins = player_data_copy.get("wins", 0)
                    player_data_copy["win_rate"] = (
                        round((wins / total_games) * 100, 1) if total_games > 0 else 0
                    )

                leaderboard_page_items_with_global_rank.append(player_data_copy)
            else:
                current_app.logger.warning(
                    f"Item in paged_leaderboard_items is not a dict: {player_data}"
                )
    else:
        current_app.logger.error(
            f"paged_leaderboard_items received from get_leaderboard is not a list: {type(paged_leaderboard_items)}"
        )

    current_app.logger.debug(
        f"Processed items for current page with global rank (first 3): {leaderboard_page_items_with_global_rank[:3]}"
    )
    current_app.logger.debug(
        f"Total items for current page after processing: {len(leaderboard_page_items_with_global_rank)}"
    )

    # Create Pagination object using the items for the current page and the actual total from the database
    pagination = Pagination(
        items=leaderboard_page_items_with_global_rank,  # These are the items to display on this page
        page=page,
        per_page=per_page,
        total=actual_total_db_items,  # This is the grand total for the query
    )
    current_app.logger.debug(
        f"Pagination object created. Page: {pagination.page}, Per_page: {pagination.per_page}, Total_items_in_db: {pagination.total}, Total_pages: {pagination.pages}, Has_next: {pagination.has_next}, Has_prev: {pagination.has_prev}"
    )

    current_app.logger.debug("--- Exiting show_ranking, rendering template ---")

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
        current_app.logger.error(
            f"API Error fetching leaderboard data for ranking_id {ranking_id}: {e}"
        )
        leaderboard_data_raw = []

    ranking_list_api = []
    for idx, data in enumerate(leaderboard_data_raw):
        # API也需要明确的字段
        entry = {
            "rank": idx + 1,  # API 中的排名通常是基于当前查询结果的
            "user_id": data.get("user_id"),
            "username": data.get("username"),
            "score": data.get("elo_score", data.get("score", 0)),
            "wins": data.get("wins", 0),
            "losses": data.get("losses", 0),
            "draws": data.get("draws", 0),
            "total": data.get("games_played", data.get("total", 0)),
        }
        if "win_rate" in data:
            entry["win_rate"] = data["win_rate"]
        elif entry["total"] > 0:
            entry["win_rate"] = round((entry["wins"] / entry["total"]) * 100, 1)
        else:
            entry["win_rate"] = 0
        ranking_list_api.append(entry)

    return jsonify(
        {
            "ranking_id": ranking_id,
            "sort_by": sort_by,
            "rankings": ranking_list_api,
            "count": len(ranking_list_api),  # 返回当前获取到的数量
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
        current_app.logger.error(
            f"API Error fetching game stats for user {user_id}, ranking_id {ranking_id}: {e}"
        )
        return jsonify({"success": False, "message": "获取用户统计时出错"}), 500

    if not stat:
        return jsonify(
            {
                "success": True,  # 操作成功，但无数据
                "user_id": user_id,
                "username": user.username,
                "ranking_id": ranking_id,
                "stats": {},
                "message": "该用户在此榜单无统计数据",
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
