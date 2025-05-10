import logging
from flask import Flask  # 导入 Flask
from game.automatch import AutoMatch

# 配置日志
logger = logging.getLogger("AutoMatchUtils")

# _automatch = None #不再需要缓存实例
_app_ref: Flask = None


def init_automatch_utils(app: Flask):
    """使用 Flask 应用填充_app_ref用于提供automatch模块的app上下文。"""
    global _app_ref
    if app is None:
        raise ValueError("Flask app instance is required for initialization")
    _app_ref = app
    logger.info("AutoMatchUtils initialized with Flask app.")


def get_automatch() -> type[AutoMatch]:  # 返回 AutoMatch 类本身
    """获取自动对战管理器类"""
    # global _automatch # 不再需要全局实例变量
    # if _automatch is None:
    #     # _automatch = AutoMatch(_app_ref) # 这是导致错误的原因
    #     # 正确的做法是，如果 AutoMatch 是一个工具类，则不应该实例化它，
    #     # 或者 AutoMatch 需要一个接受 app 的 __init__ 方法。
    #     # 鉴于 AutoMatch 充满了 @classmethod，它似乎是一个工具类。
    #     logger.info("AutoMatch instance created.") # 这条日志消息可能不再准确
    return AutoMatch  # 直接返回类
