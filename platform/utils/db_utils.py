"""
数据库相关工具函数
"""

import os
from flask import current_app

# 导入 database.action 中的函数
from database.action import get_battle_by_id, get_ai_code_by_id


def build_log_file_path(game_log_uuid, user_id=None, is_public=True):
    """
    根据game_log_uuid构建游戏日志文件路径

    参数:
        game_log_uuid: 游戏日志UUID
        user_id: 用户ID(可选)，用于构建私有日志路径
        is_public: 是否为公共日志

    返回:
        log_file_path: 日志文件完整路径
    """
    # 检查game_log_uuid是否存在
    if not game_log_uuid:
        return None

    # 设置基础数据目录
    data_dir = current_app.config.get("DATA_DIR", "./data")

    # 构建日志目录
    if is_public:
        log_dir = os.path.join(data_dir, "logs", "public")
    elif user_id:
        # 私有日志路径现在基于用户ID
        log_dir = os.path.join(data_dir, "logs", "private", str(user_id))
    else:
        # 系统日志，例如裁判未完成的日志
        log_dir = os.path.join(data_dir, "logs", "system")

    # 确保目录存在
    os.makedirs(log_dir, exist_ok=True)

    # 构建文件名
    log_file_name = f"game_{game_log_uuid}.json"
    log_file_path = os.path.join(log_dir, log_file_name)

    return log_file_path


def get_game_log_path(battle_id, user_id=None):
    """
    根据battle_id获取游戏日志路径

    参数:
        battle_id: 对战ID
        user_id: 用户ID(可选)，用于判断是否返回私有日志

    返回:
        log_file_path: 日志文件完整路径
    """
    # 使用 action 中的函数获取 battle
    battle = get_battle_by_id(battle_id)
    if not battle or not battle.game_log_uuid:
        return None

    # 检查用户是否为参与者
    is_participant = False
    if user_id:
        # battle.players 是一个查询对象 (lazy='dynamic')，需要执行查询
        participant_record = battle.players.filter_by(user_id=str(user_id)).first()
        if participant_record:
            is_participant = True

    # 如果用户是参与者，返回私有日志路径；否则返回公共日志路径
    is_public = not is_participant

    # 如果请求者不是参与者，则 user_id 参数应为 None 以获取公共路径
    log_user_id = user_id if is_participant else None

    return build_log_file_path(battle.game_log_uuid, log_user_id, is_public)


def get_ai_code_path(ai_code_id):
    """
    根据ai_code_id获取AI代码文件路径 (相对于 DATA_DIR)

    参数:
        ai_code_id: AI代码ID

    返回:
        code_path: AI代码文件路径，如果找不到则返回None
    """
    # 使用 action 中的函数获取 ai_code
    ai_code = get_ai_code_by_id(ai_code_id)
    if not ai_code or not ai_code.code_path:
        return None

    # 获取基础数据目录
    data_dir = current_app.config.get("DATA_DIR", "./data")
    # 构建AI代码上传目录的相对路径 (相对于 data_dir)
    upload_subdir = os.path.join("uploads", "ai_codes")
    # 构建完整文件路径
    file_path = os.path.join(data_dir, upload_subdir, ai_code.code_path)

    # 可选：检查文件是否存在
    # if not os.path.exists(file_path):
    #     from flask import logger
    #     logger.warning(f"AI code file not found at expected path: {file_path}")
    #     return None

    return file_path


def get_ai_code_metadata(ai_code_id):
    """
    根据ai_code_id获取AI代码元数据

    参数:
        ai_code_id: AI代码ID

    返回:
        metadata: 元数据字典，如果找不到则返回None
    """
    # 使用 action 中的函数获取 ai_code
    ai_code = get_ai_code_by_id(ai_code_id)
    if not ai_code:
        return None

    # 可以直接使用模型的 to_dict 方法（如果已定义）或手动创建字典
    metadata = {
        "id": ai_code.id,
        "user_id": ai_code.user_id,
        "name": ai_code.name,
        "code_path": ai_code.code_path,  # 相对路径
        "description": ai_code.description,
        "is_active": ai_code.is_active,
        "created_at": (
            ai_code.created_at.isoformat() if ai_code.created_at else None
        ),  # 转换为 ISO 格式字符串
        "version": ai_code.version,
        "status": ai_code.status,
    }
    # 注意：如果模型有 to_dict() 方法，可以直接调用 ai_code.to_dict()

    return metadata


def ensure_data_directories():
    """
    确保所有数据目录存在
    """
    data_dir = current_app.config.get("DATA_DIR", "./data")

    # 创建公共日志目录
    os.makedirs(os.path.join(data_dir, "logs", "public"), exist_ok=True)
    # 创建私有日志根目录 (用户特定子目录将在需要时创建)
    os.makedirs(os.path.join(data_dir, "logs", "private"), exist_ok=True)
    # 创建系统日志目录
    os.makedirs(os.path.join(data_dir, "logs", "system"), exist_ok=True)

    # 创建AI代码上传目录 (在 data_dir 下)
    os.makedirs(os.path.join(data_dir, "uploads", "ai_codes"), exist_ok=True)

    # 创建临时文件目录
    os.makedirs(os.path.join(data_dir, "temp"), exist_ok=True)

    # 可以添加对私有用户日志目录的预创建逻辑，但这通常在首次写入时处理更好
    # from database.models import User
    # users = User.query.all()
    # for user in users:
    #     os.makedirs(os.path.join(data_dir, "logs", "private", str(user.id)), exist_ok=True)

    return True
