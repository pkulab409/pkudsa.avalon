import logging
import json
from flask import Flask  # 导入 Flask
from typing import Optional
from database import (
    get_battle_by_id,
    update_battle,
    process_battle_results_and_update_stats,
    get_ai_code_path_full,
)
from database.models import (
    Battle,
)

logger = logging.getLogger(__name__)


class BattleService:
    """
    处理与对战相关的数据库交互和服务。
    此类的方法需要一个有效的 Flask 应用上下文来执行。
    """

    def __init__(self, app: Flask):  # 接收 app 实例
        if app is None:
            raise ValueError("Flask app instance is required for BattleService")
        self.app = app  # 存储 app 实例

    def get_ai_code_path(self, ai_code_id: str) -> Optional[str]:
        """获取 AI 代码的完整路径。"""
        try:
            # 数据库操作需要 app context
            with self.app.app_context():
                return get_ai_code_path_full(ai_code_id)
        except Exception as e:
            logger.error(f"获取 AI 代码路径失败 (ID: {ai_code_id}): {e}")
            return None

    def mark_battle_as_playing(self, battle_id: str) -> bool:
        """将数据库中的对战状态更新为 'playing'。"""
        try:
            # 使用 self.app 创建上下文
            with self.app.app_context():
                battle = get_battle_by_id(battle_id)
                if battle:
                    if update_battle(battle, status="playing"):
                        logger.info(f"数据库：对战 {battle_id} 状态更新为 playing")
                        return True
                    else:
                        logger.error(
                            f"数据库：更新对战 {battle_id} 状态为 playing 失败"
                        )
                        return False
                else:
                    logger.error(f"数据库：尝试更新状态时未找到对战 {battle_id}")
                    return False
        except Exception as e:
            # 记录发生在上下文创建或数据库操作期间的异常
            logger.exception(f"更新对战 {battle_id} 状态为 playing 时出错: {e}")
            return False

    def mark_battle_as_completed(self, battle_id: str, result_data: dict) -> bool:
        """处理对战完成，更新数据库状态和统计信息。"""
        try:
            # 使用 self.app 创建上下文
            with self.app.app_context():
                if process_battle_results_and_update_stats(battle_id, result_data):
                    logger.info(f"数据库：对战 {battle_id} 结果处理和统计更新成功")
                    return True
                else:
                    logger.error(f"数据库：对战 {battle_id} 结果处理或统计更新失败")
                    # 尝试标记为 completed 但记录错误
                    battle = get_battle_by_id(battle_id)
                    if battle:
                        update_battle(
                            battle,
                            status="completed",
                            results=json.dumps(
                                {"error": "结果处理失败", **result_data}
                            ),
                        )
                    return False
        except Exception as e:
            logger.exception(f"处理对战 {battle_id} 完成状态时出错: {e}")
            # 尝试在新的上下文中标记为 error
            try:
                with self.app.app_context():
                    self.mark_battle_as_error(
                        battle_id, {"error": f"完成处理时出错: {str(e)}"}
                    )
            except Exception as inner_e:
                logger.exception(
                    f"在处理完成状态错误后，标记对战 {battle_id} 为 error 时再次出错: {inner_e}"
                )
            return False

    def mark_battle_as_error(self, battle_id: str, error_details: dict) -> bool:
        """将数据库中的对战状态更新为 'error'。"""
        try:
            # 使用 self.app 创建上下文
            with self.app.app_context():
                battle = get_battle_by_id(battle_id)
                if battle:
                    if update_battle(
                            battle, status="error", results=json.dumps(error_details)
                    ):
                        logger.info(f"数据库：对战 {battle_id} 状态更新为 error")
                        if process_battle_results_and_update_stats(battle_id, error_details):
                            logger.info(f"数据库：对战 {battle_id} 玩家报错处置成功")
                            return True
                        else:
                            logger.error(f"数据库：对战 {battle_id} 玩家报错处置失败，或不需要处置玩家")
                    else:
                        logger.error(f"数据库：更新对战 {battle_id} 状态为 error 失败")
                        return False
                else:
                    logger.error(f"数据库：尝试更新错误状态时未找到对战 {battle_id}")
                    return False
        except Exception as e:
            logger.exception(f"更新对战 {battle_id} 状态为 error 时出错: {e}")
            return False

    # 新增方法：标记对战为已取消状态
    def mark_battle_as_cancelled(self, battle_id: str, cancel_data: dict) -> bool:
        """
        将数据库中的对战状态更新为 'cancelled'，并处理相关统计。

        参数:
            battle_id (str): 对战ID
            cancel_data (dict): 取消相关数据，如取消原因

        返回:
            bool: 操作是否成功
        """
        try:
            # 使用 self.app 创建上下文
            with self.app.app_context():
                # 先检查对战是否存在
                battle = get_battle_by_id(battle_id)
                if not battle:
                    logger.error(f"数据库：尝试取消时未找到对战 {battle_id}")
                    return False

                # 检查对战状态是否允许取消
                if battle.status not in ["waiting", "playing"]:
                    logger.warning(f"数据库：对战 {battle_id} 状态为 {battle.status}，不适合取消")
                    return False

                # 更新对战状态为cancelled
                if not mark_battle_as_cancelled(battle_id, cancel_data):
                    logger.error(f"数据库：更新对战 {battle_id} 状态为 cancelled 失败")
                    return False

                logger.info(f"数据库：对战 {battle_id} 状态已更新为 cancelled")

                # 处理取消对战的统计数据
                if handle_cancelled_battle_stats(battle_id):
                    logger.info(f"数据库：对战 {battle_id} 取消统计处理成功")
                    return True
                else:
                    logger.error(f"数据库：对战 {battle_id} 取消统计处理失败")
                    return False
        except Exception as e:
            logger.exception(f"取消对战 {battle_id} 时出错: {e}")
            return False

    # 可以添加包装好的日志方法，如果希望 BattleManager 完全不依赖 logging
    def log_info(self, message: str):
        logger.info(message)

    def log_error(self, message: str):
        logger.error(message)

    def log_exception(self, message: str):
        logger.exception(message)


# 修改工厂函数以接收 app
def get_battle_service(app: Flask):
    if app is None:
        raise ValueError("Flask app instance is required to get BattleService")
    # 这里可以添加更复杂的逻辑，例如依赖注入
    return BattleService(app)