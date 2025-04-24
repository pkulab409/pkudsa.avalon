from .base import db
import logging
from sqlalchemy import select, update, or_, func
import datetime
import json
import uuid
from .models import User, Battle, GameStats, AICode, Room, RoomParticipant

logger = logging.getLogger(__name__)


# 基础数据库操作函数
def safe_commit():
    """安全地提交数据库事务，出错时回滚"""
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logger.error(f"数据库提交失败: {str(e)}")
        return False


# -----------------------------------------------------------------------------------------
# 房间相关操作函数
def create_room(name, host_id, max_players, is_public=True):
    """
    创建游戏房间

    参数:
        name: 房间名称
        host_id: 房主ID
        max_players: 最大玩家数
        is_public: 是否公开

    返回:
        room: 创建的房间对象，如果创建失败则返回None
    """
    try:

        # 创建房间
        room = Room(
            name=name,
            host_id=host_id,
            max_players=max_players,
            status="waiting",
            is_public=is_public,
        )

        # 添加房主作为第一个参与者
        participant = RoomParticipant(
            room_id=room.id, user_id=host_id, is_ai=False, is_host=True, is_ready=False
        )

        db.session.add(room)
        db.session.add(participant)

        if safe_commit():
            return room
        return None
    except Exception as e:
        logger.error(f"创建房间失败: {str(e)}")
        db.session.rollback()
        return None


def join_room(room_id, user_id, is_ai=False, ai_type=None, ai_id=None, ai_name=None):
    """
    加入房间

    参数:
        room_id: 房间ID
        user_id: 用户ID（如果是AI则可为None）
        is_ai: 是否为AI
        ai_type: AI类型
        ai_id: AI ID
        ai_name: AI名称

    返回:
        participant: 创建的参与者对象，如果加入失败则返回None
    """
    try:
        # 查找房间
        room = Room.query.get(room_id)
        if not room:
            return None

        # 检查房间状态
        if room.status != "waiting":
            return None

        # 检查是否已满
        if room.get_current_players_count() >= room.max_players:
            return None

        # 如果是人类玩家，检查是否已在房间中
        if not is_ai and user_id:
            existing = RoomParticipant.query.filter_by(
                room_id=room_id, user_id=user_id, is_ai=False
            ).first()
            if existing:
                return existing

        # 创建参与者记录
        participant = RoomParticipant(
            room_id=room_id,
            user_id=user_id if not is_ai else None,
            is_ai=is_ai,
            ai_type=ai_type,
            ai_id=ai_id,
            ai_name=ai_name,
            is_host=(room.host_id == user_id),
        )

        db.session.add(participant)

        # 如果房间已满，更改状态为ready
        if room.get_current_players_count() + 1 >= room.max_players:
            room.status = "ready"

        if safe_commit():
            return participant
        return None
    except Exception as e:
        logger.error(f"加入房间失败: {str(e)}")
        db.session.rollback()
        return None


def leave_room(room_id, user_id=None, ai_id=None):
    """
    离开房间

    参数:
        room_id: 房间ID
        user_id: 用户ID (如果是人类玩家)
        ai_id: AI ID (如果是AI)

    返回:
        success: 是否成功
        deleted_room: 如果房间被删除，返回True
    """
    try:
        room = Room.query.get(room_id)
        if not room:
            return False, False

        if user_id:
            participant = RoomParticipant.query.filter_by(
                room_id=room_id, user_id=user_id, is_ai=False
            ).first()
        elif ai_id:
            participant = RoomParticipant.query.filter_by(
                room_id=room_id, ai_id=ai_id, is_ai=True
            ).first()
        else:
            return False, False

        if not participant:
            return False, False

        # 删除参与者
        db.session.delete(participant)

        # 如果是房主离开或没有人了，删除房间
        delete_room = False
        if (
            user_id and room.host_id == user_id
        ) or room.get_current_players_count() <= 1:
            db.session.delete(room)
            delete_room = True
        else:
            pass

        safe_commit()
        return True, delete_room
    except Exception as e:
        logger.error(f"离开房间失败: {str(e)}")
        db.session.rollback()
        return False, False


def get_active_rooms(only_public=True, include_ready=True):
    """
    获取活跃房间列表

    参数:
        only_public: 是否只获取公开房间
        include_ready: 是否包含ready状态的房间

    返回:
        rooms: 房间列表
    """
    try:
        query = Room.query

        # 状态过滤
        statuses = ["waiting"]
        if include_ready:
            statuses.append("ready")

        query = query.filter(Room.status.in_(statuses))

        # 公开性过滤
        if only_public:
            query = query.filter_by(is_public=True)

        return query.all()
    except Exception as e:
        logger.error(f"获取房间列表失败: {str(e)}")
        return []


