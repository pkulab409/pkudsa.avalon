"""
工具函数包
"""

# 从 db_utils 导入函数
from .db_utils import (
    build_log_file_path,
    get_game_log_path,
    get_ai_code_path,
    get_ai_code_metadata,
    ensure_data_directories,
)

# 从 battle_manager_utils 导入函数
from .battle_manager_utils import get_battle_manager
from game.automatch import AutoMatch

# 定义 __all__ 以便 `from utils import *` 使用
__all__ = [
    # db_utils functions
    "build_log_file_path",
    "get_game_log_path",
    "get_ai_code_path",
    "get_ai_code_metadata",
    "ensure_data_directories",
    # battle_manager_utils functions
    "get_battle_manager",
]
