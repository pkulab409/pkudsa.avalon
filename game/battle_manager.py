"""
对战管理器 - 使用独立进程设计的中央控制器
负责创建、管理和监控所有对战，避免与Flask主进程竞争资源
"""

# 目前存在的问题
# 不同进程的信息共享可能会出现问题，具体表现为无法实时更新游戏状态 TODO
# 其他的问题还在等待发现

import os
import uuid
import logging
import threading
import multiprocessing
import time
import queue
from queue import Queue, Empty
from typing import Dict, Any, Optional, List, Tuple
import pickle
import signal
import sys

# 导入裁判和观察者
from .referee import AvalonReferee
from .observer import Observer
from services.battle_service import BattleService

# 导入装饰器
from .decorator import DebugDecorator, settings

# 配置日志
logger = logging.getLogger("BattleManager")

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# 进程间通信队列
CMD_QUEUE = None  # 命令队列（主进程 -> BattleManager进程）
RESULT_QUEUE = None  # 结果队列（BattleManager进程 -> 主进程）
MANAGER_PROCESS = None  # BattleManager进程引用
INITIALIZED = False  # 全局初始化标志


def calculate_optimal_threads():
    """根据CPU核心数计算最佳线程数量"""
    cpu_count = multiprocessing.cpu_count()
    # I/O密集型任务通常设为CPU核心数的2倍较合适
    # 但设置上限避免线程过多
    return min(cpu_count * 6, 64)


MAX_CONCURRENT_BATTLES = calculate_optimal_threads()  # 默认最大并发对战数


class AdaptiveThreadPool:
    """自适应线程池控制器 (在BattleManager进程内使用)"""

    # 保持原有实现
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


