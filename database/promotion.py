"""
这个模块用于处理晋级功能，将一个榜单的前50%玩家晋级到另一个榜单。
"""

import logging
from sqlalchemy import desc
from .models import GameStats, User
from .action import safe_delete, safe_commit
from .base import db
import math

logger = logging.getLogger(__name__)

DEFAULT_NEW_ELO = 1200


def get_top_players_from_ranking(source_ranking_id, percentage=0.5):
    """
    从指定榜单中获取排名前percentage的玩家

    参数:
        source_ranking_id (int): 源榜单ID
        percentage (float): 获取前多少比例的玩家，默认0.5即前50%

    返回:
        list: 符合条件的GameStats对象列表，包含用户ID和ELO分数
    """
    try:
        # 从指定榜单中获取所有有效用户的游戏统计数据（按ELO降序排列）
        all_stats = (
            GameStats.query.filter_by(ranking_id=source_ranking_id)
            .filter(GameStats.games_played > 0)  # 确保只选择至少参与过一场比赛的玩家
            .order_by(
                desc(GameStats.elo_score), desc(GameStats.wins / GameStats.games_played)
            )
            .all()
        )

        # 计算需要选择的玩家数量
        total_players = len(all_stats)
        if total_players == 0:
            logger.warning(f"榜单 {source_ranking_id} 没有有效玩家数据")
            return []

        players_to_select = max(1, math.ceil(total_players * percentage))
        top_players = all_stats[:players_to_select]

        logger.info(
            f"从榜单 {source_ranking_id} 中选择了 {len(top_players)}/{total_players} 名顶尖玩家 (前 {percentage*100:.1f}%)"
        )
        return top_players

    except Exception as e:
        logger.error(
            f"获取榜单 {source_ranking_id} 的顶尖玩家失败: {str(e)}", exc_info=True
        )
        return []


def reset_ranking(ranking_id):
    """
    清空榜单
    """
    game_stats_list = GameStats.query.filter_by(ranking_id=ranking_id).all()
    flag = True
    for game_stats in game_stats_list:
        if not safe_delete(game_stats):
            flag = False
    if flag:
        logger.info(f"成功重置榜单 {ranking_id}.")
    else:
        logger.info(f"未成功重置榜单 {ranking_id}.")
    return flag


def reset_stats(ranking_id):
    """
    重置榜单中所有玩家的战绩
    """
    try:
        game_stats_list = GameStats.query.filter_by(ranking_id=ranking_id).all()
        for game_stats in game_stats_list:
            game_stats.elo_score = DEFAULT_NEW_ELO
            game_stats.games_played = 0
            game_stats.wins = 0
            game_stats.losses = 0
            game_stats.draws = 0
        safe_commit()
        logger.info(f"成功重置榜单 {ranking_id}中所有玩家的战绩.")
        return True
    except Exception as e:
        db.session.rollback()
        logger.info(f"未成功重置榜单 {ranking_id}中所有玩家的战绩.")
        return False


def promote_players_to_ranking(players_stats, target_ranking_id):
    """
    将指定玩家列表晋级到目标榜单

    参数:
        players_stats (list): GameStats对象列表
        target_ranking_id (int): 目标榜单ID

    返回:
        tuple: (成功数, 总数, 错误信息)
    """
    success_count = 0
    errors = []

    try:
        for stat in players_stats:
            user_id = stat.user_id

            # 检查用户在目标榜单中是否已有记录
            existing_stat = GameStats.query.filter_by(
                user_id=user_id, ranking_id=target_ranking_id
            ).first()

            if existing_stat:
                # 如果已存在，更新为源榜单的ELO值
                # 可以根据需要决定是否保留原有ELO或使用平均值等其他策略
                existing_stat.elo_score = DEFAULT_NEW_ELO
                db.session.add(existing_stat)
                logger.info(
                    f"更新用户 {user_id} 在榜单 {target_ranking_id} 的ELO为{DEFAULT_NEW_ELO}."
                )
            else:
                # 如果不存在，创建新记录
                new_stat = GameStats(
                    user_id=user_id,
                    ranking_id=target_ranking_id,
                    elo_score=DEFAULT_NEW_ELO,
                    games_played=0,  # 在新榜单中初始为0场比赛
                    wins=0,
                    losses=0,
                    draws=0,
                )
                db.session.add(new_stat)
                logger.info(
                    f"将用户 {user_id} 晋级到榜单 {target_ranking_id}，初始ELO为{DEFAULT_NEW_ELO}."
                )

            success_count += 1

        # 提交所有更改
        safe_commit()
        logger.info(
            f"成功将 {success_count}/{len(players_stats)} 名玩家晋级到榜单 {target_ranking_id}"
        )

    except Exception as e:
        db.session.rollback()
        error_msg = f"晋级玩家到榜单 {target_ranking_id} 失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        errors.append(error_msg)

    return success_count, len(players_stats), errors


def promote_from_multiple_rankings(
    source_ranking_ids, target_ranking_id, percentage=0.5
):
    """
    将多个源榜单的前percentage玩家晋级到目标榜单

    参数:
        source_ranking_ids (list): 源榜单ID列表
        target_ranking_id (int): 目标榜单ID
        percentage (float): 每个榜单晋级的比例，默认0.5

    返回:
        dict: 包含总结果和每个榜单的详细结果
    """
    total_success = 0
    total_players = 0
    all_errors = []
    ranking_results = {}

    for ranking_id in source_ranking_ids:
        # 获取当前榜单的顶尖玩家
        top_players = get_top_players_from_ranking(ranking_id, percentage)

        if not top_players:
            ranking_results[ranking_id] = {
                "success": 0,
                "total": 0,
                "errors": [f"榜单 {ranking_id} 没有有效玩家"],
            }
            all_errors.append(f"榜单 {ranking_id} 没有有效玩家")
            continue

        # 晋级玩家到目标榜单
        success, total, errors = promote_players_to_ranking(
            top_players, target_ranking_id
        )

        # 记录结果
        total_success += success
        total_players += total
        all_errors.extend(errors)

        ranking_results[ranking_id] = {
            "success": success,
            "total": total,
            "errors": errors,
        }

    return {
        "summary": {
            "success": total_success,
            "total": total_players,
            "errors": all_errors,
        },
        "details": ranking_results,
    }
