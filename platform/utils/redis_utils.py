import redis
from flask import current_app
from config.config import Config

# 全局redis客户端实例缓存
_redis_client = None


def get_redis_client():
    """获取Redis客户端实例，确保统一使用decode_responses=True设置"""
    global _redis_client

    # 如果已经有缓存的客户端实例，直接返回
    if _redis_client is not None:
        return _redis_client

    try:
        # 尝试从应用配置获取Redis URL
        redis_url = current_app.config.get("REDIS_URL")
    except RuntimeError:
        # 如果不在应用上下文中，直接从Config获取
        redis_url = Config._yaml_config["redis"]["url"]

    if redis_url is None:
        redis_url = Config._yaml_config["redis"]["url"]

    # 创建新的Redis客户端实例
    _redis_client = redis.from_url(redis_url, decode_responses=True)
    return _redis_client