class BattleManagerProcess:
    """在独立进程中运行的对战管理器核心"""

    def __init__(
        self,
        cmd_queue,
        result_queue,
        data_dir,
        max_concurrent_battles=MAX_CONCURRENT_BATTLES,
    ):
        self.cmd_queue = cmd_queue
        self.result_queue = result_queue
        self.data_dir = data_dir
        self.max_concurrent_battles = max_concurrent_battles

        # 初始化对战管理器状态
        self.battles = {}
        self.battle_results = {}
        self.battle_status = {}
        self.battle_observers = {}

        # 添加线程控制
        self._shutdown_event = threading.Event()
        self._thread_lock = threading.Lock()

        # 对战任务队列
        self.battle_queue = Queue(maxsize=100)
        self.worker_threads = []

        # 添加自适应线程池控制
        self.thread_pool = AdaptiveThreadPool(
            initial_threads=max_concurrent_battles,
            min_threads=4,
            max_threads=max_concurrent_battles,
        )

        # 创建数据目录
        os.makedirs(self.data_dir, exist_ok=True)

    def run(self):
        """BattleManager进程的主运行函数"""
        # 设置进程优先级
        try:
            # 降低进程优先级 (UNIX系统)
            os.nice(10)
            logger.info("已设置BattleManager进程的nice值为10")

            if PSUTIL_AVAILABLE:
                # 设置进程优先级 (Windows & UNIX)
                p = psutil.Process(os.getpid())
                if hasattr(p, "nice") and callable(p.nice):
                    if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS"):
                        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                    else:
                        p.nice(10)  # Unix fallback
                    logger.info("已通过psutil降低BattleManager进程优先级")
        except Exception as e:
            logger.warning(f"设置进程优先级失败: {str(e)}")

        # 启动工作线程池
        self._start_worker_threads()

        # 启动监控线程
        self.monitor_thread = threading.Thread(
            target=self._monitor_system_load, daemon=True, name="LoadMonitor"
        )
        self.monitor_thread.start()

        logger.info(
            f"BattleManager进程启动成功，PID: {os.getpid()}, 数据目录: {self.data_dir}"
        )

        # 主消息循环 - 处理来自主进程的命令
        try:
            while not self._shutdown_event.is_set():
                try:
                    cmd, args, kwargs = self.cmd_queue.get(timeout=1.0)
                    self._handle_command(cmd, args, kwargs)
                except Empty:
                    # 队列为空，继续等待
                    continue
                except EOFError:
                    # 队列已关闭（主进程退出）
                    logger.info("检测到主进程已退出，准备关闭BattleManager进程")
                    self._shutdown_event.set()
                    break
                except Exception as e:
                    logger.error(f"处理命令时出错: {str(e)}", exc_info=True)
        except KeyboardInterrupt:
            logger.info("收到中断信号，BattleManager进程准备退出")
        finally:
            # 清理资源
            self._shutdown()
            logger.info("BattleManager进程已关闭")

    def _handle_command(self, cmd, args, kwargs):
        """处理来自主进程的命令"""
        result = None
        error = None

        try:
            if cmd == "start_battle":
                result = self._start_battle(*args, **kwargs)
            elif cmd == "get_battle_status":
                result = self._get_battle_status(*args, **kwargs)
            elif cmd == "get_snapshots_queue":
                result = self._get_snapshots_queue(*args, **kwargs)
            elif cmd == "get_snapshots_archive":
                result = self._get_snapshots_archive(*args, **kwargs)
            elif cmd == "get_battle_result":
                result = self._get_battle_result(*args, **kwargs)
            elif cmd == "get_all_battles":
                result = self._get_all_battles(*args, **kwargs)
            elif cmd == "cancel_battle":
                result = self._cancel_battle(*args, **kwargs)
            elif cmd == "get_queue_status":
                result = self._get_queue_status(*args, **kwargs)
            elif cmd == "shutdown":
                self._shutdown_event.set()
                result = True
            else:
                error = f"未知命令: {cmd}"
                logger.error(error)
        except Exception as e:
            error = str(e)
            logger.exception(f"执行命令 {cmd} 时出错")

        # 发送结果回主进程
        self.result_queue.put((result, error))

    # 以下是原BattleManager的方法实现，保持接口一致
    # 但方法名前加下划线，表示这些是内部方法

    def _start_worker_threads(self):
        """启动工作线程池处理对战队列"""
        with self._thread_lock:
            for i in range(self.max_concurrent_battles):
                thread = threading.Thread(
                    target=self._battle_worker,
                    name=f"BattleWorker-{i}",
                    daemon=True,
                )
                thread.start()
                self.worker_threads.append(thread)
                logger.info(f"工作线程 {thread.name} 已启动")

    def _battle_worker(self):
        """工作线程：从队列获取对战任务并执行"""
        while not self._shutdown_event.is_set():
            try:
                battle_id, participant_data = self.battle_queue.get(timeout=1.0)
                try:
                    logger.info(f"工作线程开始处理对战 {battle_id}")
                    self._execute_battle(battle_id, participant_data)
                except Exception as e:
                    logger.exception(f"处理对战 {battle_id} 时发生异常: {str(e)}")
                    self.battle_status[battle_id] = "error"
                    self.battle_results[battle_id] = {
                        "error": f"处理对战任务时发生异常: {str(e)}"
                    }
                finally:
                    self.battle_queue.task_done()
                    logger.info(f"完成对战 {battle_id} 处理")
            except Empty:
                # 队列为空，继续等待
                continue

    def _adjust_worker_threads(self, target_count):
        """根据目标线程数调整工作线程数量"""
        with self._thread_lock:
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

    def _start_battle(self, battle_id, participant_data, battle_service_data):
        """将对战添加到队列中等待处理"""
        # 创建观察者
        battle_observer = Observer(battle_id)

        # 装饰器
        if settings["observer.Observer"] == 1:
            dec = DebugDecorator(battle_id)
            battle_observer = dec.decorate_instance(battle_observer)

        self.battle_observers[battle_id] = battle_observer
        battle_observer.make_snapshot("BattleManager", (0, "adding battle to queue"))

        if battle_id in self.battles:
            logger.warning(f"对战 {battle_id} 已经在运行中或已存在")
            battle_observer.make_snapshot(
                "BattleManager", (0, f"对战 {battle_id} 已经在运行中或已存在")
            )
            return False

        # 验证参与者数据和AI代码
        player_code_paths = {}

        # 构建增强的参与者数据
        enhanced_participant_data = []
        for p_data in participant_data:
            user_id = p_data.get("user_id")
            ai_code_id = p_data.get("ai_code_id")
            position = p_data.get("position", participant_data.index(p_data) + 1)

            # 增强的参与者数据
            enhanced_data = {
                "user_id": user_id,
                "ai_code_id": ai_code_id,
                "position": position,
            }

            # 从传入的battle_service_data获取AI代码路径
            ai_code_path = battle_service_data.get("code_paths", {}).get(ai_code_id)
            if ai_code_path:
                player_code_paths[position] = ai_code_path
                # 重要：将代码路径也添加到参与者数据中，以便在_execute_battle中使用
                enhanced_data["code_path"] = ai_code_path
            else:
                logger.error(
                    f"无法获取AI代码 {ai_code_id} 路径，对战 {battle_id} 无法启动"
                )
                return False

            enhanced_participant_data.append(enhanced_data)

        if len(player_code_paths) != 7:
            logger.error(
                f"未能为所有7个玩家找到有效的AI代码路径 (找到 {len(player_code_paths)} 个)"
            )
            return False

        # 添加到队列
        self.battle_queue.put((battle_id, enhanced_participant_data))
        self.battle_status[battle_id] = "waiting"
        self.battles[battle_id] = True

        logger.info(
            f"对战 {battle_id} 已加入队列，当前队列大小: {self.battle_queue.qsize()}"
        )
        battle_observer.make_snapshot(
            "BattleManager",
            (0, f"对战已加入队列，等待处理。队列大小: {self.battle_queue.qsize()}"),
        )
        return True

    def _execute_battle(self, battle_id, participant_data):
        """执行对战的核心逻辑"""
        battle_observer = self.battle_observers.get(battle_id)

        try:
            # 更新状态为playing
            self.battle_status[battle_id] = "playing"

            # 准备参与者代码路径
            player_code_paths = {}
            ai_code_id_to_path = {}  # 添加这个映射

            # 首先收集所有AI的代码路径信息
            for p_data in participant_data:
                position = p_data.get("position")
                ai_code_id = p_data.get("ai_code_id")

                # 检查p_data是否包含AI代码ID和位置信息
                if position is None or ai_code_id is None:
                    logger.warning(f"缺少必要的AI信息: {p_data}")
                    continue

                # 从传入的participant_data获取AI代码路径
                if "code_path" in p_data:
                    code_path = p_data["code_path"]
                    player_code_paths[position] = code_path
                    ai_code_id_to_path[ai_code_id] = code_path

            # 创建可用的BattleService代理
            class BattleServiceProxy:
                """提供简单的BattleService代理，仅在进程内使用"""

                def __init__(self, ai_code_paths):
                    # 存储AI代码ID到路径的映射
                    self.ai_code_paths = ai_code_paths if ai_code_paths else {}
                    logger.debug(
                        f"BattleServiceProxy初始化，代码路径映射：{self.ai_code_paths}"
                    )

                def get_ai_code_path(self, ai_code_id):
                    """获取AI代码路径"""
                    path = self.ai_code_paths.get(ai_code_id)
                    # 记录日志以便调试
                    if path is None:
                        logger.warning(f"无法找到AI代码ID的路径: {ai_code_id}")
                    return path

                def mark_battle_as_playing(self, battle_id):
                    """标记对战为进行中"""
                    return True

                def mark_battle_as_completed(self, battle_id, result_data):
                    """标记对战已完成"""
                    return True

                def mark_battle_as_error(self, battle_id, error_details):
                    """标记对战出错"""
                    return True

                def mark_battle_as_cancelled(self, battle_id, cancel_data):
                    """标记对战已取消"""
                    return True

            # 记录调试信息
            logger.debug(
                f"初始化前检查：player_code_paths={player_code_paths}, ai_code_id_to_path={ai_code_id_to_path}"
            )

            # 初始化裁判
            referee = AvalonReferee(
                battle_id=battle_id,
                participant_data=participant_data,
                config={
                    "data_dir": self.data_dir,
                    "player_code_paths": player_code_paths,
                },
                observer=battle_observer,
                battle_service=BattleServiceProxy(
                    ai_code_id_to_path
                ),  # 传入AI代码路径映射
            )

            # 装饰器
            if settings["referee.AvalonReferee"] == 1:
                dec = DebugDecorator(battle_id)
                referee = dec.decorate_instance(referee)

            # 运行游戏
            result_data = referee.run_game()

            # 记录内存结果
            self.battle_results[battle_id] = result_data

            # 处理游戏结果
            if "error" not in result_data and result_data.get("winner") is not None:
                self.battle_status[battle_id] = "completed"
                self._get_snapshots_archive(battle_id)  # 注意这里使用内部方法
            else:
                if "error" in result_data:
                    self.battle_status[battle_id] = "error"

        except Exception as e:
            logger.error(f"对战 {battle_id} 执行失败: {str(e)}", exc_info=True)
            self.battle_status[battle_id] = "error"
            self.battle_results[battle_id] = {"error": f"对战执行失败: {str(e)}"}

        finally:
            # 清理
            if battle_id in self.battles:
                del self.battles[battle_id]

    def _get_battle_status(self, battle_id):
        """获取对战状态"""
        return self.battle_status.get(battle_id)

    def _get_snapshots_queue(self, battle_id):
        """获取并清空游戏快照队列"""
        battle_observer = self.battle_observers.get(battle_id)
        if battle_observer:
            return battle_observer.pop_snapshots()
        return []

    def _get_snapshots_archive(self, battle_id):
        """保存本局所有游戏快照"""
        battle_observer = self.battle_observers.get(battle_id)
        if battle_observer:
            battle_observer.snapshots_to_json()
        return True

    def _get_battle_result(self, battle_id):
        """获取对战结果"""
        return self.battle_results.get(battle_id)

    def _get_all_battles(self):
        """获取内存中所有对战及其状态"""
        return list(self.battle_status.items())

    def _cancel_battle(self, battle_id, reason="Manually cancelled"):
        """取消一个正在进行的对战"""
        current_status = self.battle_status.get(battle_id)

        if current_status not in ["waiting", "playing"]:
            logger.warning(f"对战 {battle_id} 状态为 {current_status}，无法取消")
            return False

        if isinstance(reason, str):
            cancel_data = {"cancellation_reason": reason}
        else:
            cancel_data = reason
            if "cancellation_reason" not in cancel_data:
                cancel_data["cancellation_reason"] = "Battle cancelled by system"

        # 更新内存状态
        self.battle_status[battle_id] = "cancelled"
        self.battle_results[battle_id] = cancel_data

        logger.info(f"对战 {battle_id} 已成功取消：{reason}")
        return True

    def _get_queue_status(self):
        """获取队列状态信息"""
        return {
            "queue_size": self.battle_queue.qsize(),
            "worker_threads": len(self.worker_threads),
            "max_concurrent_battles": self.max_concurrent_battles,
        }

    def _monitor_system_load(self):
        """监控系统负载并调整线程池大小"""
        while not self._shutdown_event.is_set():
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

    def _shutdown(self):
        """关闭对战管理器进程"""
        logger.info("正在关闭BattleManager进程...")
        self._shutdown_event.set()

        # 等待所有任务完成
        try:
            self.battle_queue.join()
        except:
            pass

        # 等待所有线程结束
        for thread in self.worker_threads:
            if thread.is_alive():
                thread.join(timeout=1.0)

        logger.info("BattleManager进程资源已清理完毕")


