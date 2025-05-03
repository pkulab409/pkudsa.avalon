import logging
from flask import Flask # 导入 Flask
from game.automatch import AutoMatch

# 配置日志
logger = logging.getLogger("AutoMatchUtils")

_automatch = None

def get_automatch() -> AutoMatch:
    """获取自动对战管理器单例实例"""
    global _automatch

    if _automatch is None:
        _automatch = AutoMatch()
        logger.info("AutoMatch instance created.")

    return _automatch
