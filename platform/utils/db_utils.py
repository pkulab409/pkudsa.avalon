"""
数据库相关工具函数
"""

import os
from flask import current_app
from database.models import Battle


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
        log_dir = os.path.join(data_dir, "logs", "private", str(user_id))
    else:
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
    battle = Battle.query.get(battle_id)
    if not battle or not battle.game_log_uuid:
        return None

    # 用户为None或用户为对战参与者，返回公共日志
    is_public = True
    if user_id and str(user_id) in battle.player_ids:
        is_public = False

    return build_log_file_path(battle.game_log_uuid, user_id, is_public)


def get_room_participants_with_ai_ids(room_id):
    """
    根据room_id查询房间参与者及其选择的AI代码ID

    参数:
        room_id: 房间ID

    返回:
        participants: 包含参与者信息的列表 [{user_id, selected_ai_code_id}, ...]
    """
    from database.models import RoomParticipant

    participants = []
    room_participants = RoomParticipant.query.filter_by(room_id=room_id).all()

    for participant in room_participants:
        if not participant.is_ai:  # 只返回人类玩家
            participants.append(
                {
                    "user_id": participant.user_id,
                    "selected_ai_code_id": participant.selected_ai_code_id,
                }
            )

    return participants


def get_ai_code_path(ai_code_id):
    """
    根据ai_code_id获取AI代码文件路径

    参数:
        ai_code_id: AI代码ID

    返回:
        code_path: AI代码文件路径
    """
    from database.models import AICode

    ai_code = AICode.query.get(ai_code_id)
    if not ai_code:
        return None

    # 获取AI代码上传目录
    upload_dir = os.path.join(current_app.root_path, "uploads", "ai_codes")

    # 构建完整文件路径
    file_path = os.path.join(upload_dir, ai_code.code_path)

    return file_path


def get_ai_code_metadata(ai_code_id):
    """
    根据ai_code_id获取AI代码元数据

    参数:
        ai_code_id: AI代码ID

    返回:
        metadata: 元数据字典
    """
    from database.models import AICode

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


def ensure_data_directories():
    """
    确保所有数据目录存在
    """
    data_dir = current_app.config.get("DATA_DIR", "./data")

    # 创建公共日志目录
    os.makedirs(os.path.join(data_dir, "logs", "public"), exist_ok=True)

    # 创建系统日志目录
    os.makedirs(os.path.join(data_dir, "logs", "system"), exist_ok=True)

    # 创建AI代码上传目录
    os.makedirs(os.path.join(data_dir, "uploads", "ai_codes"), exist_ok=True)

    # 创建临时文件目录
    os.makedirs(os.path.join(data_dir, "temp"), exist_ok=True)

    return True