# 前端代理类 - 保持与原BattleManager相同的接口
class BattleManager:
    """阿瓦隆游戏对战管理器 - 单例模式代理类"""

    _instance = None
    _lock = threading.RLock()

    def __new__(
        cls, battle_service=None, max_concurrent_battles=MAX_CONCURRENT_BATTLES
    ):
        with cls._lock:
            if cls._instance is None:
                if battle_service is None:
                    raise ValueError(
                        "BattleService instance is required to create BattleManager"
                    )
                cls._instance = super(BattleManager, cls).__new__(cls)
                cls._instance._battle_service = battle_service
                cls._instance._max_concurrent_battles = max_concurrent_battles
                cls._instance._initialized = False
            return cls._instance

    def __init__(
        self, battle_service=None, max_concurrent_battles=MAX_CONCURRENT_BATTLES
    ):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.battle_service = self._instance._battle_service
        self.max_concurrent_battles = self._instance._max_concurrent_battles
        self.data_dir = os.environ.get("AVALON_DATA_DIR", "./data")

        # 确保全局进程已初始化
        init_battle_manager_process(self.data_dir, self.max_concurrent_battles)

        self._initialized = True
        logger.info("BattleManager代理类初始化完成")

    def start_battle(self, battle_id, participant_data):
        """将对战添加到队列中等待处理"""
        # 准备AI代码路径数据
        code_paths = {}
        for p_data in participant_data:
            ai_code_id = p_data.get("ai_code_id")
            if ai_code_id:
                code_path = self.battle_service.get_ai_code_path(ai_code_id)
                if code_path:
                    code_paths[ai_code_id] = code_path
                else:
                    logger.error(f"无法获取AI代码 {ai_code_id} 路径")
                    self.battle_service.mark_battle_as_error(
                        battle_id, {"error": f"AI代码 {ai_code_id} 路径无效"}
                    )
                    return False

        # 准备battle_service相关数据
        battle_service_data = {"code_paths": code_paths}

        # 调用进程间通信
        result = send_command(
            "start_battle", (battle_id, participant_data, battle_service_data)
        )

        # 如果启动成功，更新数据库状态
        if result:
            self.battle_service.mark_battle_as_playing(battle_id)
        else:
            self.battle_service.mark_battle_as_error(
                battle_id, {"error": "启动对战失败"}
            )

        return result

    def get_battle_status(self, battle_id):
        """获取对战状态"""
        return send_command("get_battle_status", (battle_id,))

    def get_snapshots_queue(self, battle_id):
        """获取并清空游戏快照队列"""
        return send_command("get_snapshots_queue", (battle_id,))

    def get_snapshots_archive(self, battle_id):
        """保存本局所有游戏快照"""
        return send_command("get_snapshots_archive", (battle_id,))

    def get_battle_result(self, battle_id):
        """获取对战结果"""
        return send_command("get_battle_result", (battle_id,))

    def get_all_battles(self):
        """获取内存中所有对战及其状态"""
        return send_command("get_all_battles")

    def cancel_battle(self, battle_id, reason="Manually cancelled"):
        """取消一个正在进行的对战"""
        result = send_command("cancel_battle", (battle_id, reason))
        if result:
            self.battle_service.mark_battle_as_cancelled(
                battle_id,
                {
                    "cancellation_reason": (
                        reason if isinstance(reason, str) else "Battle cancelled"
                    )
                },
            )
        return result

    def get_queue_status(self):
        """获取队列状态信息"""
        return send_command("get_queue_status")

    def shutdown(self):
        """优雅关闭对战管理器"""
        return send_command("shutdown")


