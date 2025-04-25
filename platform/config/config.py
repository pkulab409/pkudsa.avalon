import os
import secrets
import yaml
import logging
from datetime import timedelta

# 加载配置文件
# __file__ 指向当前文件 (config.py)
# os.path.dirname(__file__) 获取当前文件所在的目录 (config/)
# os.path.dirname(os.path.dirname(__file__)) 获取上级目录 (platform/)
BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
config_path = os.path.join(os.path.dirname(__file__), "config.yaml")

yaml_config = {}  # 初始化为空字典
try:
    with open(config_path, "r", encoding="utf-8") as f:
        yaml_config = yaml.safe_load(f) or {}  # 确保即使文件为空，也是字典
except FileNotFoundError:
    logging.warning(
        f"Config file not found at {config_path}, using defaults and environment variables."
    )
    # yaml_config 保持为空字典
except yaml.YAMLError as e:
    logging.error(
        f"Error loading config.yaml: {e}. Using defaults and environment variables."
    )
    # yaml_config 保持为空字典


class Config:
    # 保存原始配置字典 (可选，如果不需要可以移除)
    # _yaml_config = yaml_config # 移动到类定义之后设置可能更清晰

    # 基本配置 (优先使用环境变量，其次是默认值)
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(16)
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or f"sqlite:///{os.path.join(BASE_DIR, 'platform.db')}"
    )  # 使用 BASE_DIR 简化路径
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 日志配置
    LOG_LEVEL = os.environ.get("LOG_LEVEL") or logging.INFO

    # --- YAML 加载逻辑移到这里 ---
    # 注意：这里不再需要 if yaml_config 检查，因为 setattr 会在类上创建新属性或覆盖现有属性
    # for key, value in yaml_config.items():
    #     # 如果不希望YAML覆盖环境变量或默认值，可以在这里添加检查
    #     # if not hasattr(Config, key):
    #     setattr(Config, key, value) # 将YAML中的键值对设置为Config类的属性
    # --- YAML 加载逻辑结束 ---


# --- 将 YAML 加载逻辑移到类定义之后 ---
if yaml_config:  # 确保 yaml_config 已成功加载且不为空
    for key, value in yaml_config.items():
        # 检查是否应该覆盖 (可选逻辑)
        # env_var = os.environ.get(key.upper()) # 假设环境变量用大写
        # if env_var is not None and hasattr(Config, key.upper()):
        #     logging.info(f"Skipping YAML config for '{key}' as environment variable '{key.upper()}' is set.")
        #     continue # 如果环境变量已设置，则跳过 YAML 配置

        # 将YAML中的键值对设置为Config类的属性
        # 注意：这里假设 YAML 中的 key 与 Config 类属性名大小写一致或需要转换
        # 如果 YAML key 是小写下划线 (e.g., database_uri) 而类属性是大写 (e.g., DATABASE_URI)
        # 你可能需要转换: setattr(Config, key.upper(), value)
        setattr(Config, key.upper(), value)  # 假设YAML key需要转为大写以匹配类属性
        # 如果 YAML key 和类属性大小写一致，则用 setattr(Config, key, value)

# (可选) 将原始 yaml 配置也添加到 Config 类中，如果需要访问的话
setattr(Config, "_yaml_config", yaml_config)
