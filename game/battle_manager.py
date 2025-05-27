"""
对战管理器 - 单例模式设计的中央控制器
负责创建、管理和监控所有对战
"""

import os
import uuid
import logging
import threading
import multiprocessing
import time
import queue  # 确保在文件顶部已导入
from queue import Queue
from typing import Dict, Any, Optional, List, Tuple

# 导入裁判和观察者
from .referee import AvalonReferee  # 确保导入正确
from .observer import Observer  # 确保导入正确
from services.battle_service import BattleService

# 导入装饰器
from .decorator import DebugDecorator, settings


# 配置日志 (BattleManager 自身的日志)
logger = logging.getLogger("BattleManager")


try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


def calculate_optimal_threads():
    """根据CPU核心数计算最佳线程数量"""
    cpu_count = multiprocessing.cpu_count()
    # I/O密集型任务通常设为CPU核心数的2倍较合适
    # 但设置上限避免线程过多
    return min(cpu_count * 12, 64)


MAX_CONCURRENT_BATTLES = calculate_optimal_threads()  # 默认最大并发对战数


# 添加自适应线程控制类
class AdaptiveThreadPool:
    """自适应线程池控制器"""

    def __init__(self, initial_threads, min_threads=4, max_threads=32):
        self.current_max_threads = initial_threads
        self.min_threads = min_threads
        self.max_threads = max_threads
        self.active_threads = 0
        self.last_adjustment_time = time.time()

    def adjust_thread_limit(self):
        """根据系统负载调整线程限制"""
        if not PSUTIL_AVAILABLE:
            return

        # 限制调整频率
        current_time = time.time()
        if current_time - self.last_adjustment_time < 30:  # 至少30秒一次调整
            return

        self.last_adjustment_time = current_time

        # 获取系统负载
        cpu_usage = psutil.cpu_percent(interval=0.5)
        memory_percent = psutil.virtual_memory().percent

        # 根据负载调整线程数
        if cpu_usage > 75 or memory_percent > 80:  # 高负载，减少线程
            self._decrease_threads()
        elif cpu_usage < 30 and memory_percent < 60:  # 低负载，增加线程
            self._increase_threads()

    def _increase_threads(self):
        """增加线程数上限"""
        if self.current_max_threads < self.max_threads:
            self.current_max_threads = min(
                self.current_max_threads + 2, self.max_threads
            )
            logger.info(f"系统负载低，增加最大线程数至 {self.current_max_threads}")

    def _decrease_threads(self):
        """减少线程数上限"""
        if self.current_max_threads > self.min_threads:
            self.current_max_threads = max(
                self.current_max_threads - 2, self.min_threads
            )
            logger.info(f"系统负载高，减少最大线程数至 {self.current_max_threads}")

    def get_max_threads(self):
        """获取当前最大线程数"""
        return self.current_max_threads