# 进程间通信辅助函数
def send_command(cmd, args=(), kwargs={}):
    """发送命令到BattleManager进程并等待结果"""
    global CMD_QUEUE, RESULT_QUEUE, INITIALIZED

    if not INITIALIZED:
        logger.error("BattleManager进程尚未初始化")
        return None

    try:
        # 发送命令
        CMD_QUEUE.put((cmd, args, kwargs))

        # 等待结果
        result, error = RESULT_QUEUE.get(timeout=30)  # 设置合理的超时时间

        if error:
            logger.error(f"执行命令 {cmd} 时发生错误: {error}")
            return None

        return result
    except Exception as e:
        logger.error(f"与BattleManager进程通信时出错: {str(e)}")
        return None


def init_battle_manager_process(
    data_dir="./data", max_concurrent_battles=MAX_CONCURRENT_BATTLES
):
    """初始化BattleManager进程"""
    global CMD_QUEUE, RESULT_QUEUE, MANAGER_PROCESS, INITIALIZED

    if INITIALIZED:
        return

    # 创建进程间通信队列
    ctx = multiprocessing.get_context("spawn")  # 使用spawn方式，避免继承全局状态
    CMD_QUEUE = ctx.Queue()
    RESULT_QUEUE = ctx.Queue()

    # 创建并启动BattleManager进程
    MANAGER_PROCESS = ctx.Process(
        target=_run_manager_process,
        args=(CMD_QUEUE, RESULT_QUEUE, data_dir, max_concurrent_battles),
        name="BattleManagerProcess",
        daemon=True,
    )
    MANAGER_PROCESS.start()

    # 设置进程终止处理
    import atexit

    atexit.register(_cleanup_manager_process)

    INITIALIZED = True
    logger.info(f"BattleManager进程已启动，PID: {MANAGER_PROCESS.pid}")


