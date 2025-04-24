"""
BattleManager工具函数 - 提供统一获取BattleManager单例的方法
"""

import logging
from game.battle_manager import BattleManager
from database.models import Battle, RoomParticipant

# 配置日志
logger = logging.getLogger("BattleManagerUtils")

# 全局BattleManager实例缓存
_battle_manager = None


def get_battle_manager():
    """获取对战管理器实例"""
    # 这里应该从数据库而非内存获取对战管理器状态
    # 具体实现取决于您的对战管理器架构
    pass


def get_player_instance(battle_id, player_id):
    """获取对战中的玩家实例"""
    # 查找对战相关的房间
    battle = Battle.query.get(battle_id)
    if not battle or not battle.room_id:
        return None

    # 查找玩家参与信息
    participant = RoomParticipant.query.filter_by(
        room_id=battle.room_id, user_id=player_id, is_ai=False
    ).first()

    if not participant:
        return None

    # 从数据库获取AI实例
    return participant.get_ai_instance()