class BattleManager:
    """阿瓦隆游戏对战管理器 - 单例模式"""

    _instance = None
    _lock = threading.RLock()

    def __new__(
        cls,
        battle_service: BattleService = None,
        max_concurrent_battles: int = MAX_CONCURRENT_BATTLES,
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
        self,
        battle_service: BattleService = None,
        max_concurrent_battles: int = MAX_CONCURRENT_BATTLES,
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

        # 添加线程控制信号量
        self._shutdown_event = threading.Event()
        self._thread_lock = threading.Lock()

        # 修改：限制队列大小为100
        self.battle_queue = Queue(maxsize=100)
        self.worker_threads = []

        # 添加自适应线程池控制
        self.thread_pool = AdaptiveThreadPool(
            initial_threads=max_concurrent_battles,
            min_threads=4,
            max_threads=max_concurrent_battles,
        )

        # 启动工作线程池
        self._start_worker_threads()

        # 添加监控线程
        self.monitor_thread = threading.Thread(
            target=self._monitor_system_load, daemon=True, name="LoadMonitor"
        )
        self.monitor_thread.start()

        os.makedirs(self.data_dir, exist_ok=True)
        logger.info(
            f"对战管理器初始化完成，数据目录：{self.data_dir}，最大并发对战数：{self.max_concurrent_battles}"
        )
        self._initialized = True

    def _start_worker_threads(self):
        """启动工作线程池处理对战队列"""
        with self._thread_lock:
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
        # 设置较低的线程优先级
        try:
            import os

            os.nice(10)  # 增加nice值，降低优先级（仅限UNIX系统）
        except:
            pass

        while not self._shutdown_event.is_set():
            try:
                # 使用超时，以便线程能够定期检查关闭信号
                battle_id, participant_data = self.battle_queue.get(timeout=1.0)
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
            except queue.Empty:  # 使用queue.Empty
                # 队列为空，继续等待
                continue

    def _adjust_worker_threads(self, target_count):
        """根据目标线程数调整工作线程数量"""
        with self._thread_lock:
            current_count = len(self.worker_threads)

            # 移除不活跃线程
            self.worker_threads = [t for t in self.worker_threads if t.is_alive()]

            if len(self.worker_threads) < target_count:
                # 需要增加线程
                for i in range(len(self.worker_threads), target_count):
                    thread = threading.Thread(
                        target=self._battle_worker,
                        name=f"BattleWorker-{i}",
                        daemon=True,
                    )
                    thread.start()
                    self.worker_threads.append(thread)
                    logger.info(
                        f"已增加工作线程 {thread.name}，当前线程数: {len(self.worker_threads)}"
                    )

            # 注意：不主动终止线程，而是让它们自然结束
            # 当线程池缩小时，多余的线程会在处理完当前任务后自动退出

    def start_battle(
        self, battle_id: str, participant_data: List[Dict[str, str]]
    ) -> bool:
        """
        将对战添加到队列中等待处理
        返回：是否成功加入队列
        """
        battle_observer = Observer(battle_id)

        # 装饰器
        if settings["observer.Observer"] == 1:
            # 装饰实例
            dec = DebugDecorator(battle_id)
            battle_observer = dec.decorate_instance(battle_observer)

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

        # 补全 position 信息 - 先从数据库获取完整的 BattlePlayer 记录
        from database.models import BattlePlayer

        battle_players = BattlePlayer.query.filter_by(battle_id=battle_id).all()

        # 创建 BattlePlayer 记录到 participant_data 的映射
        bp_map = {}
        for bp in battle_players:
            bp_map[bp.user_id] = bp

        # 补全 participant_data 中的 position 字段
        enhanced_participant_data = []
        for i, p_data in enumerate(participant_data):
            user_id = p_data.get("user_id")
            ai_code_id = p_data.get("ai_code_id")

            # 如果用户在 BattlePlayer 记录中能找到，使用其位置
            position = bp_map.get(user_id).position if user_id in bp_map else i + 1

            enhanced_participant_data.append(
                {"user_id": user_id, "ai_code_id": ai_code_id, "position": position}
            )

            # 验证 AI 代码路径
            if user_id and ai_code_id:
                full_path = self.battle_service.get_ai_code_path(ai_code_id)
                if full_path:
                    player_code_paths[position] = full_path
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

        # 添加到队列 - 使用补全后的参与者数据
        self.battle_queue.put((battle_id, enhanced_participant_data))
        self.battle_status[battle_id] = "waiting"
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
                battle_id=battle_id,
                participant_data=participant_data,  # 传递参与者数据列表
                config={
                    "data_dir": self.data_dir,
                    "player_code_paths": player_code_paths,
                },  # 配置字典
                observer=battle_observer,  # 观察者对象
                battle_service=self.battle_service,  # 服务对象
            )

            # 装饰器
            if settings["referee.AvalonReferee"] == 1:
                # 装饰实例
                dec = DebugDecorator(battle_id)
                referee = dec.decorate_instance(referee)

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
                    if self.battle_service.mark_battle_as_completed(
                        battle_id, result_data
                    ):
                        self.battle_service.log_info(
                            f"对战 {battle_id} 完成，结果已处理"
                        )
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
            logger.error(f"对战 {battle_id} 执行失败: {str(e)}", exc_info=True)
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
            # 确保线程退出前清理所有资源
            try:
                # 强制清理当前线程的客户端会话
                from .avalon_game_helper import get_current_helper

                helper = get_current_helper()

                # 装饰器
                if settings["avalon_game_helper.GameHelper"] == 1:
                    # 装饰实例
                    dec = DebugDecorator(battle_id)
                    helper = dec.decorate_instance(helper)

                if hasattr(helper, "client_manager"):
                    # 获取当前线程ID，清理相关会话
                    current_thread_id = threading.current_thread().ident
                    logger.info(f"Cleaning up resources for thread {current_thread_id}")
            except Exception as cleanup_e:
                logger.warning(f"Error during thread cleanup: {cleanup_e}")

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
        if current_status not in ["waiting", "playing"]:
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

    def _monitor_system_load(self):
        """监控系统负载并调整线程池大小"""
        while True:
            try:
                self.thread_pool.adjust_thread_limit()
                # 动态调整工作线程数量
                current_max = self.thread_pool.get_max_threads()
                if current_max != self.max_concurrent_battles:
                    old_max = self.max_concurrent_battles
                    self.max_concurrent_battles = current_max
                    logger.info(
                        f"调整最大并发对战数：{old_max} -> {self.max_concurrent_battles}"
                    )

                    # 调整实际工作线程数量
                    self._adjust_worker_threads(self.max_concurrent_battles)

                # 定期清理已结束的线程
                if len(self.worker_threads) > self.max_concurrent_battles:
                    with self._thread_lock:
                        self.worker_threads = [
                            t for t in self.worker_threads if t.is_alive()
                        ]
                    logger.info(f"清理后的工作线程数量: {len(self.worker_threads)}")

                time.sleep(60)  # 每分钟检查一次
            except Exception as e:
                logger.error(f"监控系统负载时出错: {str(e)}")
                time.sleep(120)  # 出错时延长休眠时间

    def shutdown(self):
        """优雅关闭对战管理器"""
        logger.info("正在关闭对战管理器...")
        self._shutdown_event.set()

        # 等待所有任务完成
        self.battle_queue.join()

        # 等待所有线程结束
        for thread in self.worker_threads:
            if thread.is_alive():
                thread.join(timeout=1.0)

        logger.info("对战管理器已关闭")
