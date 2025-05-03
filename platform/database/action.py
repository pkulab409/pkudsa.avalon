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
# 准备好后面一千多行的冲击吧！


from .base import db
import logging
from sqlalchemy import select, update, or_, func
import datetime
import json
import uuid
from .models import (
    User,
    Battle,
    GameStats,
    AICode,
    BattlePlayer,
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
        game_stats = GameStats(user=user)  # 建立关系

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
        user.updated_at = datetime.datetime.now()  # 更新时间戳
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


def get_game_stats_by_user_id(user_id):
    """
    根据用户ID获取游戏统计记录。

    参数:
        user_id (str): 用户ID。

    返回:
        GameStats: 游戏统计对象，不存在则返回None。
    """
    try:
        return GameStats.query.filter_by(user_id=user_id).first()
    except Exception as e:
        logger.error(f"获取用户 {user_id} 的游戏统计失败: {e}", exc_info=True)
        return None


def create_game_stats(user_id):
    """
    为指定用户创建游戏统计记录 (如果在用户创建时没有自动创建)。

    参数:
        user_id (str): 用户ID。

    返回:
        GameStats: 创建成功的统计对象，失败或已存在则返回None。
    """
    try:
        existing_stats = get_game_stats_by_user_id(user_id)
        if existing_stats:
            logger.warning(f"用户 {user_id} 的游戏统计已存在，无需重复创建。")
            return None

        stats = GameStats(user_id=user_id)
        if safe_add(stats):
            logger.info(f"为用户 {user_id} 创建游戏统计成功。")
            return stats
        return None
    except Exception as e:
        logger.error(f"创建用户 {user_id} 的游戏统计失败: {e}", exc_info=True)
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


def get_leaderboard(limit=100, min_games_played=1):
    """
    获取游戏排行榜。

    参数:
        limit (int): 返回数量限制。
        min_games_played (int): 玩家至少参与的游戏场次。

    返回:
        list: 包含排行榜数据的字典列表。
    """
    try:
        leaderboard_data = (
            db.session.query(GameStats, User.username)
            .join(User, GameStats.user_id == User.id)
            .filter(GameStats.games_played >= min_games_played)
            .order_by(GameStats.elo_score.desc())
            .limit(limit)
            .all()
        )

        result = []
        for stats, username in leaderboard_data:
            result.append(stats.to_dict())  # 使用 GameStats 的 to_dict 方法
            result[-1]["username"] = username  # 添加用户名
            result[-1]["win_rate"] = (
                round(stats.wins / stats.games_played * 100, 2)
                if stats.games_played > 0
                else 0
            )

        return result
    except Exception as e:
        logger.error(f"获取排行榜失败: {e}", exc_info=True)
        return []


# -----------------------------------------------------------------------------------------
# 对战 (Battle) 及 对战参与者 (BattlePlayer) CRUD 操作


def create_battle(participant_data_list, status="waiting", section=0, game_data=None):
    """
    创建对战记录及关联的参与者记录。

    参数:
        participant_data_list (list): 参与者数据列表，每个元素应为字典，
                                      至少包含 'user_id' 和 'ai_code_id'。 # <--- 修改文档注释
                                      示例: [{'user_id': '...', 'ai_code_id': '...'}, ...] # <--- 修改文档注释
        status (str): 初始状态 (e.g., 'waiting', 'playing'). 默认为 'waiting'.
        section (int): 分区类型：0=普通对局，1=预选赛，2=决赛，等. 默认为 0.
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
            section=section,  # 使用传入的分区类型
            created_at=datetime.datetime.now(),
            # started_at 在对战真正开始时设置
            # results 在对战结束时设置
            # game_log_uuid 在对战结束时设置
        )
        db.session.add(battle)
        db.session.flush()  # 确保 battle 有了 ID

        battle_players = []
        for i, data in enumerate(participant_data_list):
            # 获取玩家当前的ELO作为 initial_elo 快照
            user_stats = get_game_stats_by_user_id(data["user_id"])
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
                join_time=datetime.datetime.now(),
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
                battle.started_at = datetime.datetime.now()
            elif (
                new_status in ["completed", "error", "cancelled"]
                and battle.ended_at is None
            ):
                battle.ended_at = datetime.datetime.now()

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

    参数:
        battle_id (str): 对战的唯一标识符
        results_data (dict): 包含对战结果的数据，格式为:
            {
                "winner": "red"|"blue",  # 获胜队伍
                "error": bool,           # 新增错误标识（可选）
                "public_log_file": str,  # 新增公共日志路径（可选）
                # 其他可选字段（如game_log_uuid等）
            }

    返回:
        bool: 处理成功返回True，否则False
    """

    RED_TEAM = "red"
    BLUE_TEAM = "blue"
    BLUE_ROLES = ["Merlin", "Percival", "Knight"]  # 蓝方角色
    RED_ROLES = ["Morgana", "Assassin", "Oberon"]  # 红方角色

    def _get_team_assignment(player_index: int) -> str:
        """返回玩家的队伍 (player_index 取1-7)"""
        if results_data["roles"][player_index] in RED_ROLES:
            return RED_TEAM
        else:
            return BLUE_TEAM

    try:
        # ----------------------------------
        # 阶段1：获取基础数据并验证
        # ----------------------------------
        battle = get_battle_by_id(battle_id)
        if not battle:
            logger.error(f"[Battle {battle_id}] 对战记录不存在")
            return False

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
        if "error" in results_data:
            # 验证公共日志文件路径
            PUBLIC_LIB_FILE_DIR = results_data.get("public_log_file")
            if not PUBLIC_LIB_FILE_DIR:
                logger.error(f"[Battle {battle_id}] 缺少公共日志文件路径")
                return False

            # 读取公共日志获取错误玩家
            try:
                with open(PUBLIC_LIB_FILE_DIR, "r", encoding="utf-8") as plib:
                    data = json.load(plib)
                    last_record = data[-1] if data else None
                    if not last_record:
                        logger.error(f"[Battle {battle_id}] 公有库无记录")
                        return False
                    error_pid_in_game = last_record.get("error_code_pid")
                    if error_pid_in_game is None or not (1 <= error_pid_in_game <=7):
                        logger.error(f"[Battle {battle_id}] 无效的错误玩家PID: {error_pid_in_game}")
                        return False
            except Exception as e:
                logger.error(f"[Battle {battle_id}] 读取公共日志失败: {str(e)}", exc_info=True)
                return False

            # 获取错误玩家信息
            err_player_index = error_pid_in_game - 1
            if err_player_index >= len(battle_players):
                logger.error(f"[Battle {battle_id}] 错误玩家索引超出范围")
                return False
            err_user_id = battle_players[err_player_index].user_id

        # ----------------------------------
        # 阶段2：基础数据更新
        # ----------------------------------
        battle.status = "completed" if err_user_id is None else "error"
        battle.ended_at = datetime.datetime.now()
        battle.results = json.dumps(results_data)
        battle.game_log_uuid = results_data.get("game_log_uuid")

        # ----------------------------------
        # 阶段3：生成核心映射关系
        # ----------------------------------
        team_map = {
            bp.user_id: _get_team_assignment(idx + 1)
            for idx, bp in enumerate(battle_players)
        }


        # 生成用户结果映射
        if "error" in results_data:
            user_outcomes = {
                user_id: "loss" if user_id == err_user_id else "draw"
                for user_id in team_map.keys()
            }
        else:
            winner_team = results_data.get("winner")
            if winner_team not in (RED_TEAM, BLUE_TEAM):
                logger.error(f"[Battle {battle_id}] 无效的获胜队伍标识: {winner_team}")
                return False

            team_outcomes = {
                RED_TEAM: "win" if winner_team == RED_TEAM else "loss",
                BLUE_TEAM: "win" if winner_team == BLUE_TEAM else "loss"
            }
            user_outcomes = {
                user_id: team_outcomes[team]
                for user_id, team in team_map.items()
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
        with open(PUBLIC_LIB_FILE_DIR, "r", encoding="utf-8") as plib:
            data = json.load(plib)
            for line in data[::-1]:
                if line.get("type") == "tokens":
                    tokens = line.get("result") # [{"input": 0, "output": 0} for i in range(7)]
                    break
        
        involved_user_ids = list(user_outcomes.keys())
        user_stats_map = {
            stats.user_id: stats
            for stats in GameStats.query.filter(
                GameStats.user_id.in_(involved_user_ids)
            ).all()
        }

        # 创建缺失的统计记录
        for user_id in involved_user_ids:
            if user_id not in user_stats_map:
                new_stats = create_game_stats(user_id)
                if new_stats:
                    user_stats_map[user_id] = new_stats
                    db.session.add(new_stats)
                else:
                    logger.error(
                        f"[Battle {battle_id}] 无法为玩家 {user_id} 创建统计记录"
                    )

        # 错误处理分支
        if "error" in results_data:
            # 计算队伍平均ELO
            team_elos = {RED_TEAM: [], BLUE_TEAM: []}
            for user_id, stats in user_stats_map.items():
                team = team_map.get(user_id)
                if team in team_elos:
                    team_elos[team].append(stats.elo_score)

            team_avg = {
                team: sum(scores)/len(scores) if scores else 0
                for team, scores in team_elos.items()
            }


            # 计算惩罚值
            reduction = 2 * abs(team_avg[BLUE_TEAM] - team_avg[RED_TEAM])

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
                    new_elo = max(round(stats.elo_score - reduction), 100)
                    bp.elo_change = new_elo - stats.elo_score
                    stats.elo_score = new_elo
                    logger.info(f"[ERROR] 扣除ELO: {user_id} | {bp.initial_elo} -> {new_elo}")
                else:
                    bp.elo_change = 0
                    stats.draws += 1


                db.session.add(stats)
                db.session.add(bp)

        # 正常处理分支
        else:
            # 原ELO计算逻辑
            team_elos = {RED_TEAM: [], BLUE_TEAM: []}
            for user_id, stats in user_stats_map.items():
                team = team_map.get(user_id)
                if team in team_elos:
                    team_elos[team].append(stats.elo_score)

            team_avg = {
                team: sum(scores)/len(scores)
                for team, scores in team_elos.items()
            }

            K_FACTOR = 32
            red_expected = 1 / (1 + 10**((team_avg[BLUE_TEAM] - team_avg[RED_TEAM])/400))
            blue_expected = 1 / (1 + 10**((team_avg[RED_TEAM] - team_avg[BLUE_TEAM])/400))


            actual_score = {
                RED_TEAM: 1.0 if winner_team == RED_TEAM else 0.0,
                BLUE_TEAM: 1.0 if winner_team == BLUE_TEAM else 0.0
            }

            for user_id, stats in user_stats_map.items():
                bp = next((p for p in battle_players if p.user_id == user_id), None)
                if not bp:
                    continue

                team = team_map[user_id]
                expected = red_expected if team == RED_TEAM else blue_expected
                delta = K_FACTOR * (actual_score[team] - expected)

                stats.games_played += 1
                if team_outcomes[team] == "win":
                    stats.wins += 1
                else:
                    stats.losses += 1
                
                new_elo = max(round(stats.elo_score + delta), 100)
                bp.initial_elo = stats.elo_score
                bp.elo_change = new_elo - stats.elo_score
                stats.elo_score = new_elo
                logger.info(f"更新ELO: {user_id} | {bp.initial_elo} -> {new_elo}")

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
        return (
            Battle.query.filter_by(status="completed")
            .order_by(Battle.ended_at.desc())
            .limit(limit)
            .all()
        )
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


# -----------------------------------------------------------------------------------------
# Flask-Login User 加载函数 (从 models.py 移到此处或其他合适的数据加载模块)

# 用户加载函数 (用于 Flask-Login)
# 如果您希望将数据加载逻辑集中在这里，可以把这个函数放在此处
# @login_manager.user_loader # login_manager 需要在这里导入或从 base 中获取
# def load_user(user_id):
#     return get_user_by_id(user_id)
# 注: 如果 login_manager 在 app/__init__.py 中初始化并配置了 user_loader，则无需此处再次定义。
