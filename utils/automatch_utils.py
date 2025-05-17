import logging
from flask import Flask  # 导入 Flask
from game.automatch import AutoMatch

# 配置日志
logger = logging.getLogger("AutoMatchUtils")

_automatch = None
_app_ref: Flask = None


def init_automatch_utils(app: Flask):
    """使用 Flask 应用填充_app_ref用于提供automatch模块的app上下文。"""
    global _app_ref
    if app is None:
        raise ValueError("Flask app instance is required for initialization")
    _app_ref = app
    logger.info("AutoMatchUtils initialized with Flask app.")


def get_automatch() -> AutoMatch:
    """获取自动对战管理器单例实例"""
    global _automatch

    if _automatch is None:
        _automatch = AutoMatch(_app_ref)
        logger.info("AutoMatch instance created.")

    return _automatch