def get_room_details(room_id):
    """
    获取房间详情

    参数:
        room_id: 房间ID

    返回:
        room_details: 包含房间详情和参与者的字典
    """
    try:
        room = Room.query.get(room_id)
        if not room:
            return None

        participants = RoomParticipant.query.filter_by(room_id=room_id).all()

        # 构建结果
        result = {
            "id": room.id,
            "name": room.name,
            "host_id": room.host_id,
            "max_players": room.max_players,
            "status": room.status,
            "is_public": room.is_public,
            "created_at": room.created_at,
            "current_battle_id": room.current_battle_id,
            "participants": [p.to_dict() for p in participants],
            "current_players_count": len(participants),
        }

        return result
    except Exception as e:
        logger.error(f"获取房间详情失败: {str(e)}")
        return None


# AI代码查询和选择函数
def get_room_participants_with_ai_ids(room_id):
    """
    根据room_id查询房间参与者及其选择的AI代码ID

    参数:
        room_id: 房间ID

    返回:
        participants: 包含参与者信息的列表 [{user_id, selected_ai_code_id}, ...]
    """
    try:
        participants = []
        room_participants = RoomParticipant.query.filter_by(
            room_id=room_id, is_ai=False
        ).all()

        for participant in room_participants:
            participants.append(
                {
                    "user_id": participant.user_id,
                    "selected_ai_code_id": participant.selected_ai_code_id,
                }
            )

        return participants
    except Exception as e:
        logger.error(f"获取房间参与者AI代码失败: {str(e)}")
        return []


def get_ai_code_path(ai_code_id):
    """
    根据ai_code_id获取AI代码文件路径

    参数:
        ai_code_id: AI代码ID

    返回:
        code_path: AI代码文件完整的文件系统路径
    """
    try:
        ai_code = AICode.query.get(ai_code_id)
        if not ai_code:
            return None

        # 获取文件存储基础目录，从配置中读取
        from flask import current_app
        import os

        # 获取AI代码上传目录
        upload_dir = os.path.join(current_app.root_path, "uploads", "ai_codes")

        # 构建完整文件路径
        file_path = os.path.join(upload_dir, ai_code.code_path)

        return file_path
    except Exception as e:
        logger.error(f"获取AI代码路径失败: {str(e)}")
        return None


def get_ai_code_metadata(ai_code_id):
    """
    根据ai_code_id获取AI代码元数据

    参数:
        ai_code_id: AI代码ID

    返回:
        metadata: 元数据字典
    """
    try:
        ai_code = AICode.query.get(ai_code_id)
        if not ai_code:
            return None

        metadata = {
            "id": ai_code.id,
            "user_id": ai_code.user_id,
            "name": ai_code.name,
            "code_path": ai_code.code_path,
            "description": ai_code.description,
            "is_active": ai_code.is_active,
            "created_at": ai_code.created_at,
            "version": ai_code.version,
            "status": ai_code.status,
        }

        return metadata
    except Exception as e:
        logger.error(f"获取AI代码元数据失败: {str(e)}")
        return None


def save_ai_selection(room_id, user_id, ai_code_id):
    """
    保存用户在房间中选择的AI代码

    参数:
        room_id: 房间ID
        user_id: 用户ID
        ai_code_id: 选择的AI代码ID

    返回:
        success: 是否成功
    """
    try:
        participant = RoomParticipant.query.filter_by(
            room_id=room_id, user_id=user_id, is_ai=False
        ).first()

        if not participant:
            return False

        # 验证AI代码存在且归属于该用户
        ai_code = AICode.query.get(ai_code_id)
        if not ai_code or ai_code.user_id != user_id:
            return False

        participant.selected_ai_code_id = ai_code_id

        return safe_commit()
    except Exception as e:
        logger.error(f"保存AI选择失败: {str(e)}")
        db.session.rollback()
        return False


def get_user_ai_codes(user_id):
    """
    获取用户的AI代码列表

    参数:
        user_id: 用户ID

    返回:
        ai_codes: 包含AI代码信息的列表
    """
    try:
        query = AICode.query.filter_by(user_id=user_id)

        ai_codes = query.all()

        result = []
        for ai in ai_codes:
            result.append(
                {
                    "id": ai.id,
                    "name": ai.name,
                    "description": ai.description,
                    "is_active": ai.is_active,
                    "status": ai.status,
                }
            )

        return result
    except Exception as e:
        logger.error(f"获取用户AI代码列表失败: {str(e)}")
        return []


