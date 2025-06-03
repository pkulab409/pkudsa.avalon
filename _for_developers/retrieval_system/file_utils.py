import re
from pathlib import Path


def sanitize_path(user_input):
    """消毒用户输入路径"""
    # 移除危险字符
    cleaned = re.sub(r'[\\/*?:"<>|]', "", user_input)
    # 限制路径深度
    return Path(cleaned).name[:128]  # 限制最大长度