def _run_manager_process(cmd_queue, result_queue, data_dir, max_concurrent_battles):
    """BattleManager进程的入口函数"""
    try:
        # 设置信号处理器
        signal.signal(signal.SIGTERM, lambda sig, frame: sys.exit(0))
        signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))

        # 创建并运行BattleManager实例
        manager = BattleManagerProcess(
            cmd_queue, result_queue, data_dir, max_concurrent_battles
        )
        manager.run()
    except Exception as e:
        logger.critical(f"BattleManager进程崩溃: {str(e)}", exc_info=True)
    finally:
        # 确保队列关闭
        try:
            cmd_queue.close()
            result_queue.close()
        except:
            pass


def _cleanup_manager_process():
    """清理BattleManager进程"""
    global MANAGER_PROCESS, INITIALIZED

    if INITIALIZED and MANAGER_PROCESS and MANAGER_PROCESS.is_alive():
        try:
            # 尝试发送关闭命令
            send_command("shutdown")
            # 给进程时间优雅地关闭
            MANAGER_PROCESS.join(timeout=5)

            # 如果进程仍在运行，则强制终止
            if MANAGER_PROCESS.is_alive():
                logger.warning("BattleManager进程未能及时关闭，将强制终止")
                MANAGER_PROCESS.terminate()
                MANAGER_PROCESS.join(timeout=2)
        except Exception as e:
            logger.error(f"清理BattleManager进程时出错: {str(e)}")