def get_ai_code_by_id(ai_code_id):
    """
    根据ID获取AI代码记录

    参数:
        ai_code_id: AI代码ID

    返回:
        AICode对象，找不到则返回None
    """
    try:
        return AICode.query.get(ai_code_id)
    except Exception as e:
        logger.error(f"获取AI代码失败: {str(e)}")
        return None


def get_room_participants(room_id):
    """
    获取房间所有参与者

    参数:
        room_id: 房间ID

    返回:
        参与者列表，出错则返回空列表
    """
    try:
        return RoomParticipant.query.filter_by(room_id=room_id).all()
    except Exception as e:
        logger.error(f"获取房间参与者失败: {str(e)}")
        return []


# -----------------------------------------------------------------------------------------
# 对战相关操作函数
def create_battle(player_ids, room_id=None, **kwargs):
    """
    创建对战记录

    参数:
        player_ids: 参与玩家ID列表
        room_id: 关联的房间ID（可选）
        **kwargs: 其他参数

    返回:
        battle_id: 创建的对战ID，失败则返回None
    """
    try:
        # 生成UUID
        battle_id = str(uuid.uuid4())

        # 将玩家ID列表转为JSON字符串
        player_ids_json = json.dumps(player_ids)

        # 创建对战记录
        battle = Battle(
            id=battle_id,
            room_id=room_id,
            player_ids=player_ids_json,
            status="waiting",
            started_at=datetime.datetime.now(),
        )

        db.session.add(battle)

        # 如果提供了房间ID，更新房间的current_battle_id
        if room_id:
            room = Room.query.get(room_id)
            if room:
                room.current_battle_id = battle_id
                room.status = "playing"

        if safe_commit():
            logger.info(f"创建对战成功: {battle_id}")
            return battle_id
        return None
    except Exception as e:
        logger.error(f"创建对战失败: {str(e)}")
        db.session.rollback()
        return None


def update_battle_status(battle_id, status, **kwargs):
    """
    更新对战状态

    参数:
        battle_id: 对战ID
        status: 新状态
        **kwargs: 其他需要更新的字段

    返回:
        success: 是否成功
    """
    try:
        battle = Battle.query.get(battle_id)
        if not battle:
            return False

        battle.status = status

        # 如果状态为completed或error，设置结束时间
        if status in ["completed", "error"]:
            battle.ended_at = datetime.datetime.now()

        # 更新其他字段
        for key, value in kwargs.items():
            if hasattr(battle, key):
                setattr(battle, key, value)

        # 如果游戏结束，解除房间关联
        if status in ["completed", "error"] and battle.room_id:
            room = Room.query.get(battle.room_id)
            if room and room.current_battle_id == battle_id:
                room.status = "completed"
                room.current_battle_id = None

        return safe_commit()
    except Exception as e:
        logger.error(f"更新对战状态失败: {str(e)}")
        db.session.rollback()
        return False


def end_battle(battle_id, winner_id=None, game_log_uuid=None, results=None):
    """
    结束对战

    参数:
        battle_id: 对战ID
        winner_id: 胜利者ID
        game_log_uuid: 游戏日志UUID
        results: 游戏结果数据

    返回:
        success: 是否成功
    """
    try:
        battle = Battle.query.get(battle_id)
        if not battle:
            return False

        battle.status = "completed"
        battle.ended_at = datetime.datetime.now()

        if winner_id is not None:
            battle.winner_id = winner_id

        if game_log_uuid:
            battle.game_log_uuid = game_log_uuid

        if results:
            battle.results = json.dumps(results)

        # 更新游戏统计
        update_player_stats(battle)

        # 解除房间关联
        if battle.room_id:
            room = Room.query.get(battle.room_id)
            if room and room.current_battle_id == battle_id:
                room.status = "completed"
                room.current_battle_id = None

        return safe_commit()
    except Exception as e:
        logger.error(f"结束对战失败: {str(e)}")
        db.session.rollback()
        return False


