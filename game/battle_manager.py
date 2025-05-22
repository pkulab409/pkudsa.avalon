"""
对战管理器 - 单例模式设计的中央控制器
负责创建、管理和监控所有对战
"""

import os
import uuid
import logging
import threading
from queue import Queue
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
    _lock = threading.RLock()

    def __new__(
        cls, battle_service: BattleService = None, max_concurrent_battles: int = 10
    ):
        with cls._lock:
            if cls._instance is None:
                if battle_service is None:
                    # 如果在 get_battle_manager 之外创建，需要处理 service
                    raise ValueError(
                        "BattleService instance is required to create BattleManager"
                    )
                cls._instance = super(BattleManager, cls).__new__(cls)
                # 将 service 存储在实例上，以便 __init__ 可以访问
                cls._instance._battle_service = battle_service
                cls._instance._max_concurrent_battles = max_concurrent_battles
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

    def __init__(
        self, battle_service: BattleService = None, max_concurrent_battles: int = 10
    ):
        if hasattr(self, "_initialized") and self._initialized:
            return

        # 从 _instance 获取 service
        self.battle_service: BattleService = self._instance._battle_service
        self.max_concurrent_battles = self._instance._max_concurrent_battles

        # 初始化对战管理器
        self.battles: Dict[str, threading.Thread] = {}
        self.battle_results: Dict[str, Dict] = {}
        self.battle_status: Dict[str, str] = {}
        self.battle_observers: Dict[str, Observer] = {}
        self.data_dir = os.environ.get("AVALON_DATA_DIR", "./data")

        # 初始化任务队列
        self.battle_queue = Queue()
        self.worker_threads = []

        # 启动工作线程池
        self._start_worker_threads()

        os.makedirs(self.data_dir, exist_ok=True)
        logger.info(
            f"对战管理器初始化完成，数据目录：{self.data_dir}，最大并发对战数：{self.max_concurrent_battles}"
        )
        self._initialized = True

    def _start_worker_threads(self):
        """启动工作线程池处理对战队列"""
        for i in range(self.max_concurrent_battles):
            thread = threading.Thread(
                target=self._battle_worker,
                name=f"BattleWorker-{i}",
                daemon=True,  # 设为守护线程，随主程序退出
            )
            thread.start()
            self.worker_threads.append(thread)
            logger.info(f"工作线程 {thread.name} 已启动")

    def _battle_worker(self):
        """工作线程：从队列获取对战任务并执行"""
        while True:
            battle_id, participant_data = self.battle_queue.get()
            try:
                logger.info(f"工作线程开始处理对战 {battle_id}")
                self._execute_battle(battle_id, participant_data)
            except Exception as e:
                logger.exception(f"处理对战 {battle_id} 时发生异常: {str(e)}")
                # 确保对战状态被标记为错误
                self.battle_status[battle_id] = "error"
                self.battle_results[battle_id] = {
                    "error": f"处理对战任务时发生异常: {str(e)}"
                }
                self.battle_service.mark_battle_as_error(
                    battle_id, {"error": f"对战任务处理异常: {str(e)}"}
                )
            finally:
                self.battle_queue.task_done()
                logger.info(f"完成对战 {battle_id} 处理")

    def start_battle(
        self, battle_id: str, participant_data: List[Dict[str, str]]
    ) -> bool:
        """
        将对战添加到队列中等待处理
        返回：是否成功加入队列
        """
        battle_observer = Observer(battle_id)
        self.battle_observers[battle_id] = battle_observer

        self.battle_observers[battle_id].make_snapshot(
            "BattleManager", (0, "adding battle to queue")
        )

        if battle_id in self.battles:
            logger.warning(f"对战 {battle_id} 已经在运行中或已存在")
            self.battle_observers[battle_id].make_snapshot(
                "BattleManager", (0, f"对战 {battle_id} 已经在运行中或已存在")
            )
            return False

        # 验证参与者数据和AI代码
        player_code_paths = {}
        for p_data in participant_data:
            user_id = p_data.get("user_id")
            ai_code_id = p_data.get("ai_code_id")
            if user_id and ai_code_id:
                full_path = self.battle_service.get_ai_code_path(ai_code_id)
                if full_path:
                    player_index = participant_data.index(p_data) + 1
                    player_code_paths[player_index] = full_path
                else:
                    logger.error(
                        f"无法获取玩家 {user_id} 的AI代码 {ai_code_id} 路径，对战 {battle_id} 无法启动"
                    )
                    self.battle_observers[battle_id].make_snapshot(
                        "BattleManager",
                        (
                            0,
                            f"无法获取玩家 {user_id} 的AI代码 {ai_code_id} 路径，对战 {battle_id} 无法启动",
                        ),
                    )
                    self.battle_service.mark_battle_as_error(
                        battle_id, {"error": f"AI代码 {ai_code_id} 路径无效"}
                    )
                    return False
            else:
                logger.error(f"参与者数据不完整 {p_data}，对战 {battle_id} 无法启动")
                self.battle_observers[battle_id].make_snapshot(
                    "BattleManager",
                    (0, f"参与者数据不完整 {p_data}，对战 {battle_id} 无法启动"),
                )
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

        # 添加到队列
        self.battle_queue.put((battle_id, participant_data))
        self.battle_status[battle_id] = "queued"
        self.battles[battle_id] = True  # 标记为有效对战，但不再存储线程对象

        logger.info(
            f"对战 {battle_id} 已加入队列，当前队列大小: {self.battle_queue.qsize()}"
        )
        self.battle_observers[battle_id].make_snapshot(
            "BattleManager",
            (0, f"对战已加入队列，等待处理。队列大小: {self.battle_queue.qsize()}"),
        )
        return True

    def _execute_battle(self, battle_id: str, participant_data: List[Dict[str, str]]):
        """
        执行对战的核心逻辑
        由工作线程调用，不直接暴露给外部
        """
        battle_observer = self.battle_observers.get(battle_id)

        try:
            # 1. 更新状态为 playing
            if not self.battle_service.mark_battle_as_playing(battle_id):
                self.battle_status[battle_id] = "error"
                self.battle_results[battle_id] = {
                    "error": "无法更新数据库状态为 playing"
                }
                logger.error(f"对战 {battle_id} 启动失败：无法更新数据库状态为 playing")
                if battle_observer:
                    battle_observer.make_snapshot(
                        "BattleManager",
                        (0, f"对战 {battle_id} 启动失败：无法更新数据库状态为 playing"),
                    )
                return

            # 2. 更新内存状态
            self.battle_status[battle_id] = "playing"
            self.battle_service.log_info(f"对战 {battle_id} 开始执行")
            if battle_observer:
                battle_observer.make_snapshot(
                    "BattleManager", (0, f"对战 {battle_id} 开始执行")
                )

            # 准备参与者代码
            player_code_paths = {}
            for p_data in participant_data:
                user_id = p_data.get("user_id")
                ai_code_id = p_data.get("ai_code_id")
                if user_id and ai_code_id:
                    full_path = self.battle_service.get_ai_code_path(ai_code_id)
                    if full_path:
                        player_index = participant_data.index(p_data) + 1
                        player_code_paths[player_index] = full_path

            # 3. 初始化裁判
            referee = AvalonReferee(
                battle_id, battle_observer, self.data_dir, player_code_paths
            )

            # 4. 运行游戏
            result_data = referee.run_game()

            # 5. 记录内存结果
            self.battle_results[battle_id] = result_data

            # 检查结果是否正常完成
            if "error" not in result_data and result_data.get("winner") is not None:
                # 正常完成
                self.battle_status[battle_id] = "completed"
                self.get_snapshots_archive(battle_id)  # 保存快照
                self.battle_service.log_info(
                    f"对战 {battle_id} 结果已保存到 {self.data_dir}"
                )

                # 更新数据库
                if self.battle_service.mark_battle_as_completed(battle_id, result_data):
                    self.battle_service.log_info(f"对战 {battle_id} 完成，结果已处理")
                else:
                    self.battle_service.log_error(
                        f"对战 {battle_id} 完成，但结果处理或数据库更新失败"
                    )
            else:
                # 非正常完成
                self.battle_service.log_info(
                    f"对战 {battle_id} 非正常结束，保持原状态，结果已记录"
                )
                self.get_snapshots_archive(battle_id)

                # 错误处理
                if "error" in result_data:
                    self.battle_status[battle_id] = "error"
                    self.battle_service.mark_battle_as_error(battle_id, result_data)
                else:
                    self.battle_service.log_info(
                        f"对战 {battle_id} 非正常结束，但未发现错误，保持原状态"
                    )

        except Exception as e:
            # 处理异常
            self.battle_service.log_exception(
                f"对战 {battle_id} 执行过程中发生严重错误: {str(e)}"
            )
            self.battle_status[battle_id] = "error"
            error_result = {"error": f"对战执行失败: {str(e)}"}
            self.battle_results[battle_id] = error_result
            self.battle_service.mark_battle_as_error(battle_id, error_result)

        finally:
            # 清理
            if battle_id in self.battles:
                del self.battles[battle_id]
            self.battle_service.log_info(f"对战 {battle_id} 处理完成")

    def get_queue_status(self) -> dict:
        """获取队列状态信息"""
        return {
            "queue_size": self.battle_queue.qsize(),
            "worker_threads": len(self.worker_threads),
            "max_concurrent_battles": self.max_concurrent_battles,
        }

    # 以下方法保持不变
    def get_battle_status(self, battle_id: str) -> Optional[str]:
        """获取对战状态 (优先从内存获取)"""
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
        if current_status not in ["waiting", "playing", "queued"]:
            logger.warning(f"对战 {battle_id} 状态为 {current_status}，无法取消")
            return False

        # 更新数据库状态为 cancelled
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
