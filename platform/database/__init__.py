# author: shihuaidexianyu (refactored by AI assistant)
# date: 2025-04-25
# status: refactored
# description: 这个文件作为包的入口，导出 db, login_manager 以及 action.py 中定义的操作函数和 models.py 中定义的模型。

# 从 base.py 导出 db 和 login_manager 实例
from .base import db, login_manager

# 从 models.py 导出所有模型类
from .models import User, AICode, GameStats, Battle, BattlePlayer


# 定义数据库初始化函数
def initialize_database(app):
    """初始化数据库并关联应用"""
    db.init_app(app)
    # login_manager 也可以在这里初始化，如果它依赖于 app 配置
    # login_manager.init_app(app)


# 从 action.py 导出所有需要外部使用的数据库操作函数
from .action import (
    # 基础工具 (如果需要在外部使用)
    # safe_commit,
    # safe_add,
    # safe_delete,
    # 用户 (User) 操作
    get_user_by_id,
    get_user_by_username,
    get_user_by_email,
    create_user,
    update_user,
    delete_user,
    # AI 代码 (AICode) 操作
    get_ai_code_by_id,
    get_user_ai_codes,
    get_user_active_ai_code,
    create_ai_code,
    update_ai_code,
    delete_ai_code,
    set_active_ai_code,
    get_ai_code_path_full,
    # 游戏统计 (GameStats) 操作
    get_game_stats_by_user_id,
    create_game_stats,
    update_game_stats,
    get_leaderboard,
    # 对战 (Battle) 及 对战参与者 (BattlePlayer) 操作
    create_battle,
    get_battle_by_id,
    update_battle,
    delete_battle,
    get_battle_players_for_battle,
    process_battle_results_and_update_stats,
    get_user_battle_history,
    get_recent_battles,
    get_battle_player_by_id,
    update_battle_player,
)


# 配置 Flask-Login 的 user_loader (如果不在 action.py 或 app 初始化中配置)
# 注意：确保 get_user_by_id 已经导入
@login_manager.user_loader
def load_user(user_id):
    """Flask-Login 用来加载用户的回调函数"""
    return get_user_by_id(user_id)


# 清理命名空间，只导出希望公开的接口
__all__ = [
    "db",
    "login_manager",
    "initialize_database",
    "load_user",
    # 模型
    "User",
    "AICode",
    "GameStats",
    "Battle",
    "BattlePlayer",
    # 用户操作
    "get_user_by_id",
    "get_user_by_username",
    "get_user_by_email",
    "create_user",
    "update_user",
    "delete_user",
    # AI 操作
    "get_ai_code_by_id",
    "get_user_ai_codes",
    "get_user_active_ai_code",
    "create_ai_code",
    "update_ai_code",
    "delete_ai_code",
    "set_active_ai_code",
    "get_ai_code_path_full",
    # 统计操作
    "get_game_stats_by_user_id",
    "create_game_stats",
    "update_game_stats",
    "get_leaderboard",
    # 对战操作
    "create_battle",
    "get_battle_by_id",
    "update_battle",
    "delete_battle",
    "get_battle_players_for_battle",
    "process_battle_results_and_update_stats",
    "get_user_battle_history",
    "get_recent_battles",
    "get_battle_player_by_id",
    "update_battle_player",
]