def update_player_stats(battle):
    """
    根据对战结果更新玩家统计数据

    参数:
        battle: 对战记录
    """
    try:
        if battle.status != "completed":
            return

        # 解析玩家ID列表
        player_ids = json.loads(battle.player_ids)

        for player_id in player_ids:
            # 获取或创建游戏统计记录
            stats = GameStats.query.filter_by(user_id=player_id).first()

            if not stats:
                stats = GameStats(user_id=player_id)
                db.session.add(stats)

            # 更新游戏场次
            stats.games_played += 1

            # 更新胜负记录
            is_draw = battle.winner_id is None
            if is_draw:
                stats.draws += 1
            elif battle.winner_id == player_id:
                stats.wins += 1
            else:
                stats.losses += 1

            # 更新用户表中的统计数据
            user = User.query.get(player_id)
            if user:
                user.games_played += 1
                if is_draw:
                    user.draws += 1
                elif battle.winner_id == player_id:
                    user.wins += 1
                else:
                    user.losses += 1

        # 如果有胜者和败者，更新ELO积分
        if battle.winner_id and len(player_ids) == 2:
            winner_id = battle.winner_id
            loser_id = (
                [pid for pid in player_ids if pid != winner_id][0]
                if len(player_ids) > 1
                else None
            )

            if loser_id:
                winner_stats = GameStats.query.filter_by(user_id=winner_id).first()
                loser_stats = GameStats.query.filter_by(user_id=loser_id).first()

                if winner_stats and loser_stats:
                    update_elo_scores(winner_stats, loser_stats)

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新玩家统计失败: {str(e)}")


def update_elo_scores(winner_stats, loser_stats, k_factor=32):
    """
    更新ELO积分

    参数:
        winner_stats: 胜者的GameStats对象
        loser_stats: 败者的GameStats对象
        k_factor: K因子，影响积分变化幅度
    """
    # 计算预期胜率
    expected_winner = 1 / (
        1 + 10 ** ((loser_stats.elo_score - winner_stats.elo_score) / 400)
    )
    expected_loser = 1 / (
        1 + 10 ** ((winner_stats.elo_score - loser_stats.elo_score) / 400)
    )

    # 计算新积分
    winner_score_change = k_factor * (1 - expected_winner)
    loser_score_change = k_factor * (0 - expected_loser)

    winner_stats.elo_score = round(winner_stats.elo_score + winner_score_change)
    loser_stats.elo_score = round(loser_stats.elo_score + loser_score_change)

    # 确保积分下限
    winner_stats.elo_score = max(winner_stats.elo_score, 100)
    loser_stats.elo_score = max(loser_stats.elo_score, 100)

    # 记录积分变化以便前端显示
    return winner_score_change, loser_score_change


def get_player_stats(user_id):
    """
    获取玩家统计数据

    参数:
        user_id: 用户ID

    返回:
        stats: 统计数据对象(GameStats)，不存在则返回None
    """
    try:
        stats = GameStats.query.filter_by(user_id=user_id).first()
        return stats
    except Exception as e:
        logger.error(f"获取玩家统计失败: {str(e)}")
        return None


def get_leaderboard(limit=100):
    """
    获取排行榜

    参数:
        limit: 返回数量限制

    返回:
        leaderboard: 排行榜数据
    """
    try:
        leaderboard = (
            db.session.query(GameStats, User.username)
            .join(User, GameStats.user_id == User.id)
            .filter(GameStats.games_played > 0)
            .order_by(GameStats.elo_score.desc())
            .limit(limit)
            .all()
        )

        result = []
        for stats, username in leaderboard:
            result.append(
                {
                    "user_id": stats.user_id,
                    "username": username,
                    "elo_score": stats.elo_score,
                    "games_played": stats.games_played,
                    "wins": stats.wins,
                    "losses": stats.losses,
                    "draws": stats.draws,
                    "win_rate": (
                        round(stats.wins / stats.games_played * 100, 2)
                        if stats.games_played > 0
                        else 0
                    ),
                }
            )

        return result
    except Exception as e:
        logger.error(f"获取排行榜失败: {str(e)}")
        return []


def get_user_battles(user_id, page=1, per_page=10, paginate=True):
    """
    获取用户对战历史

    参数:
        user_id: 用户ID
        page: 页码
        per_page: 每页数量
        paginate: 是否分页

    返回:
        battles: 对战列表
        total: 总数（仅当paginate=True时返回）
    """
    try:
        query = Battle.query.filter(Battle.player_ids.like(f"%{user_id}%")).order_by(
            Battle.started_at.desc()
        )

        # 获取总数
        total = query.count()

        if paginate:
            battles = query.offset((page - 1) * per_page).limit(per_page).all()

            # 进一步过滤结果，确保用户确实在player_ids中
            filtered_battles = []
            for battle in battles:
                players = json.loads(battle.player_ids)
                if user_id in players:
                    filtered_battles.append(battle)

            return filtered_battles, total
        else:
            # 不分页，直接返回限制数量的结果
            battles = query.limit(per_page).all()

            # 进一步过滤结果
            filtered_battles = []
            for battle in battles:
                players = json.loads(battle.player_ids)
                if user_id in players:
                    filtered_battles.append(battle)

            return filtered_battles
    except Exception as e:
        logger.error(f"获取用户对战历史失败: {str(e)}")
        return ([], 0) if paginate else []
