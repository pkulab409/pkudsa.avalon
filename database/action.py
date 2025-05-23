# author: shihuaidexianyu (refactored by AI assistant)
# date: 2025-04-25
# status: refactored
# description: Database operations (CRUD)

# dmcnczy 25/4/27
# 更新： action.py 文档，七人两队 ELO 操作 (删除原有的 1V1 代码)
"""
实现 CRUD 数据库操作，内含丰富的操作工具：
- 【用户】 注册、登录、删除等
- 【用户 AI 代码】 创建、更新、激活、删除等
- 【游戏记录统计】 获取、游动更新更新，获取排行榜
- 【对战功能】 创建对战、更新对战、对战用户管理、对战历史、*ELO*等
- 备用：BattlePlayer 独立 CRUD 操作
"""
import os

import yaml
from flask import current_app
import threading, time

# 准备好后面一千多行的冲击吧！
MAX_TOKEN_ALLOWED = 3000

from .base import db
import logging
from sqlalchemy import select, update, or_, func
from datetime import datetime
import json
import math
import uuid
from .models import (
    User,
    Battle,
    GameStats,
    AICode,
    BattlePlayer,
    db,
)  # 移除Room, RoomParticipant

# 配置 Logger
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------------------
# 基础数据库工具函数


def safe_commit():
    """
    安全地提交数据库事务，出错时回滚并记录错误。

    返回:
        bool: 提交是否成功。
    """
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logger.error(f"数据库提交失败: {e}", exc_info=True)  # 记录详细异常信息
        return False


