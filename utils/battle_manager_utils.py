# author: shihuaidexianyu
# date: 2025-04-24
# status: developing
# description: BattleManager工具函数 - 提供统一获取BattleManager单例的方法


import logging
from flask import Flask  # 导入 Flask
from game.battle_manager import BattleManager
from services.battle_service import BattleService, get_battle_service

# 配置日志
logger = logging.getLogger("BattleManagerUtils")

# 全局BattleManager实例缓存
_battle_manager = None
_battle_service = None  # 缓存 service 实例
_app_ref: Flask = None  # 用于存储 Flask app 实例的引用


def init_battle_manager_utils(app: Flask):
    """使用 Flask 应用实例初始化此工具模块。"""
    global _app_ref
    if app is None:
        raise ValueError("Flask app instance is required for initialization")
    _app_ref = app
    logger.info("BattleManagerUtils initialized with Flask app.")


def get_battle_manager() -> BattleManager:
    """获取对战管理器单例实例，并确保注入 BattleService"""
    global _battle_manager
    global _battle_service
    global _app_ref

    if _app_ref is None:
        # 提供更清晰的错误信息
        raise RuntimeError(
            "BattleManagerUtils has not been initialized with the Flask app. Call init_battle_manager_utils(app) first."
        )

    if _battle_manager is None:
        if _battle_service is None:
            try:
                # 将存储的 app 引用传递给工厂函数
                _battle_service = get_battle_service(_app_ref)
                logger.info("BattleService instance created.")
            except Exception as e:
                logger.exception("Failed to create BattleService instance.")
                raise RuntimeError(
                    "Could not initialize BattleService for BattleManager"
                ) from e

        # 创建 BattleManager 并注入 service
        _battle_manager = BattleManager(battle_service=_battle_service)
        logger.info("BattleManager instance created and injected with BattleService.")
    # else: # 移除这个日志，因为它在每次获取时都会打印
    # logger.info("BattleManager instance reused.")
    return _battle_manager


def get_shared_battle_service() -> BattleService:
    """获取共享的 BattleService 实例"""
    global _battle_service
    global _app_ref

    # 优先从已初始化的 manager 获取
    if _battle_manager:
        return _battle_manager.battle_service
    elif _battle_service:
        return _battle_service
    else:
        # 如果 manager 和 service 都未创建，尝试创建 service
        logger.warning(
            "Attempting to get BattleService before BattleManager initialization or reuse."
        )
        if _app_ref:
            try:
                _battle_service = get_battle_service(_app_ref)
                logger.info(
                    "BattleService instance created on demand for get_shared_battle_service."
                )
                return _battle_service
            except Exception as e:
                logger.exception("Failed to create BattleService instance on demand.")
                raise RuntimeError(
                    "Could not get BattleService: Failed to create instance."
                ) from e
        else:
            # 如果没有 app 引用，无法创建
            raise RuntimeError(
                "Cannot get BattleService: BattleManagerUtils not initialized with Flask app."
            )
