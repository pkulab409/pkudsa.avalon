"""
对战管理器 - 单例模式设计的中央控制器
负责创建、管理和监控所有对战
"""

import os
import uuid
import logging
import threading
from typing import Dict, Any, Optional, List, Tuple

# 导入裁判和观察者
from .referee import AvalonReferee
from .observer import Observer
from services.battle_service import BattleService

# 配置日志 (BattleManager 自身的日志)
logger = logging.getLogger("BattleManager")


class BattleManager:
    """阿瓦隆游戏对战管理器 - 单例模式"""

    _instance = None
    _lock = threading.Lock()

    # 修改 __new__ 以接受 battle_service 和 app
    def __new__(cls, battle_service: BattleService = None, app=None):
        with cls._lock:
            if cls._instance is None:
                if battle_service is None:
                    # 如果在 get_battle_manager 之外创建，需要处理 service
                    raise ValueError(
                        "BattleService instance is required to create BattleManager"
                    )
                cls._instance = super(BattleManager, cls).__new__(cls)
                # 将 service 和 app 存储在实例上，以便 __init__ 可以访问
                cls._instance._battle_service = battle_service
                cls._instance._app = app
                cls._instance._initialized = False
            # 如果实例已存在，确保 service 一致性或忽略新的 service？
            elif (
                battle_service is not None
                and cls._instance._battle_service is not battle_service
            ):
                logger.warning(
                    "BattleManager singleton already exists with a different BattleService instance."
                )
            return cls._instance

    def __init__(self, battle_service: BattleService = None, app=None):  # 添加 app 参数
        if hasattr(self, "_initialized") and self._initialized:
            return

        # 从 _instance 获取 service 和 app
        self.battle_service: BattleService = self._instance._battle_service
        self.app = self._instance._app  # 存储Flask应用实例或上下文

        # 初始化对战管理器
        self.battles: Dict[str, threading.Thread] = {}
        self.battle_results: Dict[str, Dict] = {}
        self.battle_status: Dict[str, str] = {}
        self.battle_observers: Dict[str, Observer] = {}
        self.data_dir = os.environ.get("AVALON_DATA_DIR", "./data")

        os.makedirs(self.data_dir, exist_ok=True)
        logger.info(f"对战管理器初始化完成，数据目录：{self.data_dir}")
        self._initialized = True

    def start_battle(
        self, battle_id: str, participant_data: List[Dict[str, str]]
    ) -> bool:
        """
        启动一个新的对战线程 (不直接与数据库交互)
        """
        if battle_id in self.battles:
            logger.warning(f"对战 {battle_id} 已经在运行中或已存在")
            return False

        # 准备玩家代码路径信息
        player_code_paths = {}
        for p_data in participant_data:
            user_id = p_data.get("user_id")
            ai_code_id = p_data.get("ai_code_id")
            if user_id and ai_code_id:
                # 使用 service 获取路径
                full_path = self.battle_service.get_ai_code_path(ai_code_id)
                if full_path:
                    player_index = participant_data.index(p_data) + 1
                    player_code_paths[player_index] = full_path
                else:
                    # 记录错误，但不直接更新数据库，让调用者或 service 处理
                    logger.error(
                        f"无法获取玩家 {user_id} 的AI代码 {ai_code_id} 路径，对战 {battle_id} 无法启动"
                    )
                    # 可以在这里调用 service 的 mark_battle_as_error
                    self.battle_service.mark_battle_as_error(
                        battle_id, {"error": f"AI代码 {ai_code_id} 路径无效"}
                    )
                    return False
            else:
                logger.error(f"参与者数据不完整 {p_data}，对战 {battle_id} 无法启动")
                self.battle_service.mark_battle_as_error(
                    battle_id, {"error": "参与者数据不完整"}
                )
                return False

        if len(player_code_paths) != 7:
            logger.error(
                f"未能为所有7个玩家找到有效的AI代码路径 (找到 {len(player_code_paths)} 个)，对战 {battle_id} 无法启动"
            )
            self.battle_service.mark_battle_as_error(
                battle_id, {"error": "未能集齐7个有效AI代码"}
            )
            return False

        battle_observer = Observer(battle_id)
        self.battle_observers[battle_id] = battle_observer

        def battle_thread_func():
            try:
                # 1. 更新状态为 playing (通过 service)
                if not self.battle_service.mark_battle_as_playing(battle_id):
                    # 如果更新数据库失败，记录内存状态并终止
                    self.battle_status[battle_id] = "error"
                    self.battle_results[battle_id] = {
                        "error": "无法更新数据库状态为 playing"
                    }
                    logger.error(
                        f"对战 {battle_id} 启动失败：无法更新数据库状态为 playing"
                    )
                    return  # 终止线程

                # 2. 更新内存状态
                self.battle_status[battle_id] = "playing"
                self.battle_service.log_info(
                    f"对战 {battle_id} 线程开始执行"
                )  # 使用 service log

                # 3. 初始化裁判 - 修改这里，传递应用上下文给裁判
                referee = AvalonReferee(
                    battle_id,
                    battle_observer,
                    self.data_dir,
                    player_code_paths,
                    # app_context=self.app,  # 传递Flask应用上下文给裁判 # Removed app_context
                )

                # 4. 运行游戏
                result_data = referee.run_game()

                # 5. 记录内存结果
                self.battle_results[battle_id] = result_data

                # 检查结果是否正常完成 - 只有正常完成才更新状态为 completed
                if "error" not in result_data and result_data.get("winner") is not None:
                    # 只有正常完成的游戏才会更新状态为 completed
                    self.battle_status[battle_id] = "completed"
                    self.get_snapshots_archive(battle_id)  # 保存快照
                    self.battle_service.log_info(
                        f"对战 {battle_id} 结果已保存到 {self.data_dir}"
                    )

                    # 正常结束，更新数据库状态为 completed
                    if self.battle_service.mark_battle_as_completed(
                        battle_id, result_data
                    ):
                        self.battle_service.log_info(
                            f"对战 {battle_id} 完成，结果已处理"
                        )
                    else:
                        # Service 内部已记录错误，BattleManager 只记录内存状态
                        self.battle_service.log_error(
                            f"对战 {battle_id} 完成，但结果处理或数据库更新失败"
                        )
                else:
                    # 非正常完成的情况 (游戏中止、错误等)，不改变状态，只更新结果
                    self.battle_service.log_info(
                        f"对战 {battle_id} 非正常结束，保持原状态，结果已记录"
                    )
                    # 仍然保存快照以便查看游戏进程
                    self.get_snapshots_archive(battle_id)

                    # 如果结果中有错误信息，标记为错误状态
                    if "error" in result_data:
                        self.battle_status[battle_id] = "error"
                        self.battle_service.mark_battle_as_error(battle_id, result_data)
                    else:
                        # 对于中止但无错误的情况（如外部取消），保持原状态
                        self.battle_service.log_info(
                            f"对战 {battle_id} 非正常结束，但未发现错误，保持原状态"
                        )

            except Exception as e:
                # 7. 处理异常 (通过 service)
                self.battle_service.log_exception(
                    f"对战 {battle_id} 线程发生严重错误: {str(e)}"
                )
                self.battle_status[battle_id] = "error"
                error_result = {"error": f"对战执行失败: {str(e)}"}
                self.battle_results[battle_id] = error_result
                # 更新数据库状态为 error (通过 service)
                self.battle_service.mark_battle_as_error(battle_id, error_result)

            finally:
                # 8. 线程结束清理 (可选)
                if battle_id in self.battles:
                    # del self.battles[battle_id]
                    pass
                self.battle_service.log_info(f"对战 {battle_id} 线程结束")

        battle_thread = threading.Thread(
            target=battle_thread_func, name=f"BattleThread-{battle_id}"
        )
        self.battles[battle_id] = battle_thread
        battle_thread.start()

        logger.info(f"对战 {battle_id} 线程已启动")
        return True

    def get_battle_status(self, battle_id: str) -> Optional[str]:
        """获取对战状态 (优先从内存获取)"""
        """可以实时实现与数据库的交汇，清理其余标记的残余记录"""
        return self.battle_status.get(battle_id)

    def get_snapshots_queue(self, battle_id: str) -> List[Dict[str, Any]]:
        """获取并清空游戏快照队列"""
        battle_observer = self.battle_observers.get(battle_id)
        if battle_observer:
            snapshots_queue = battle_observer.pop_snapshots()
            return snapshots_queue
        logger.warning(f"尝试获取不存在的对战 {battle_id} 的快照")
        return []

    def get_snapshots_archive(self, battle_id: str):
        """保存本局所有游戏快照"""
        battle_observer = self.battle_observers.get(battle_id)
        if battle_observer:
            battle_observer.snapshots_to_json()
        else:
            logger.warning(f"尝试获取不存在的对战 {battle_id} 的快照")

    def get_battle_result(self, battle_id: str) -> Optional[Dict[str, Any]]:
        """获取对战结果 (优先从内存获取)"""
        return self.battle_results.get(battle_id)

    def get_all_battles(self) -> List[Tuple[str, str]]:
        """获取内存中所有对战及其状态"""
        return list(self.battle_status.items())

    def cancel_battle(self, battle_id: str, reason: str = "Manually cancelled") -> bool:
        """
        取消一个正在进行的对战

        参数:
            battle_id (str): 对战ID
            reason (str): 取消原因

        返回:
            bool: 操作是否成功
        """
        # 从内存中获取对战状态
        current_status = self.get_battle_status(battle_id)

        # 只有等待中或正在进行的对战可以被取消
        if current_status not in ["waiting", "playing"]:
            logger.warning(f"对战 {battle_id} 状态为 {current_status}，无法取消")
            return False

        # 更新数据库状态为 cancelled
        # 修改这里：确保传递正确的格式
        # 如果 reason 是字符串，就保持原样；如果 reason 已经是字典，就增加 cancellation_reason 字段
        if isinstance(reason, str):
            cancel_data = {"cancellation_reason": reason}
        else:
            cancel_data = reason
            if "cancellation_reason" not in cancel_data:
                cancel_data["cancellation_reason"] = "Battle cancelled by system"

        if not self.battle_service.mark_battle_as_cancelled(battle_id, cancel_data):
            logger.error(f"对战 {battle_id} 取消失败：无法更新数据库状态")
            return False

        # 更新内存状态
        self.battle_status[battle_id] = "cancelled"
        self.battle_results[battle_id] = cancel_data

        logger.info(f"对战 {battle_id} 已成功取消：{reason}")
        return True