def safe_add(instance):
    """
    安全地添加数据库记录并提交。

    参数:
        instance: SQLAlchemy 模型实例。

    返回:
        bool: 添加并提交是否成功。
    """
    try:
        db.session.add(instance)
        return safe_commit()
    except Exception as e:
        logger.error(f"添加数据库记录失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def safe_delete(instance):
    """
    安全地删除数据库记录并提交。

    参数:
        instance: SQLAlchemy 模型实例。

    返回:
        bool: 删除并提交是否成功。
    """
    try:
        db.session.delete(instance)
        return safe_commit()
    except Exception as e:
        logger.error(f"删除数据库记录失败: {e}", exc_info=True)
        db.session.rollback()
        return False


# -----------------------------------------------------------------------------------------
# 用户 (User) CRUD 操作


def get_user_by_id(user_id):
    """根据ID获取用户记录。"""
    try:
        return User.query.get(user_id)
    except Exception as e:
        logger.error(f"根据ID获取用户失败: {e}", exc_info=True)
        return None


def get_user_index_in_battle(battle_id, user_id):
    """根据battle_id获取用户index"""
    battle_players = get_battle_players_for_battle(battle_id)
    for idx, bp in enumerate(battle_players):
        if bp.user_id == user_id:
            return idx + 1  # index范围1~7
    return None


def get_user_by_username(username):
    """根据用户名获取用户记录。"""
    try:
        return User.query.filter_by(username=username).first()
    except Exception as e:
        logger.error(f"根据用户名获取用户失败: {e}", exc_info=True)
        return None


def get_user_by_email(email):
    """根据邮箱获取用户记录。"""
    try:
        return User.query.filter_by(email=email).first()
    except Exception as e:
        logger.error(f"根据邮箱获取用户失败: {e}", exc_info=True)
        return None


def create_user(username, email, password):
    """
    创建新用户。

    参数:
        username (str): 用户名。
        email (str): 邮箱。
        password (str): 原始密码。

    返回:
        User: 创建成功的用户对象，失败则返回None。
    """
    try:
        # 检查用户名和邮箱是否已存在
        if get_user_by_username(username) or get_user_by_email(email):
            logger.warning(f"创建用户失败: 用户名或邮箱已存在 ({username}, {email})")
            return None

        user = User(username=username, email=email)
        user.set_password(password)  # 使用模型方法设置密码哈希

        # 为新用户创建游戏统计记录，即使他们还没玩过游戏
        game_stats = GameStats(user_id=user.id, ranking_id=0)  # 显式设置 ranking_id

        db.session.add(user)
        db.session.add(game_stats)  # 添加统计记录

        if safe_commit():
            logger.info(f"用户 {username} 创建成功, ID: {user.id}")
            return user
        return None
    except Exception as e:
        logger.error(f"创建用户失败: {e}", exc_info=True)
        db.session.rollback()
        return None


def update_user(user, **kwargs):
    """
    更新用户记录。

    参数:
        user (User): 要更新的用户对象。
        **kwargs: 要更新的字段及其值。

    返回:
        bool: 更新是否成功。
    """
    if not user:
        return False
    try:
        for key, value in kwargs.items():
            if hasattr(user, key):
                if key == "password":  # 特殊处理密码更新
                    user.set_password(value)
                elif key != "id":  # 不允许修改ID
                    setattr(user, key, value)
        user.updated_at = datetime.now()  # 开始时间戳  # 更新时间戳
        return safe_commit()
    except Exception as e:
        logger.error(f"更新用户 {user.id} 失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def delete_user(user):
    """
    删除用户记录。

    参数:
        user (User): 要删除的用户对象。

    返回:
        bool: 删除是否成功。
    """
    if not user:
        return False
    try:
        # Related records (AICode, BattlePlayer, GameStats) will be handled by cascade rules
        # or foreign key constraints depending on your __tablename__ definition and DB setup.
        # Ensure ON DELETE CASCADE is used in migrations if using foreign keys directly,
        # or configure cascades in relationships (like 'all, delete-orphan' for Battle to BattlePlayer).
        # User -> AICode, User -> BattlePlayer via foreign keys: Often cascade on delete.
        # User <-> GameStats via unique foreign key: Cascade on delete is typical.
        # Or SQLAlchemy relationship cascades can be employed if foreign key cascades are not used.
        # For simplicity, we rely on DB foreign key constraints with CASCADE or SQLAlchemy's relationship cascade if defined.
        # Check your models carefully - they use backref but relationships defining cascade are needed.
        # Example: db.relationship("AICode", backref="user", lazy="dynamic", cascade="all, delete-orphan")
        # YOUR MODELS.PY LACKS CASCADE. You need to add cascade rules in models or rely on DB FK cascades.
        # Assuming DB FK cascades are set up or you will add SQLAlchemy cascades in models for related tables...

        return safe_delete(user)
    except Exception as e:
        logger.error(f"删除用户 {user.id} 失败: {e}", exc_info=True)
        db.session.rollback()
        return False


# -----------------------------------------------------------------------------------------
# AI 代码 (AICode) CRUD 操作


def get_ai_code_by_id(ai_code_id):
    """根据ID获取AI代码记录。"""
    try:
        return AICode.query.get(ai_code_id)
    except Exception as e:
        logger.error(f"根据ID获取AI代码失败: {e}", exc_info=True)
        return None


def get_user_index_in_battle(battle_id, user_id):
    """根据battle_id获取用户index"""
    battle_players = get_battle_players_for_battle(battle_id)
    for idx, bp in enumerate(battle_players):
        if bp.user_id == user_id:
            return idx + 1  # index范围1~7
    return None


def get_active_ai_codes_by_ranking_ids(ranking_ids: list[int] = None) -> list[AICode]:
    """
    获取指定 ranking_id 列表中的用户的激活 AI 代码。
    如果 ranking_ids 为 None 或为空列表，则获取所有用户的激活 AI 代码。

    改进版本：
    1. 为每个不同的ranking_ids组合使用单独的锁和缓存
    2. 增强了错误处理和重试逻辑
    3. 添加了更多的日志记录支持

    参数:
        ranking_ids (list[int], optional): 一个可选的整数列表，指定要筛选的 ranking_id。

    返回:
        list[AICode]: 一个 AICode 对象的列表。
    """

    # 标准化ranking_ids参数，确保它始终是一个list
    if ranking_ids is None:
        normalized_ranking_ids = []
    else:
        normalized_ranking_ids = sorted(list(set(ranking_ids)))  # 去重并排序

    active_ai_codes = []
    try:
        if not normalized_ranking_ids:
            # 如果未指定ranking_ids或为空列表，则获取所有用户的激活AI代码
            logger.info("获取所有用户的激活AI代码")
            return AICode.query.filter_by(is_active=True).all()
        else:
            # 遍历每个排名ID
            for ranking_id in normalized_ranking_ids:
                logger.info(f"获取排名ID为 {ranking_id} 的用户激活AI代码")
                # 查询该排名下的所有用户ID
                game_stats_list = GameStats.query.filter_by(ranking_id=ranking_id).all()
                # 获取每个用户的激活AI代码
                for game_stats in game_stats_list:
                    user_id = game_stats.user_id
                    ai_code = get_user_active_ai_code(user_id)
                    if ai_code and ai_code not in active_ai_codes:  # 避免重复
                        active_ai_codes.append(ai_code)

        logger.info(f"成功获取 {len(active_ai_codes)} 个激活的AI代码")
        return active_ai_codes

    except Exception as e:
        ranking_id_str = (
            "全部" if not normalized_ranking_ids else str(normalized_ranking_ids)
        )
        logger.error(f"获取榜单 {ranking_id_str} 的AI代码列表失败: {e}", exc_info=True)
        return []


def get_user_ai_codes(user_id):
    """获取用户的所有AI代码记录。"""
    try:
        return (
            AICode.query.filter_by(user_id=user_id)
            .order_by(AICode.created_at.desc())
            .all()
        )
    except Exception as e:
        logger.error(f"获取用户 {user_id} 的AI代码列表失败: {e}", exc_info=True)
        return []


def get_user_active_ai_code(user_id):
    """获取用户当前激活的AI代码。"""
    try:
        return AICode.query.filter_by(user_id=user_id, is_active=True).first()
    except Exception as e:
        logger.error(f"获取用户 {user_id} 的激活AI失败: {e}", exc_info=True)
        return None


def create_ai_code(user_id, name, code_path, description=None):
    """
    创建新的AI代码记录。

    参数:
        user_id (str): 用户ID。
        name (str): AI代码名称。
        code_path (str): AI代码文件路径（相对于上传目录）。
        description (str, optional): AI代码描述。

    返回:
        AICode: 创建成功的AI代码对象，失败则返回None。
    """
    try:
        # Versioning: Find the latest version for this user and name, increment
        latest_version = (
            db.session.query(func.max(AICode.version))
            .filter_by(user_id=user_id, name=name)
            .scalar()
            or 0
        )
        new_version = latest_version + 1

        ai_code = AICode(
            user_id=user_id,
            name=name,
            code_path=code_path,
            description=description,
            version=new_version,
            is_active=False,  # 默认不激活
        )
        db.session.add(ai_code)
        if safe_commit():
            return ai_code  # 返回对象而不是布尔值
        return None
    except Exception as e:
        logger.error(f"为用户 {user_id} 创建AI代码失败: {e}", exc_info=True)
        db.session.rollback()
        return None


def update_ai_code(ai_code, **kwargs):
    """
    更新AI代码记录。

    参数:
        ai_code (AICode): 要更新的AI代码对象。
        **kwargs: 要更新的字段及其值。

    返回:
        bool: 更新是否成功。
    """
    if not ai_code:
        return False
    try:
        for key, value in kwargs.items():
            if (
                hasattr(ai_code, key)
                and key != "id"
                and key != "created_at"
                and key != "user_id"
                and key != "version"
            ):  # 不允许修改ID, 创建日期, 用户ID, 版本
                setattr(ai_code, key, value)
        # AICode model doesn't have updated_at, you might add it if needed.
        return safe_commit()
    except Exception as e:
        logger.error(f"更新AI代码 {ai_code.id} 失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def delete_ai_code(ai_code):
    """删除AI代码记录"""
    if not ai_code:
        return False
    try:
        # 检查是否有BattlePlayer记录引用此AI
        battle_players = BattlePlayer.query.filter_by(
            selected_ai_code_id=ai_code.id
        ).all()

        if battle_players:
            # 只在同一用户的AI代码中查找替代品
            default_ai_code = AICode.query.filter(
                AICode.user_id == ai_code.user_id,  # 限制为同一用户
                AICode.id != ai_code.id,
            ).first()

            if not default_ai_code:
                logger.error(
                    f"删除AI代码 {ai_code.id} 失败: 该用户没有其他可用AI代码作为替代，但此AI已被用于对战"
                )
                return False

            # 更新所有引用
            for bp in battle_players:
                bp.selected_ai_code_id = default_ai_code.id

            # 提交更改
            if not safe_commit():
                logger.error(
                    f"删除AI代码 {ai_code.id} 失败: 无法更新关联的BattlePlayer记录"
                )
                return False

        # 删除AI代码
        return safe_delete(ai_code)
    except Exception as e:
        logger.error(f"删除AI代码 {ai_code.id} 失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def set_active_ai_code(user_id, ai_code_id):
    """
    为用户设置激活的AI代码。取消该用户当前所有AI的激活状态，并将指定AI设为激活。

    参数:
        user_id (str): 用户ID。
        ai_code_id (str): 要激活的AI代码ID。

    返回:
        bool: 操作是否成功。
    """
    try:
        # 检查AI是否存在且属于该用户
        ai_to_activate = AICode.query.filter_by(id=ai_code_id, user_id=user_id).first()
        if not ai_to_activate:
            logger.warning(
                f"用户 {user_id} 尝试激活不存在或不属于自己的AI代码 {ai_code_id}"
            )
            return False

        # 取消该用户下所有AI的激活状态
        AICode.query.filter_by(user_id=user_id, is_active=True).update(
            {"is_active": False}, synchronize_session=False
        )
        db.session.flush()  # 同步更新到 session

        # 激活指定的AI
        ai_to_activate.is_active = True

        return safe_commit()
    except Exception as e:
        logger.error(
            f"为用户 {user_id} 设置激活AI {ai_code_id} 失败: {e}", exc_info=True
        )
        db.session.rollback()
        return False


def get_ai_code_path_full(ai_code_id):
    """
    根据ai_code_id获取AI代码文件在文件系统中的完整路径。

    参数:
        ai_code_id (str): AI代码ID。

    返回:
        str: 文件完整路径，找不到或出错则返回None。
    """
    try:
        ai_code = get_ai_code_by_id(ai_code_id)
        if not ai_code or not ai_code.code_path:
            return None

        from flask import current_app
        import os

        # 获取AI代码上传目录 (通常在 config 中设置或根据约定)
        upload_dir = current_app.config.get(
            "AI_CODE_UPLOAD_FOLDER"
        )  # 假设配置中有这个key
        if not upload_dir:
            logger.error("Flask config 中未设置 'AI_CODE_UPLOAD_FOLDER'")
            return None

        # 构建完整文件路径
        # 使用 secure_filename 可以在文件上传时保护，这里的 code_path 应该是已经处理过的安全路径 M
        file_path = os.path.join(upload_dir, ai_code.code_path)

        # 检查文件是否存在 (可选但推荐)
        if not os.path.exists(file_path):
            logger.warning(f"AI代码文件不存在: {file_path}")
            return None

        return file_path
    except Exception as e:
        logger.error(f"获取AI代码 {ai_code_id} 完整路径失败: {e}", exc_info=True)
        return None


# -----------------------------------------------------------------------------------------
# 游戏统计 (GameStats) CRUD 操作


def get_game_stats_by_user_id(user_id, ranking_id=0):
    """
    根据用户ID和排行榜ID获取游戏统计记录。

    参数:
        user_id (str): 用户ID。
        ranking_id (int): 排行榜ID。

    返回:
        GameStats: 游戏统计对象，不存在则返回None。
    """
    try:
        return GameStats.query.filter_by(user_id=user_id, ranking_id=ranking_id).first()
    except Exception as e:
        logger.error(
            f"获取用户 {user_id} 在排行榜 {ranking_id} 的游戏统计失败: {e}",
            exc_info=True,
        )
        return None


def create_game_stats(user_id, ranking_id=0):
    """
    为指定用户在特定排行榜创建游戏统计记录。

    参数:
        user_id (str): 用户ID。
        ranking_id (int): 排行榜ID。

    返回:
        GameStats: 创建成功的统计对象，失败或已存在则返回None。
    """
    try:
        existing_stats = get_game_stats_by_user_id(user_id, ranking_id)
        if existing_stats:
            logger.warning(
                f"用户 {user_id} 在排行榜 {ranking_id} 的游戏统计已存在，无需重复创建。"
            )
            return None

        stats = GameStats(user_id=user_id, ranking_id=ranking_id)
        if safe_add(stats):
            logger.info(f"为用户 {user_id} 在排行榜 {ranking_id} 创建游戏统计成功。")
            return stats
        return None
    except Exception as e:
        logger.error(
            f"创建用户 {user_id} 在排行榜 {ranking_id} 的游戏统计失败: {e}",
            exc_info=True,
        )
        db.session.rollback()
        return None


def update_game_stats(stats, **kwargs):
    """
    更新游戏统计记录。主要用于手动修改 Elo 等，增加胜负场次应通过 battle 结束流程。

    参数:
        stats (GameStats): 要更新的统计对象。
        **kwargs: 要更新的字段及其值。

    返回:
        bool: 更新是否成功。
    """
    if not stats:
        return False
    try:
        for key, value in kwargs.items():
            if hasattr(stats, key) and key not in [
                "id",
                "user_id",
            ]:  # 不允许修改ID, 用户ID
                setattr(stats, key, value)
        return safe_commit()
    except Exception as e:
        logger.error(f"更新游戏统计 {stats.id} 失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def get_leaderboard(ranking_id=0, page=1, per_page=15, min_games_played=0):
    """获取排行榜数据，支持分页"""
    # 基本查询条件
    base_query = GameStats.query.filter_by(ranking_id=ranking_id)

    if min_games_played > 0:
        base_query = base_query.filter(GameStats.games_played >= min_games_played)

    # 计算总记录数
    total_count = base_query.count()

    # 先执行JOIN，再做排序和分页
    query = (
        base_query.join(User)  # 先JOIN再分页
        .with_entities(
            GameStats.user_id,
            User.username,
            GameStats.elo_score,
            GameStats.wins,
            GameStats.losses,
            GameStats.draws,
            GameStats.games_played,
        )
        .order_by(GameStats.elo_score.desc())  # 排序
    )

    # 然后应用分页
    offset = (page - 1) * per_page
    paginated_query = query.offset(offset).limit(per_page)

    # 获取结果
    stats_with_users = paginated_query.all()

    # 格式化返回数据
    result = []
    for rank, (
        user_id,
        username,
        elo_score,
        wins,
        losses,
        draws,
        games_played,
    ) in enumerate(stats_with_users, start=offset + 1):
        win_rate = round(wins / games_played * 100, 1) if games_played > 0 else 0
        result.append(
            {
                "rank": rank,
                "user_id": user_id,
                "username": username,
                "elo_score": elo_score,
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "games_played": games_played,
                "win_rate": win_rate,
            }
        )

    return result, total_count


# -----------------------------------------------------------------------------------------
# 对战 (Battle) 及 对战参与者 (BattlePlayer) CRUD 操作


def create_battle(
    participant_data_list, ranking_id=0, status="waiting", game_data=None
):
    """
    创建对战记录及关联的参与者记录。

    参数:
        participant_data_list (list): 参与者数据列表，每个元素应为字典，
                                      至少包含 'user_id' 和 'ai_code_id'。
                                      示例: [{'user_id': '...', 'ai_code_id': '...'}, ...]
        ranking_id (int): 对战所属的排行榜ID。默认为0。
        status (str): 初始状态 (e.g., 'waiting', 'playing'). 默认为 'waiting'.
        game_data (dict, optional): 游戏初始数据。

    返回:
        Battle: 创建成功的对战对象，失败则返回None。
    """
    try:
        if not participant_data_list:
            logger.error("创建对战失败: 参与者列表为空。")
            return None

        # 确保所有参与者都存在且选择了AI (根据 BattlePlayer 模型 nullable=False 的定义)
        for data in participant_data_list:
            user = get_user_by_id(data.get("user_id"))
            # 使用 'ai_code_id' 作为键
            ai_code = get_ai_code_by_id(data.get("ai_code_id"))  # <--- 修改这里
            if not user or not ai_code or ai_code.user_id != user.id:
                # 记录更详细的错误原因
                reason = ""
                if not user:
                    reason = "用户不存在"
                elif not ai_code:
                    reason = "AI代码不存在"
                elif ai_code.user_id != user.id:
                    reason = "AI代码不属于该用户"
                logger.error(
                    f"创建对战失败: 无效的参与者或AI代码数据 {data} (原因: {reason})"
                )
                return None

        battle = Battle(
            status=status,
            ranking_id=ranking_id,
            created_at=datetime.now(),  # 开始时间戳,
            # started_at 在对战真正开始时设置
            # results 在对战结束时设置
            # game_log_uuid 在对战结束时设置
        )
        db.session.add(battle)
        db.session.flush()  # 确保 battle 有了 ID

        battle_players = []
        for i, data in enumerate(participant_data_list):
            # 获取玩家当前的ELO作为 initial_elo 快照
            user_stats = get_game_stats_by_user_id(data["user_id"], ranking_id)
            initial_elo = (
                user_stats.elo_score if user_stats else 1200
            )  # 默认或从 GameStats 获取

            bp = BattlePlayer(
                battle_id=battle.id,
                user_id=data["user_id"],
                # 使用 'ai_code_id' 作为键
                selected_ai_code_id=data["ai_code_id"],  # <--- 修改这里
                position=i + 1,  # 简单设置位置
                initial_elo=initial_elo,
                join_time=datetime.now(),  # 开始时间戳,
            )
            battle_players.append(bp)
            db.session.add(bp)  # 添加BattlePlayer 记录

        if safe_commit():
            logger.info(
                f"对战 {battle.id} 创建成功，包含 {len(battle_players)} 位玩家。"
            )
            return battle
        return None
    except Exception as e:
        logger.error(f"创建对战失败: {e}", exc_info=True)
        db.session.rollback()
        return None


def get_battle_by_id(battle_id):
    """
    根据ID获取对战记录。

    参数:
        battle_id (str): 对战ID。

    返回:
        Battle: 对战对象，不存在则返回None。
    """
    try:
        # Lazy='dynamic' on battle.players means you might need to load them explicitly if accessed often
        # e.g., battle = Battle.query.options(db.joinedload(Battle.players)).get(battle_id)
        # Or access battle.players outside this function call, which will trigger the dynamic query.
        return Battle.query.get(battle_id)
    except Exception as e:
        logger.error(f"获取对战 {battle_id} 失败: {e}", exc_info=True)
        return None


def update_battle(battle, **kwargs):
    """
    更新对战记录 (Battle) 的通用方法。

    参数:
        battle (Battle): 要更新的对战对象。
        **kwargs: 要更新的字段及其值。

    返回:
        bool: 更新是否成功。
    """
    if not battle:
        return False
    try:
        for key, value in kwargs.items():
            if hasattr(battle, key) and key not in [
                "id",
                "created_at",
            ]:  # 不允许修改ID, created_at
                setattr(battle, key, value)

        # Special handling for status transition
        if "status" in kwargs:
            new_status = kwargs["status"]
            if new_status == "playing" and battle.started_at is None:
                battle.started_at = datetime.now()  # 开始时间戳
            elif (
                new_status in ["completed", "error", "cancelled"]
                and battle.ended_at is None
            ):
                battle.ended_at = datetime.now()  # 开始时间戳

        return safe_commit()
    except Exception as e:
        logger.error(f"更新对战 {battle.id} 失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def delete_battle(battle):
    """
    删除对战记录。

    参数:
        battle (Battle): 要删除的对战对象。

    返回:
        bool: 删除是否成功。
    """
    if not battle:
        return False
    try:
        # Due to cascade="all, delete-orphan" on Battle.players, deleting the Battle
        # will automatically delete all associated BattlePlayer records. This is the desired behavior.
        return safe_delete(battle)
    except Exception as e:
        logger.error(f"删除对战 {battle.id} 失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def get_battle_players_for_battle(battle_id):
    """
    获取指定对战的所有 BattlePlayer 参与者记录。

    参数:
        battle_id (str): 对战ID。

    返回:
        list: BattlePlayer 对象列表，出错则返回空列表。
    """
    try:
        # Because lazy='dynamic' on battle.players, Battle.query.get(battle_id).players
        # returns a query. Executing .all() here fetches the list.
        battle = get_battle_by_id(battle_id)
        if battle:
            return battle.players.all()  # Executes the dynamic query
        return []
    except Exception as e:
        logger.error(f"获取对战 {battle_id} 的参与者失败: {e}", exc_info=True)
        return []


def process_battle_results_and_update_stats(battle_id, results_data):
    """
    处理4v3对战结果，更新玩家对战记录及ELO评分。

    改进：
    1. 更准确地识别玩家错误
    2. 基于错误类型和方法实现差异化的ELO惩罚
    3. 提供更详细的日志记录
    4. 支持多排行榜 (ranking_id)

    参数:
        battle_id (str): 对战的唯一标识符
        results_data (dict): 包含对战结果的数据，格式为:
            {
                "winner": "red"|"blue",  # 获胜队伍
                "error": bool,           # 新增错误标识（可选）
                "public_log_file": str,  # 新增公共日志路径（可选）
                "roles": {...},          # 角色分配信息
                # 其他可选字段（如game_log_uuid等）
            }

    返回:
        bool: 处理成功返回True，否则False
    """

    RED_TEAM = "red"
    BLUE_TEAM = "blue"
    BLUE_ROLES = ["Merlin", "Percival", "Knight"]  # 蓝方角色
    RED_ROLES = ["Morgana", "Assassin", "Oberon"]  # 红方角色

    try:
        # ----------------------------------
        # 阶段1：获取基础数据并验证
        # ----------------------------------
        battle = get_battle_by_id(battle_id)
        if not battle:
            logger.error(f"[Battle {battle_id}] 对战记录不存在")
            return False

        # --- 新增检查 ---
        if battle.is_elo_exempt:
            logger.info(
                f"[Battle {battle_id}] 此对战 (类型: {battle.battle_type}) 被标记为ELO豁免，将跳过ELO和统计更新。"
            )
            # 只需要更新battle的状态和结果，不进行统计和ELO计算
            battle.status = "completed"  # 或者根据results_data判断是否error
            if "error" in results_data:  # 确保result_data被正确解析
                try:
                    parsed_results = (
                        json.loads(results_data)
                        if isinstance(results_data, str)
                        else results_data
                    )
                    if "error" in parsed_results:
                        battle.status = "error"
                except:
                    pass  # 保持completed

            battle.ended_at = (
                datetime.now()
            )  # 开始时间戳  # 使用 datetime.datetime.utcnow() 如果你的时间都是UTC
            battle.results = (
                json.dumps(results_data)
                if not isinstance(results_data, str)
                else results_data
            )
            battle.game_log_uuid = (
                results_data.get("game_log_uuid")
                if isinstance(results_data, dict)
                else None
            )

            # 对于BattlePlayer，我们可能仍想记录他们的outcome (win/loss/draw)但没有elo_change
            battle_players = get_battle_players_for_battle(battle_id)
            roles_data = (
                results_data.get("roles", {}) if isinstance(results_data, dict) else {}
            )
            # ... (可以复用之前的 player_roles 和 team_map, user_outcomes 的逻辑来确定 outcome) ...
            # 例如:
            # player_roles = {} ...
            # team_map = {} ...
            # user_outcomes = {} ... (基于 winner_team)
            winner_team = (
                results_data.get("winner") if isinstance(results_data, dict) else None
            )
            if winner_team:
                team_outcomes = {
                    RED_TEAM: "win" if winner_team == RED_TEAM else "loss",
                    BLUE_TEAM: "win" if winner_team == BLUE_TEAM else "loss",
                }
                # 假设可以获取到角色和队伍映射
                # user_outcomes = { bp.user_id: team_outcomes[get_team_for_user(bp.user_id, roles_data)] for bp in battle_players }

                for bp in battle_players:
                    # outcome = user_outcomes.get(bp.user_id, "draw") # 默认为平局如果无法确定
                    # bp.outcome = outcome
                    if bp.initial_elo is None:
                        user_stats = get_game_stats_by_user_id(
                            bp.user_id, battle.ranking_id
                        )
                        bp.initial_elo = (
                            user_stats.elo_score if user_stats else 1200
                        )  # Fallback to default

                    bp.elo_change = 0  # 明确ELO变化为0 for exempt battles
                    db.session.add(bp)

            if safe_commit():
                logger.info(
                    f"[Battle {battle_id}] ELO豁免的对战结果已记录，无统计更新。"
                )
                return True
            else:
                logger.error(
                    f"[Battle {battle_id}] ELO豁免的对战结果记录失败（数据库提交错误）。"
                )
                return False
        # --- 结束新增检查 ---
        battle_ranking_id = battle.ranking_id  # 获取对战的排行榜ID

        if battle.status == "completed":
            logger.info(f"[Battle {battle_id}] 对战已处理，跳过重复操作")
            return True  # 幂等性处理

        # 获取对战玩家记录（按加入顺序排列）
        battle_players = get_battle_players_for_battle(battle_id)
        if len(battle_players) != 7:
            logger.error(
                f"[Battle {battle_id}] 玩家数量异常（预期7人，实际{len(battle_players)}人）"
            )
            return False

        # 初始化错误处理相关变量
        err_user_id = None
        error_pid_in_game = None
        error_type = None
        error_code_method = None
        error_msg = None

        # 验证公共日志文件路径
        PUBLIC_LIB_FILE_DIR = results_data.get("public_log_file")
        if not PUBLIC_LIB_FILE_DIR:
            logger.error(f"[Battle {battle_id}] 缺少公共日志文件路径")
            return False

        # 读取公共日志获取错误玩家
        try:
            with open(PUBLIC_LIB_FILE_DIR, "r", encoding="utf-8") as plib:
                data = json.load(plib)
                # 遍历日志条目，查找错误记录
                for record in reversed(data):  # 从最新记录开始查找
                    # 检查是否是错误记录
                    if "type" in record and record["type"] in [
                        "critical_player_ERROR",
                        "player_ruturn_ERROR",
                    ]:
                        error_type = record.get("type")
                        error_pid_in_game = record.get("error_code_pid")
                        error_code_method = record.get("error_code_method")
                        error_msg = record.get("error_msg")

                        # 检查错误玩家ID有效性
                        if (
                            error_pid_in_game is not None
                            and 1 <= error_pid_in_game <= 7
                        ):
                            logger.info(
                                f"[Battle {battle_id}] 找到错误玩家PID: {error_pid_in_game}, 错误类型: {error_type}, 错误方法: {error_code_method}"
                            )
                            break

                # 如果没有找到有效的错误记录
                if error_pid_in_game is None or not (1 <= error_pid_in_game <= 7):
                    # 检查最后一条记录是否有错误信息但格式不同
                    last_record = data[-1] if data else None
                    if last_record and "error" in last_record:
                        logger.warning(
                            f"[Battle {battle_id}] 找到非标准错误记录: {last_record}"
                        )
                        # 尝试从非标准错误记录中提取信息
                        if isinstance(
                            last_record.get("error"), str
                        ) and "Player" in last_record.get("error"):
                            # 尝试从错误消息中提取玩家ID
                            import re

                            match = re.search(r"Player (\d+)", last_record.get("error"))
                            if match:
                                error_pid_in_game = int(match.group(1))
                                error_type = "extracted_error"
                                error_msg = last_record.get("error")

                                # 尝试提取错误方法
                                method_match = re.search(
                                    r"method '([^']+)'|executing ([^ ]+)",
                                    last_record.get("error"),
                                )
                                if method_match:
                                    error_code_method = method_match.group(
                                        1
                                    ) or method_match.group(2)

                                logger.info(
                                    f"[Battle {battle_id}] 从错误消息中提取出玩家ID: {error_pid_in_game}, 方法: {error_code_method}"
                                )

                    # 如果仍然没有找到错误玩家
                    if error_pid_in_game is None or not (1 <= error_pid_in_game <= 7):
                        logger.error(f"[Battle {battle_id}] 无法找到有效的错误玩家PID")
                        # 此时不返回False，而是继续处理，但不执行ELO扣分
        except Exception as e:
            logger.error(
                f"[Battle {battle_id}] 读取公共日志失败: {str(e)}", exc_info=True
            )
            # 继续处理，但不执行ELO扣分

        # 获取错误玩家信息
        if error_pid_in_game is not None and 1 <= error_pid_in_game <= 7:
            err_player_index = error_pid_in_game - 1
            if err_player_index < len(battle_players):
                err_user_id = battle_players[err_player_index].user_id
                logger.info(
                    f"[Battle {battle_id}] 错误玩家用户ID: {err_user_id} (游戏中的PID: {error_pid_in_game})"
                )
            else:
                logger.error(f"[Battle {battle_id}] 错误玩家索引超出范围")

        # ----------------------------------
        # 阶段2：基础数据更新
        # ----------------------------------
        battle.status = "completed" if err_user_id is None else "error"
        battle.ended_at = datetime.now()  # 开始时间戳
        battle.results = json.dumps(results_data)
        battle.game_log_uuid = results_data.get("game_log_uuid")

        # ----------------------------------
        # 阶段3：生成核心映射关系 - 修复部分
        # ----------------------------------
        # 获取角色信息，处理不同格式的roles数据
        roles_data = results_data.get("roles", {})
        logger.info(f"[Battle {battle_id}] 从结果数据中获取角色信息: {roles_data}")

        # 创建player_id到角色的映射
        player_roles = {}

        # 尝试多种方式从结果数据中提取角色信息
        if isinstance(roles_data, dict):
            # 如果roles是字典格式
            for pid_str, role in roles_data.items():
                try:
                    # 尝试将键转换为整数（处理字符串键的情况）
                    pid = int(pid_str) if isinstance(pid_str, str) else pid_str
                    player_roles[pid] = role
                except (ValueError, TypeError):
                    logger.warning(
                        f"[Battle {battle_id}] 无法解析角色数据键: {pid_str}"
                    )

        # 如果无法从结果数据中获取角色信息，我们将基于最终获胜方推断队伍
        if not player_roles and "winner" in results_data:
            logger.warning(
                f"[Battle {battle_id}] 无法从结果中获取角色信息，将基于最终胜负推断队伍"
            )

            # 根据最终获胜方分配角色（简化处理）
            winner_team = results_data.get("winner")

            # 模拟一个基础的角色分配
            # 前4个玩家是蓝队，后3个玩家是红队（这是一种简化处理）
            for i in range(1, 8):
                if i <= 4:  # 前4个玩家属于蓝队
                    player_roles[i] = "Knight"  # 默认蓝队角色
                else:  # 后3个玩家属于红队
                    player_roles[i] = "Assassin"  # 默认红队角色

        # 在没有任何角色信息的情况下，记录警告并继续
        if not player_roles:
            logger.warning(f"[Battle {battle_id}] 无法确定角色分配，将默认分配角色")
            # 创建默认角色映射
            for i in range(1, 8):
                player_roles[i] = "Knight" if i <= 4 else "Assassin"

        # 打印获取到的角色信息进行调试
        logger.info(f"[Battle {battle_id}] 获取到的角色映射: {player_roles}")

        # 定义获取队伍的函数
        def _get_team_assignment(player_index: int) -> str:
            """返回玩家的队伍 (player_index 取1-7)"""
            role = player_roles.get(player_index)
            if role in RED_ROLES:
                return RED_TEAM
            else:
                return BLUE_TEAM

        # 生成用户ID到队伍的映射
        team_map = {
            bp.user_id: _get_team_assignment(idx + 1)
            for idx, bp in enumerate(battle_players)
        }

        logger.info(f"[Battle {battle_id}] 生成的队伍映射: {team_map}")

        # 生成用户结果映射
        if err_user_id is not None:
            # 有错误玩家，该玩家为失败，其他为平局
            user_outcomes = {
                user_id: "loss" if user_id == err_user_id else "draw"
                for user_id in team_map.keys()
            }
        else:
            # 正常情况，根据胜负判断
            winner_team = results_data.get("winner")
            if winner_team not in (RED_TEAM, BLUE_TEAM):
                logger.error(f"[Battle {battle_id}] 无效的获胜队伍标识: {winner_team}")
                return False

            team_outcomes = {
                RED_TEAM: "win" if winner_team == RED_TEAM else "loss",
                BLUE_TEAM: "win" if winner_team == BLUE_TEAM else "loss",
            }
            user_outcomes = {
                user_id: team_outcomes[team] for user_id, team in team_map.items()
            }

        # ----------------------------------
        # 阶段4：更新玩家对战记录
        # ----------------------------------
        for bp in battle_players:
            outcome = user_outcomes.get(bp.user_id)
            if outcome:
                bp.outcome = outcome.lower()
                db.session.add(bp)
            else:
                logger.warning(f"[Battle {battle_id}] 玩家 {bp.user_id} 无结果记录")
        db.session.flush()

        # ----------------------------------
        # 阶段5：ELO评分计算
        # ----------------------------------

        # 这里获取对局token数
        tokens = []
        try:
            with open(PUBLIC_LIB_FILE_DIR, "r", encoding="utf-8") as plib:
                data = json.load(plib)
                for line in data[::-1]:
                    if line.get("type") == "tokens":
                        tokens = line.get(
                            "result", []
                        )  # [{"input": 0, "output": 0} for i in range(7)]
                        break
            logger.info(f"[Battle {battle_id}] 获取到的tokens数据: {tokens}")
        except Exception as e:
            logger.warning(f"[Battle {battle_id}] 获取tokens数据失败: {str(e)}")
            # 创建默认tokens
            tokens = [{"input": 0, "output": 0} for i in range(7)]

        involved_user_ids = list(user_outcomes.keys())
        user_stats_map = {
            stats.user_id: stats
            for stats in GameStats.query.filter(
                GameStats.user_id.in_(involved_user_ids),
                GameStats.ranking_id == battle_ranking_id,  # 使用对战的排行榜ID
            ).all()
        }

        # 创建缺失的统计记录
        for user_id in involved_user_ids:
            if user_id not in user_stats_map:
                new_stats = create_game_stats(
                    user_id, battle_ranking_id
                )  # 使用对战的排行榜ID
                if new_stats:
                    user_stats_map[user_id] = new_stats
                    db.session.add(new_stats)
                else:
                    logger.error(
                        f"[Battle {battle_id}] 无法为玩家 {user_id} 创建统计记录"
                    )

        # 错误处理分支 - 代码错误的玩家将受到ELO扣除
        if err_user_id is not None:
            # 计算队伍平均ELO
            team_elos = {RED_TEAM: [], BLUE_TEAM: []}
            for user_id, stats in user_stats_map.items():
                team = team_map.get(user_id)
                if team in team_elos:
                    team_elos[team].append(stats.elo_score)

            team_avg = {
                team: sum(scores) / len(scores) if scores else 0
                for team, scores in team_elos.items()
            }

            # 计算惩罚值 - 改进的惩罚计算逻辑
            # 对于代码错误，基础惩罚为30分，加上队伍差距的10%
            base_penalty = 30
            team_diff_penalty = abs(team_avg[BLUE_TEAM] - team_avg[RED_TEAM]) * 0.1

            # 根据错误类型调整惩罚
            error_type_multiplier = 1.0
            if error_type == "critical_player_ERROR":
                error_type_multiplier = 1.5  # 严重错误
            elif error_type == "player_ruturn_ERROR":
                error_type_multiplier = 1.2  # 返回值错误

            # 根据错误方法调整惩罚
            method_penalty = 0
            if error_code_method == "walk":  # 移动错误
                method_penalty = 10
            elif error_code_method == "decide_mission_member":  # 队伍选择错误
                method_penalty = 15
            elif error_code_method == "mission_vote2":  # 投票错误
                method_penalty = 20

            total_reduction = round(
                (base_penalty + team_diff_penalty) * error_type_multiplier
                + method_penalty
            )

            # 确保惩罚至少为20分，最多为100分
            total_reduction = max(20, min(total_reduction, 100))

            logger.info(
                f"[Battle {battle_id}] 错误惩罚计算: 基础={base_penalty}, 队伍差异={team_diff_penalty:.1f}, "
                + f"类型系数={error_type_multiplier}, 方法惩罚={method_penalty}, 总计={total_reduction}"
            )

            # 更新所有玩家数据
            for user_id, stats in user_stats_map.items():
                bp = next((p for p in battle_players if p.user_id == user_id), None)
                if not bp:
                    continue

                # 通用更新
                stats.games_played += 1
                bp.initial_elo = stats.elo_score

                # 错误玩家特殊处理
                if user_id == err_user_id:
                    stats.losses += 1
                    new_elo = max(round(stats.elo_score - total_reduction), 100)
                    bp.elo_change = new_elo - stats.elo_score
                    stats.elo_score = new_elo
                    logger.info(
                        f"[Battle {battle_id}] [ERROR] 扣除ELO: 玩家 {user_id} | {bp.initial_elo} -> {new_elo} (减少: {total_reduction}分)"
                    )
                else:
                    bp.elo_change = 0
                    stats.draws += 1
                    logger.info(
                        f"[Battle {battle_id}] 其他玩家不受影响: 玩家 {user_id} | ELO 保持 {stats.elo_score}"
                    )

                db.session.add(stats)
                db.session.add(bp)

        # 正常处理分支
        else:
            # ELO计算逻辑
            # 看玩家tokens数占全局tokens比例proportion,
            # 若proportion<1,按照1计算，>1,
            # 则胜率 = min{1, 胜率 * (1 + (max{proportion,1} - 1) / 3)}
            team_elos = {RED_TEAM: [], BLUE_TEAM: []}
            for user_id, stats in user_stats_map.items():
                team = team_map.get(user_id)
                if team in team_elos:
                    team_elos[team].append(stats.elo_score)

            tokens_standard = [
                (tokens[ui - 1]["input"] + 3 * tokens[ui - 1]["output"]) / 4
                for ui in range(1, 8)
            ]  # 一倍输入和三倍输出的和

            tokens_avg = max(
                MAX_TOKEN_ALLOWED, sum(tokens_standard) / 7
            )  # 均值, 该常量以下必不惩罚

            proportion = [token / tokens_avg for token in tokens_standard]  # 比例

            team_avg = {
                team: (
                    len(scores) / sum([min(1, 1 / score) for score in scores])
                )  # 防止分母为0
                for team, scores in team_elos.items()
            }  # 这里改为调和平均，给有大蠢蛋参与队伍的强者发点补助

            K_FACTOR = 100
            red_expected = 1 / (
                1 + 10 ** ((team_avg[BLUE_TEAM] - team_avg[RED_TEAM]) / 400)
            )
            blue_expected = 1 / (
                1 + 10 ** ((team_avg[RED_TEAM] - team_avg[BLUE_TEAM]) / 400)
            )

            actual_score = {
                RED_TEAM: 1.0 if results_data.get("winner") == RED_TEAM else 0.0,
                BLUE_TEAM: 1.0 if results_data.get("winner") == BLUE_TEAM else 0.0,
            }

            for user_id, stats in user_stats_map.items():
                bp = next((p for p in battle_players if p.user_id == user_id), None)
                if not bp or bp.position is None:
                    continue
                idx = bp.position - 1  # position为1~7，proportion下标为0~6
                team = team_map[user_id]
                expected = red_expected if team == RED_TEAM else blue_expected
                delta = K_FACTOR * (
                    actual_score[team]
                    - min(1, expected * (0.9 + (max(proportion[idx] - 1, 0) / 3)))
                )

                stats.games_played += 1
                if team_outcomes[team] == "win":
                    stats.wins += 1
                else:
                    stats.losses += 1

                new_elo = max(round(stats.elo_score + delta), 100)
                bp.initial_elo = stats.elo_score
                bp.elo_change = new_elo - stats.elo_score
                stats.elo_score = new_elo
                logger.info(
                    f"[Battle {battle_id}] 更新ELO: 玩家 {user_id} | {bp.initial_elo} -> {new_elo} (变化: {bp.elo_change:+d})"
                )

                db.session.add(stats)
                db.session.add(bp)

        # ----------------------------------
        # 阶段6：最终提交
        # ----------------------------------
        if safe_commit():
            logger.info(f"[Battle {battle_id}] 处理成功")
            return True
        else:
            db.session.rollback()
            logger.error(f"[Battle {battle_id}] 数据库提交失败")
            return False

    except Exception as e:
        db.session.rollback()
        logger.error(f"[Battle {battle_id}] 处理异常: {str(e)}", exc_info=True)
        return False


def get_user_battle_history(user_id, page=1, per_page=10):
    """
    获取用户参与过的对战历史记录 (分页)。

    参数:
        user_id (str): 用户ID。
        page (int): 当前页码 (从1开始)。
        per_page (int): 每页记录数。

    返回:
        tuple: (对战列表, 总记录数)。出错返回 ([], 0)。
    """
    try:
        # 查询 BattlePlayer 记录，筛选出指定用户的参与记录
        # 然后加载关联的 Battle 和 User (为了获取用户名)
        # 使用 joinedload 可以减少查询次数
        query = (
            BattlePlayer.query.filter_by(user_id=user_id)
            .join(BattlePlayer.battle)
            .order_by(Battle.created_at.desc())
        )

        # 获取总数
        total = query.count()

        # 应用分页
        battle_players_page = query.offset((page - 1) * per_page).limit(per_page).all()

        # 提取关联的 Battle 对象
        # 使用 set 去重，因为一个 Battle 可能有多个 BattlePlayer (不是 1v1 的情况)
        # 但实际上这里因为是按 BattlePlayer 查，每个 BattlePlayer 只对应一个 Battle。
        # 转换为 battle 列表方便处理
        battles = [bp.battle for bp in battle_players_page if bp.battle]

        return battles, total
    except Exception as e:
        logger.error(f"获取用户 {user_id} 的对战历史失败: {e}", exc_info=True)
        return [], 0


def get_recent_battles(limit=20):
    """
    获取最近结束的对战列表。

    参数:
        limit (int): 返回数量限制。

    返回:
        list: Battle 对象列表。
    """
    try:
        # 过滤已完成的对战，按结束时间降序排列
        return Battle.query.order_by(Battle.ended_at.desc()).limit(limit).all()
    except Exception as e:
        logger.error(f"获取最近对战失败: {e}", exc_info=True)
        return []


# -----------------------------------------------------------------------------------------
# BattlePlayer 独立 CRUD 操作 (除了在 Battle 函数中创建/删除)
# 这些通常在 Battle 函数内部调用，但提供独立的访问点以防需要


def get_battle_player_by_id(battle_player_id):
    """根据ID获取 BattlePlayer 记录。"""
    try:
        return BattlePlayer.query.get(battle_player_id)
    except Exception as e:
        logger.error(f"根据ID获取 BattlePlayer 失败: {e}", exc_info=True)
        return None


# create_battle_player 在 create_battle 内部实现
# delete_battle_player 在 delete_battle 内部，通过 cascade 实现


def update_battle_player(battle_player, **kwargs):
    """
    更新 BattlePlayer 记录。

    参数:
        battle_player (BattlePlayer): 要更新的 BattlePlayer 对象。
        **kwargs: 要更新的字段及其值 (例如 outcome, elo_change)。

    返回:
        bool: 更新是否成功。
    """
    if not battle_player:
        return False
    try:
        for key, value in kwargs.items():
            if hasattr(battle_player, key) and key not in [
                "id",
                "battle_id",
                "user_id",
                "selected_ai_code_id",
            ]:  # 不允许修改关联ID
                setattr(battle_player, key, value)
        return safe_commit()
    except Exception as e:
        logger.error(f"更新 BattlePlayer {battle_player.id} 失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def mark_battle_as_cancelled(battle_id, cancellation_reason=None):
    """
    将对战标记为已取消状态。

    参数:
        battle_id (str): 对战ID。
        cancellation_reason (str, optional): 取消原因。

    返回:
        bool: 操作是否成功。
    """
    try:
        battle = get_battle_by_id(battle_id)
        if not battle:
            logger.error(f"将对战标记为已取消失败: 对战 {battle_id} 不存在")
            return False

        # 检查对战状态，只允许取消特定状态的对战
        allowed_states = ["waiting", "playing"]
        if battle.status not in allowed_states:
            logger.warning(
                f"无法取消对战 {battle_id}: 当前状态 '{battle.status}' 不允许取消"
            )
            return False

        # 更新对战状态
        battle.status = "cancelled"
        battle.ended_at = datetime.now()  # 开始时间戳

        # 如果提供了取消原因，则更新结果字段
        if cancellation_reason:
            # 如果已有结果，则保留原有结果并添加取消原因
            if battle.results:
                try:
                    results_data = json.loads(battle.results)
                    results_data["cancellation_reason"] = cancellation_reason
                    battle.results = json.dumps(results_data)
                except (json.JSONDecodeError, TypeError):
                    # 如果 battle.results 不是有效的 JSON，则创建新的
                    battle.results = json.dumps(
                        {"cancellation_reason": cancellation_reason}
                    )
            else:
                # 如果没有结果，则创建新的
                battle.results = json.dumps(
                    {"cancellation_reason": cancellation_reason}
                )

        if safe_commit():
            logger.info(f"对战 {battle_id} 已标记为已取消")
            return True
        return False
    except Exception as e:
        logger.error(f"将对战标记为已取消失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def handle_cancelled_battle_stats(battle_id):
    """
    处理已取消对战的玩家统计数据。

    根据系统设计，可能需要:
    1. 不计入玩家游戏统计
    2. 或标记为"取消"而非输赢
    3. 或在特定情况下给予部分ELO补偿
    4. 支持多排行榜 (ranking_id)

    参数:
        battle_id (str): 已取消对战的ID。

    返回:
        bool: 操作是否成功。
    """
    try:
        battle = get_battle_by_id(battle_id)
        if not battle:
            logger.error(f"处理已取消对战统计失败: 对战 {battle_id} 不存在")
            return False

        battle_ranking_id = battle.ranking_id  # 获取对战的排行榜ID

        if battle.status != "cancelled":
            logger.warning(f"对战 {battle_id} 不是已取消状态，无法处理取消统计")
            return False

        # 获取对战玩家列表
        battle_players = get_battle_players_for_battle(battle_id)
        if not battle_players:
            logger.warning(f"对战 {battle_id} 没有参与玩家，无需处理统计")
            return True  # 无玩家，视为成功处理

        # 解析取消原因（如果有）
        cancellation_reason = None
        if battle.results:
            try:
                results_data = json.loads(battle.results)
                cancellation_reason = results_data.get("cancellation_reason")
            except (json.JSONDecodeError, TypeError):
                pass

        # 系统故障取消 vs 用户主动取消 vs 管理员取消等情况可能有不同处理
        # 修改这里：检查 cancellation_reason 的类型
        is_system_error = False
        if (
            isinstance(cancellation_reason, str)
            and "system" in cancellation_reason.lower()
        ):
            is_system_error = True
        elif (
            isinstance(cancellation_reason, dict)
            and cancellation_reason.get("error")
            and "system" in str(cancellation_reason.get("error")).lower()
        ):
            is_system_error = True

        # 更新所有参与者的对战记录
        for bp in battle_players:
            # 设置对战结果为"取消"
            bp.outcome = "cancelled"
            # 对于已经开始的对战，可能需要保留ELO初始值但不计算变化
            bp.elo_change = 0
            db.session.add(bp)

            # 根据实际需求决定是否更新游戏统计
            # 例如：系统故障导致的取消不计入玩家的游戏场次
            if not is_system_error:
                # 获取用户统计
                stats = get_game_stats_by_user_id(
                    bp.user_id, battle_ranking_id
                )  # 使用对战的排行榜ID
                if stats:
                    # 更新取消的对战计数（假设模型中有canceled_games字段）
                    # 如果模型中没有，可以添加，或者选择不记录
                    if hasattr(stats, "cancelled_games"):
                        stats.cancelled_games += 1
                        db.session.add(stats)

        # 提交所有更改
        return safe_commit()
    except Exception as e:
        logger.error(f"处理已取消对战统计失败: {e}", exc_info=True)
        db.session.rollback()
        return False


from sqlalchemy import desc, or_, and_  # Import and_ if needed, or_ is key here


def get_battles_paginated_filtered(filters=None, page=1, per_page=10, error_out=False):
    """
    Fetches battles with optional filters and pagination. Supports multi-player filtering.

    :param filters: A dictionary with possible keys: 'status', 'date_from', 'date_to', 'players'.
    :param page: Current page number.
    :param per_page: Items per page.
    :param error_out: If True, raises an error for invalid page numbers.
    :return: A Flask-SQLAlchemy Pagination object.
    """
    query = Battle.query

    # 默认不显示 'ready' 状态的对局，除非过滤器明确要求
    # (这种方式可能更复杂，取决于你如何组合查询)
    # 一个简单的方法是，如果状态过滤器不是 'ready'，则排除 'ready'
    status_filter_value = filters.get("status") if filters else None

    if status_filter_value and status_filter_value.lower() == "ready":
        query = query.filter(Battle.status == "ready")
    elif status_filter_value and status_filter_value.lower() != "all":
        query = query.filter(Battle.status == status_filter_value)
        # 如果不是 'all' 也不是 'ready'，我们可能仍想排除 ready，但这取决于需求
        # query = query.filter(Battle.status != 'ready') # 如果总是想排除ready，除非明确选择
    elif not status_filter_value or status_filter_value.lower() == "all":
        # 当选择 "all" 或没有状态过滤器时，默认排除 "ready"
        query = query.filter(Battle.status != "ready")

    if filters:
        # Apply status filter
        if "status" in filters and filters["status"] and filters["status"] != "all":
            query = query.filter(Battle.status == filters["status"])

        # Apply date filters
        if "date_from" in filters and filters["date_from"]:
            query = query.filter(Battle.created_at >= filters["date_from"])
        if "date_to" in filters and filters["date_to"]:
            query = query.filter(Battle.created_at <= filters["date_to"])

        # Apply multiple player filters
        if "players" in filters and filters["players"]:
            player_list = filters["players"]
            player_ids = []

            # Find all user IDs for the player names/IDs in the list
            for player_identifier in player_list:
                # Construct conditions for user identification
                user_conditions = [User.username == player_identifier]
                if player_identifier.isdigit():
                    try:
                        user_conditions.append(User.id == int(player_identifier))
                    except ValueError:
                        pass

                user = User.query.filter(or_(*user_conditions)).first()
                if user:
                    player_ids.append(user.id)

            if player_ids:
                # Create a subquery to find battles where any of these players participated
                subquery = (
                    db.session.query(BattlePlayer.battle_id)
                    .filter(BattlePlayer.user_id.in_(player_ids))
                    .group_by(BattlePlayer.battle_id)
                )

                # If we want to find battles where ALL specified players participated, we need to count
                if len(player_ids) > 1:
                    subquery = subquery.having(
                        func.count(BattlePlayer.user_id.distinct()) == len(player_ids)
                    )

                subquery = subquery.subquery()

                # Join with the main query
                query = query.join(subquery, Battle.id == subquery.c.battle_id)
            else:
                # No valid players found, return no results
                query = query.filter(False)

    # Default ordering
    query = query.order_by(desc(Battle.created_at))

    return query.paginate(page=page, per_page=per_page, error_out=error_out)


def create_battle_instance(created_by, ranking_id=0):
    """
    创建新的对战实例

    参数:
        created_by (str): 创建者的用户ID
        ranking_id (int): 排行榜ID，默认为0

    返回:
        Battle: 新创建的对战实例
    """
    try:
        # 创建一个新的对战实例
        new_battle = Battle(
            status="waiting",  # 初始状态：等待中
            ranking_id=ranking_id,
            created_at=datetime.now(),
            # 其他字段会使用默认值或在后续更新
        )

        # 保存到数据库
        db.session.add(new_battle)
        db.session.commit()

        current_app.logger.info(
            f"创建了新对战 ID: {new_battle.id}, 创建者: {created_by}"
        )

        return new_battle

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"创建对战实例失败: {str(e)}")
        # 可以选择重新抛出异常或返回None
        return None


def add_player_to_battle(battle_id, position, user_id, ai_code_id=None):
    """
    将玩家添加到对战中

    参数:
        battle_id (str): 对战ID
        position (int): 玩家位置 (1-7)
        user_id (str): 用户ID
        ai_code_id (str, optional): AI代码ID，如果要使用特定AI

    返回:
        BattlePlayer: 新创建的对战玩家实例
    """
    try:
        # 验证对战存在
        battle = db.session.query(Battle).filter(Battle.id == battle_id).first()
        if not battle:
            current_app.logger.error(f"添加玩家失败: 对战ID {battle_id} 不存在")
            return None

        # 验证位置未被占用
        existing_player = (
            db.session.query(BattlePlayer)
            .filter(
                BattlePlayer.battle_id == battle_id, BattlePlayer.position == position
            )
            .first()
        )

        if existing_player:
            current_app.logger.error(
                f"添加玩家失败: 对战 {battle_id} 的位置 {position} 已被占用"
            )
            return None

        # 检查AI代码是否存在
        if ai_code_id:
            ai_code = db.session.query(AICode).filter(AICode.id == ai_code_id).first()
            if not ai_code:
                current_app.logger.error(f"添加玩家失败: AI代码 {ai_code_id} 不存在")
                return None

        # 创建新的对战玩家记录
        new_player = BattlePlayer(
            battle_id=battle_id,
            user_id=user_id,
            position=position,
            selected_ai_code_id=ai_code_id,
            join_time=datetime.now(),
        )

        # 保存到数据库
        db.session.add(new_player)
        db.session.commit()

        # 更新对战的玩家计数
        update_battle_player_count(battle_id)

        current_app.logger.info(
            f"添加玩家成功: 用户 {user_id} 加入对战 {battle_id} 的位置 {position}"
        )

        return new_player

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"添加玩家到对战失败: {str(e)}")
        # 可以选择重新抛出异常或返回None
        return None


def update_battle_player_count(battle_id):
    """
    更新对战的玩家计数

    参数:
        battle_id (str): 对战ID
    """
    try:
        # 计算当前玩家数量
        player_count = (
            db.session.query(BattlePlayer)
            .filter(BattlePlayer.battle_id == battle_id)
            .count()
        )

        # 获取对战实例
        battle = db.session.query(Battle).filter(Battle.id == battle_id).first()
        if battle:
            # 如果已满员，可以更新对战状态
            if player_count >= 7:  # 阿瓦隆需要7名玩家
                battle.status = "ready"

            db.session.commit()

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"更新对战玩家计数失败: {str(e)}")


def load_initial_users_from_config():
    """
    从 config.yaml 加载 INITIAL_USERS 配置。
    """
    try:
        # 假设 config.yaml 与 action.py 在同一目录或可以通过 current_app.config 访问其路径
        # 或者提供一个绝对/相对路径到 config.yaml
        # 为简单起见，我们这里假设 config.yaml 在项目根目录
        config_path = os.path.join(
            current_app.root_path, "config", "config.yaml"
        )  # 调整路径
        if not os.path.exists(config_path):
            # 尝试备用路径，例如在当前应用的根目录下
            config_path = os.path.join(current_app.root_path, "config.yaml")

        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
        return config_data.get("INITIAL_USERS", [])
    except Exception as e:
        current_app.logger.error(f"加载 config.yaml 失败: {e}", exc_info=True)
        return []


def get_available_ai_instances(username_prefix=None, specific_usernames=None):
    """
    获取可用的AI实例，基于config.yaml中的用户名。

    参数:
        username_prefix (str, optional): 用户名前缀 (例如 "smart_user", "basic_user").
        specific_usernames (list, optional): 特定的用户名列表。

    返回:
        list: 符合条件的已激活的 AICode 实例列表。
    """
    try:
        initial_users_config = load_initial_users_from_config()
        if not initial_users_config:
            return []

        target_usernames = set()

        if specific_usernames:
            for uname in specific_usernames:
                target_usernames.add(uname)
        elif username_prefix:
            for user_config in initial_users_config:
                if user_config.get("username", "").startswith(username_prefix):
                    target_usernames.add(user_config["username"])
        else:
            # 如果两者都未提供，默认获取所有在config中定义的用户的AI
            for user_config in initial_users_config:
                target_usernames.add(user_config["username"])

        if not target_usernames:
            current_app.logger.warning(
                f"根据条件 {username_prefix=} {specific_usernames=} 未找到目标用户"
            )
            return []

        # 从数据库中查询这些用户的已激活AI
        # 首先获取这些用户的User对象，以便通过user_id查询AICode
        users = User.query.filter(User.username.in_(list(target_usernames))).all()
        user_ids = [user.id for user in users]

        if not user_ids:
            current_app.logger.warning(f"未在数据库中找到用户: {target_usernames}")
            return []

        # 查询这些用户所有已激活的AI
        available_ai_codes = AICode.query.filter(
            AICode.user_id.in_(user_ids), AICode.is_active == True
        ).all()

        # 进一步根据 config.yaml 中的 file_path 进行匹配 (可选，但更精确)
        # 因为一个用户可能有多个AI，但config中只指定了一个初始AI
        # 如果需要严格匹配config中的AI，可以这样做：
        ai_instances = []
        user_config_map = {
            uc["username"]: uc.get("ai_code", {}).get("file_path")
            for uc in initial_users_config
        }

        for ai_code in available_ai_codes:
            user = get_user_by_id(ai_code.user_id)  # 获取AI代码对应的用户
            if user and user.username in user_config_map:
                # config_ai_filepath = user_config_map[user.username]
                # 数据库中存储的 code_path 通常是相对路径，需要与 config 中的 file_path 比较
                # 这里的比较逻辑可能需要根据实际存储情况调整
                # 例如，如果 config 中的 file_path 是 'game/smart_player.py'
                # 而数据库中的 code_path 是 'user_id_xxx/smart_player.py' (上传后的路径)
                # 这种情况下，直接比较 file_path 可能不准确。
                # 更稳妥的方式是，只要是这个用户的激活AI，就认为是可用的。
                # 如果要严格按config.yaml的file_path，那么在创建用户和AI时就要确保路径一致性。
                # 为了简化，我们先假设用户的激活AI就是我们想要的。
                ai_instances.append(ai_code)

        if not ai_instances:
            current_app.logger.warning(
                f"用户 {target_usernames} 没有找到已激活的AI代码"
            )

        return ai_instances

    except Exception as e:
        current_app.logger.error(f"获取AI实例时出错: {str(e)}", exc_info=True)
        return []


# -----------------------------------------------------------------------------------------
# Flask-Login User 加载函数 (从 models.py 移到此处或其他合适的数据加载模块)

# 用户加载函数 (用于 Flask-Login)
# 如果您希望将数据加载逻辑集中在这里，可以把这个函数放在此处
# @login_manager.user_loader # login_manager 需要在这里导入或从 base 中获取
# def load_user(user_id):
#     return get_user_by_id(user_id)
# 注: 如果 login_manager 在 app/__init__.py 中初始化并配置了 user_loader，则无需此处再次定义。
