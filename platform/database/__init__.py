# 从base.py导出db实例
from .base import db, login_manager


# 定义数据库初始化函数
def initialize_database(app):
    """初始化数据库"""
    db.init_app(app)


# 导出其他需要的函数
from .action import (
    create_battle,
    end_battle,
    update_player_stats,
    update_elo_scores,
    get_player_stats,
    get_leaderboard,
    get_user_battles,
)
