from .base import db
import logging
from sqlalchemy import select, update, or_, func
import datetime
from .models import User, Battle, GameStats
import json

logger = logging.getLogger(__name__)

# 需要实现安全提交函数
def safe_commit():
    """安全地提交数据库事务，出错时回滚"""
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logger.error(f"数据库提交失败: {str(e)}")
        return False

def create_battle(player_ids, game_type, room_id, **kwargs):
    """
    创建新的对战记录

    参数:
        player_ids: 玩家ID列表
        game_type: 游戏类型
        room_id: 房间ID
        **kwargs: 其他参数

    返回:
        Battle对象或None
    """
    try:
        battle_data = {
            "player_ids": json.dumps(player_ids),
            "game_type": game_type,
            "room_id": room_id,
            "started_at": datetime.datetime.now(),
        }

        # 添加其他可选参数
        for key, value in kwargs.items():
            if hasattr(Battle, key):
                battle_data[key] = value

        battle = Battle(**battle_data)
        db.session.add(battle)
        if safe_commit():
            return battle
        return None
    except Exception as e:
        db.session.rollback()
        logger.error(f"创建对战记录失败: {str(e)}")
        return None

def end_battle(
    battle_id,
    winner_ids=None,
    loser_ids=None,
    is_draw=False,
    game_data=None,
    game_data_uuid=None,
):
    """
    结束对战，更新结果

    参数:
        battle_id: 对战ID
        winner_ids: 胜者ID列表
        loser_ids: 败者ID列表
        is_draw: 是否平局
        game_data: 游戏数据JSON字符串
        game_data_uuid: 游戏数据文件UUID

    返回:
        Battle对象或None
    """
    try:
        battle = db.session.get(Battle, battle_id)
        if not battle:
            return None

        battle.ended_at = datetime.datetime.now()

        if is_draw:
            battle.is_draw = True
            battle.winner_ids = None
            battle.loser_ids = None
        else:
            if winner_ids:
                battle.winner_ids = json.dumps(winner_ids)
            if loser_ids:
                battle.loser_ids = json.dumps(loser_ids)
            battle.is_draw = False

        if game_data:
            battle.game_data = game_data

        if game_data_uuid:
            battle.game_data_uuid = game_data_uuid

        # 更新玩家统计数据
        update_player_stats(battle)

        return battle if safe_commit() else None

    except Exception as e:
        db.session.rollback()
        logger.error(f"结束对战失败: {str(e)}")
        return None

def update_player_stats(battle):
    """
    根据对战结果更新玩家统计数据

    参数:
        battle: Battle对象
    """
    try:
        # 获取玩家列表
        player_ids = json.loads(battle.player_ids)

        # 获取或创建每个玩家的统计数据
        player_stats = {}
        for player_id in player_ids:
            stat = GameStats.query.filter_by(
                user_id=player_id, game_type=battle.game_type
            ).first()

            if not stat:
                stat = GameStats(user_id=player_id, game_type=battle.game_type)
                db.session.add(stat)

            # 更新游戏计数和最后游戏时间
            stat.games_played += 1
            stat.last_played = battle.ended_at
            player_stats[player_id] = stat

        # 根据对战结果更新统计
        if battle.is_draw:
            # 平局情况
            for stat in player_stats.values():
                stat.games_draw += 1
        else:
            # 胜负情况
            winner_ids = json.loads(battle.winner_ids) if battle.winner_ids else []
            loser_ids = json.loads(battle.loser_ids) if battle.loser_ids else []

            for player_id, stat in player_stats.items():
                if player_id in winner_ids:
                    stat.games_won += 1
                elif player_id in loser_ids:
                    stat.games_lost += 1

        # 计算新的ELO分数 (仅对两人游戏)
        if (
            not battle.is_draw
            and len(player_ids) == 2
            and battle.winner_ids
            and battle.loser_ids
        ):
            winner_ids = json.loads(battle.winner_ids)
            loser_ids = json.loads(battle.loser_ids)

            if len(winner_ids) == 1 and len(loser_ids) == 1:
                winner_id = winner_ids[0]
                loser_id = loser_ids[0]
                update_elo_scores(
                    player_stats[winner_id], player_stats[loser_id], winner_id
                )

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新玩家统计失败: {str(e)}")

def update_elo_scores(player1_stats, player2_stats, winner_id):
    """
    根据对战结果更新玩家ELO分数

    参数:
        player1_stats: 玩家1的GameStats对象
        player2_stats: 玩家2的GameStats对象
        winner_id: 获胜者ID
    """
    # ELO常数，控制分数变化幅度
    K = 32

    # 计算期望胜率
    r1 = 10 ** (player1_stats.score / 400)
    r2 = 10 ** (player2_stats.score / 400)

    e1 = r1 / (r1 + r2)  # 玩家1的期望胜率
    e2 = r2 / (r1 + r2)  # 玩家2的期望胜率

    # 实际结果
    s1 = 1 if winner_id == player1_stats.user_id else 0
    s2 = 1 if winner_id == player2_stats.user_id else 0

    # 计算新分数
    player1_stats.score = int(player1_stats.score + K * (s1 - e1))
    player2_stats.score = int(player2_stats.score + K * (s2 - e2))

def get_player_stats(user_id, game_type=None):
    """
    获取玩家在特定游戏类型的统计数据

    参数:
        user_id: 用户ID
        game_type: 游戏类型，不指定则获取所有类型

    返回:
        GameStats对象列表
    """
    try:
        query = GameStats.query.filter_by(user_id=user_id)
        if game_type:
            query = query.filter_by(game_type=game_type)
        return query.all()
    except Exception as e:
        logger.error(f"获取玩家统计数据失败: {str(e)}")
        return []

def get_leaderboard(game_type, limit=100):
    """
    获取特定游戏类型的排行榜

    参数:
        game_type: 游戏类型
        limit: 返回数量限制

    返回:
        (GameStats, User)元组的列表，按分数降序排序
    """
    try:
        return (
            GameStats.query.filter_by(game_type=game_type)
            .join(User, GameStats.user_id == User.id)
            .order_by(GameStats.score.desc())
            .with_entities(GameStats, User)
            .limit(limit)
            .all()
        )
    except Exception as e:
        logger.error(f"获取排行榜失败: {str(e)}")
        return []

def get_user_battles(user_id, page=1, per_page=10, paginate=True):
    """
    获取用户的对战历史

    参数:
        user_id: 用户ID
        page: 页码
        per_page: 每页记录数
        paginate: 是否进行分页并返回总数

    返回:
        paginate=True时: (对战列表, 总记录数)元组
        paginate=False时: 对战列表
    """
    try:
        # 由于player_ids是JSON字符串，我们需要使用JSON搜索或文本搜索
        user_id_str = str(user_id)
        query = Battle.query.filter(
            Battle.player_ids.like(f"%{user_id_str}%")
        ).order_by(Battle.started_at.desc())

        if paginate:
            total = query.count()
            battles = query.offset((page - 1) * per_page).limit(per_page).all()

            # 进一步过滤结果，确保用户确实在player_ids中
            filtered_battles = [
                battle for battle in battles if user_id in json.loads(battle.player_ids)
            ]
            return filtered_battles, total
        else:
            # 不分页，直接返回限制数量的结果
            battles = query.limit(per_page).all()

            # 进一步过滤结果
            filtered_battles = [
                battle for battle in battles if user_id in json.loads(battle.player_ids)
            ]
            return filtered_battles
    except Exception as e:
        logger.error(f"获取用户对战历史失败: {str(e)}")
        return ([], 0) if paginate else []
