import os
import secrets
import yaml
import logging
from datetime import timedelta

# 加载配置文件
config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    yaml_config = yaml.safe_load(f)


class Config:
    # 保存原始配置字典
    _yaml_config = yaml_config

    # 基本配置
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(16)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL"
    ) or "sqlite:///" + os.path.join(
        os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "platform.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 日志配置
    LOG_LEVEL = os.environ.get("LOG_LEVEL") or logging.INFO

    # 从YAML配置文件加载其他配置
    for key, value in yaml_config.items():
        locals()[key] = value
