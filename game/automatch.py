import logging
from queue import Queue
from time import sleep, time
from random import sample, choice  # choice 可能用于从多个 target_ranking_ids 中选择一个
from typing import Dict, Any, Optional, List, Tuple, Set, FrozenSet
import threading

from flask import Flask

from database import (
    create_battle as db_create_battle,
    get_active_ai_codes_by_ranking_ids,  # 使用 action.py 中的函数
)
from database.models import AICode  # User 模型可能不再直接在此使用
from utils.battle_manager_utils import get_battle_manager

logger = logging.getLogger("AutoMatch")

MAX_AUTOMATCH_PARALLEL_GAMES_PER_RANKING = 10  # 每个榜单的并行对战数
MIN_PARTICIPANTS_FOR_BATTLE = 7  # 至少需要多少AI才能开始一场对战


class AutoMatchInstance:
    """管理单个榜单的自动对战实例"""

    def __init__(self, app: Flask, ranking_id: int, parallel_games: int):
        self.app = app
        self.ranking_id = ranking_id
        self.is_on = False
        self.battle_count = 0
        self.battle_queue = Queue(parallel_games)
        self.loop_thread: Optional[threading.Thread] = None
        self.current_participants: List[AICode] = []
        self.min_participants = MIN_PARTICIPANTS_FOR_BATTLE
        # 添加实例私有锁，防止该实例内的资源竞争
        self._instance_lock = threading.RLock()
        # 添加上次获取参与者的时间戳，用于控制查询频率
        self._last_fetch_time = 0
        # 最小获取间隔(秒)
        self._min_fetch_interval = 5

    def _fetch_participants(self):
        """获取当前榜单的激活AI代码，添加时间间隔控制避免频繁查询"""
        current_time = time()

        # 如果距离上次获取时间不足最小间隔，则跳过
        if current_time - self._last_fetch_time < self._min_fetch_interval:
            return

        with self._instance_lock:
            self._last_fetch_time = current_time

        with self.app.app_context():
            # 确保只获取当前榜单的AI代码
            try:
                ai_codes = get_active_ai_codes_by_ranking_ids(
                    ranking_ids=[self.ranking_id]
                )

                # 立即提取AICode的所有需要的数据，包括ID，用户ID等
                # 这样在session关闭后仍可安全访问这些数据
                self.current_participants = []
                for ai_code in ai_codes:
                    # 创建AICode的副本，并确保所有需要的属性都被获取
                    ai_code_copy = AICode(
                        id=ai_code.id,
                        user_id=ai_code.user_id,
                        name=ai_code.name,
                        code_path=ai_code.code_path,
                        description=ai_code.description,
                        is_active=ai_code.is_active,
                        created_at=ai_code.created_at,
                        version=ai_code.version,
                    )
                    self.current_participants.append(ai_code_copy)

                logger.info(
                    f"[Rank-{self.ranking_id}] 加载到 {len(self.current_participants)} 个激活AI代码。"
                )
            except Exception as e:
                logger.error(
                    f"[Rank-{self.ranking_id}] 获取AI代码时出错: {str(e)}",
                    exc_info=True,
                )

    def _loop(self):
        """单个榜单的后台对战循环"""
        with self.app.app_context():
            logger.info(
                f"[Rank-{self.ranking_id}] 自动对战循环线程 '{threading.current_thread().name}' 开始运行。"
            )
            battle_manager = get_battle_manager()
            self._fetch_participants()  # 初始获取

            # 添加指数退避重试逻辑
            retry_delay = 1  # 初始延迟1秒
            max_retry_delay = 60  # 最大延迟60秒

            while self.is_on:
                try:
                    # 检查参与者数量
                    if len(self.current_participants) < self.min_participants:
                        logger.debug(
                            f"[Rank-{self.ranking_id}] 参与者不足 ({len(self.current_participants)}/{self.min_participants})，等待{retry_delay}秒后重新获取..."
                        )
                        sleep(retry_delay)
                        retry_delay = min(
                            retry_delay * 2, max_retry_delay
                        )  # 指数增加延迟
                        self._fetch_participants()  # 重新获取参与者
                        continue
                    else:
                        retry_delay = 1  # 重置延迟

                    # 确保抽样数量不超过可用参与者数量，且至少为最小数量
                    num_to_sample = min(
                        7, len(self.current_participants)
                    )  # 假设每场最多7人
                    if num_to_sample < self.min_participants:
                        logger.warning(
                            f"[Rank-{self.ranking_id}] 当前可用参与者 {len(self.current_participants)}，不足以抽取 {self.min_participants} 人进行对战，等待后重试。"
                        )
                        sleep(retry_delay)
                        retry_delay = min(retry_delay * 2, max_retry_delay)
                        self._fetch_participants()  # 尝试重新获取更多参与者
                        continue
                    else:
                        retry_delay = 1  # 重置延迟

                    # 添加随机性和唯一性检查，确保不重复选择相同AI组合
                    try:
                        # 从当前获取的参与者中随机抽取，同时避免重复组合
                        selected_combinations = getattr(
                            self, "_selected_combinations", set()
                        )
                        if not hasattr(self, "_selected_combinations"):
                            self._selected_combinations = selected_combinations

                        max_attempts = 10  # 最多尝试10次不同组合
                        participants_ai_codes = None

                        for _ in range(max_attempts):
                            participants_ai_codes = sample(
                                self.current_participants, num_to_sample
                            )
                            # 创建组合标识符 - 使用安全的方式获取ID以避免会话问题
                            try:
                                combination_id = frozenset(
                                    ai_code.id for ai_code in participants_ai_codes
                                )
                            except Exception as e:
                                logger.error(
                                    f"[Rank-{self.ranking_id}] 创建对战组合ID时出错: {e}",
                                    exc_info=True,
                                )
                                # 重新获取参与者列表并尝试一次
                                self._fetch_participants()
                                sleep(1)  # 短暂休眠
                                continue

                            # 检查是否是近期使用过的组合
                            if combination_id not in selected_combinations:
                                # 记录此组合
                                selected_combinations.add(combination_id)
                                # 限制记录集大小，防止无限增长
                                if len(selected_combinations) > 100:
                                    # 移除最早添加的组合
                                    selected_combinations.pop()
                                break

                        participant_data = [
                            {"user_id": ai_code.user_id, "ai_code_id": ai_code.id}
                            for ai_code in participants_ai_codes
                        ]

                        # 数据库操作，创建对战时指定 ranking_id
                        battle = db_create_battle(
                            participant_data,
                            ranking_id=self.ranking_id,  # 关键：为对战设置ranking_id
                            status="waiting",
                        )

                        if not battle:
                            logger.error(
                                f"[Rank-{self.ranking_id}] 创建对战失败，db_create_battle 返回 None。"
                            )
                            sleep(retry_delay)  # 等待一段时间再重试
                            retry_delay = min(retry_delay * 2, max_retry_delay)
                            continue
                        else:
                            retry_delay = 1  # 重置延迟

                        self.battle_queue.put_nowait(battle.id)
                        logger.debug(
                            f"[Rank-{self.ranking_id}] 对战 {battle.id} 已加入队列。队列大小: {self.battle_queue.qsize()}"
                        )

                        if self.battle_queue.full():
                            head_battle_id = self.battle_queue.get_nowait()
                            logger.debug(
                                f"[Rank-{self.ranking_id}] 对战队列已满，等待队头对战 {head_battle_id} 结束..."
                            )
                            while (
                                self.is_on
                                and battle_manager.get_battle_status(head_battle_id)
                                == "playing"
                            ):
                                sleep(0.5)
                            if not self.is_on:
                                logger.info(
                                    f"[Rank-{self.ranking_id}] 在等待队头对战时收到停止信号。"
                                )
                                break

                        if not self.is_on:  # 再次检查停止信号
                            break

                        self.battle_count += 1
                        logger.info(
                            f"[Rank-{self.ranking_id}] 启动第 {self.battle_count} 次自动对战 (Battle ID: {battle.id})。"
                        )
                        battle_manager.start_battle(battle.id, participant_data)

                        # 短暂休眠，避免CPU高占用和过于频繁的对战创建
                        sleep(1)

                    except Exception as e:
                        logger.error(
                            f"[Rank-{self.ranking_id}] 创建对战循环中发生错误: {e}",
                            exc_info=True,
                        )
                        sleep(retry_delay)  # 发生错误后等待一段时间
                        retry_delay = min(retry_delay * 2, max_retry_delay)

                except Exception as e:
                    logger.error(
                        f"[Rank-{self.ranking_id}] 自动对战循环中发生错误: {e}",
                        exc_info=True,
                    )
                    sleep(retry_delay)  # 发生错误后等待一段时间
                    retry_delay = min(retry_delay * 2, max_retry_delay)

            logger.info(
                f"[Rank-{self.ranking_id}] 自动对战循环线程 '{threading.current_thread().name}' 正常结束。"
            )

    def start(self) -> bool:
        if self.is_on:
            logger.warning(f"[Rank-{self.ranking_id}] 自动对战已在运行，无法重复启动。")
            return False

        self.is_on = True
        self.battle_count = 0  # 重置计数器
        logger.info(f"[Rank-{self.ranking_id}] 启动自动对战...")

        self.loop_thread = threading.Thread(
            target=self._loop, name=f"Thread-AutoMatch-Rank-{self.ranking_id}"
        )
        self.loop_thread.daemon = True  # 设置为守护线程，主程序退出时会自动结束
        self.loop_thread.start()
        logger.info(
            f"[Rank-{self.ranking_id}] 自动对战线程 '{self.loop_thread.name}' 已启动。"
        )
        return True

    def stop(self) -> bool:
        if not self.is_on:
            logger.warning(f"[Rank-{self.ranking_id}] 自动对战未运行。")
            return False

        self.is_on = False
        logger.info(f"[Rank-{self.ranking_id}] 正在停止自动对战...")
        if self.loop_thread and self.loop_thread.is_alive():
            self.loop_thread.join(timeout=10)  # 等待线程结束，设置超时
            if self.loop_thread.is_alive():
                logger.warning(f"[Rank-{self.ranking_id}] 自动对战线程未能及时停止。")
        logger.info(f"[Rank-{self.ranking_id}] 自动对战已停止。")
        return True

    def get_status(self) -> dict:
        return {
            "ranking_id": self.ranking_id,
            "is_on": self.is_on,
            "battle_count": self.battle_count,
            "queue_size": self.battle_queue.qsize(),
            "thread_alive": self.loop_thread.is_alive() if self.loop_thread else False,
            "current_participants_count": len(self.current_participants),
        }


class AutoMatchManager:
    def __init__(self, app: Flask):
        self.app = app
        self.instances: Dict[int, AutoMatchInstance] = {}
        self.lock = threading.Lock()  # 用于同步对 instances 字典的访问

    def start_automatch_for_ranking(
        self,
        ranking_id: int,
        parallel_games: int = MAX_AUTOMATCH_PARALLEL_GAMES_PER_RANKING,
    ) -> bool:
        """为指定的 ranking_id 启动自动对战"""
        logger.info(f"尝试为 Ranking ID {ranking_id} 启动自动对战")

        with self.lock:
            instance = self.instances.get(ranking_id)

            # 如果实例存在且已在运行，则返回False
            if instance and instance.is_on:
                logger.warning(f"Ranking ID {ranking_id} 的自动对战已在运行。")
                return False

            # 如果实例不存在，则创建新实例
            if not instance:
                instance = AutoMatchInstance(self.app, ranking_id, parallel_games)
                self.instances[ranking_id] = instance
                logger.info(f"为 Ranking ID {ranking_id} 创建新的自动对战实例。")

        # 实例已创建，尝试启动它（在锁外执行避免长时间持有锁）
        success = instance.start()

        if success:
            logger.info(f"Ranking ID {ranking_id} 的自动对战已成功启动。")
        else:
            logger.error(f"Ranking ID {ranking_id} 的自动对战启动失败。")

        return success

    def stop_automatch_for_ranking(self, ranking_id: int) -> bool:
        """停止指定 ranking_id 的自动对战"""
        with self.lock:
            instance = self.instances.get(ranking_id)
            if not instance or not instance.is_on:
                logger.warning(f"Ranking ID {ranking_id} 的自动对战未运行或不存在。")
                return False
        return instance.stop()

    def start_all_managed_automatch(self) -> Dict[int, bool]:
        """启动所有当前管理的（即已创建实例的）ranking_id的自动对战"""
        results = {}
        # 创建副本进行迭代，以防在循环中修改字典 (虽然当前逻辑不会)
        instance_ids_to_start = []
        with self.lock:
            instance_ids_to_start = list(self.instances.keys())

        for ranking_id in instance_ids_to_start:
            # start_automatch_for_ranking 内部有锁，所以这里不需要再锁
            # 但为了确保获取的是最新的实例，还是在锁内获取
            instance = None
            with self.lock:
                instance = self.instances.get(ranking_id)

            if instance:
                results[ranking_id] = instance.start()
            else:
                results[ranking_id] = False  # 实例可能在迭代间隙被移除
        return results

    def stop_all_automatch(self) -> Dict[int, bool]:
        """停止所有正在运行的自动对战"""
        results = {}
        # 创建副本进行迭代
        running_instance_ids = []
        with self.lock:
            for rank_id, instance in self.instances.items():
                if instance.is_on:
                    running_instance_ids.append(rank_id)

        for ranking_id in running_instance_ids:
            results[ranking_id] = self.stop_automatch_for_ranking(ranking_id)
        return results

    def get_status_for_ranking(self, ranking_id: int) -> Optional[dict]:
        with self.lock:
            instance = self.instances.get(ranking_id)
            if instance:
                return instance.get_status()
        return None

    def get_all_statuses(self) -> Dict[int, dict]:
        statuses = {}
        with self.lock:
            for ranking_id, instance in self.instances.items():
                statuses[ranking_id] = instance.get_status()
        return statuses

    def is_on(self):
        statuses = self.get_all_statuses()
        for ranking_id in statuses:
            if statuses[ranking_id]["is_on"]:
                return True
        return False

    def manage_ranking_ids(
        self,
        target_ranking_ids: Set[int],
        parallel_games_per_ranking: int = MAX_AUTOMATCH_PARALLEL_GAMES_PER_RANKING,
    ):
        """
        管理自动对战实例，确保只为 target_ranking_ids 运行。
        会停止不在 target_ranking_ids 中的现有对战，并为新的 target_ranking_ids 创建（但不一定启动）实例。
        """
        with self.lock:
            current_managed_ids = set(self.instances.keys())

            # 停止不再需要的榜单的自动对战
            ids_to_stop = current_managed_ids - target_ranking_ids
            for rank_id in ids_to_stop:
                instance = self.instances.get(rank_id)
                if instance and instance.is_on:
                    logger.info(f"榜单 {rank_id} 不再是目标，停止其自动对战。")
                    instance.stop()  # 停止它

            # 为新的目标榜单创建实例（如果尚不存在）
            ids_to_create = target_ranking_ids - current_managed_ids
            for rank_id in ids_to_create:
                if rank_id not in self.instances:  # 双重检查
                    logger.info(f"为新的目标榜单 {rank_id} 创建自动对战实例。")
                    self.instances[rank_id] = AutoMatchInstance(
                        self.app, rank_id, parallel_games_per_ranking
                    )

            logger.info(f"当前管理的榜单: {list(self.instances.keys())}")
            return True

    def terminate_all_and_clear(self):
        """停止所有自动对战并清除所有实例"""
        self.stop_all_automatch()  # 先尝试正常停止
        with self.lock:
            for ranking_id, instance in list(
                self.instances.items()
            ):  # list() for safe iteration while deleting
                if instance.loop_thread and instance.loop_thread.is_alive():
                    logger.warning(
                        f"[Rank-{instance.ranking_id}] 线程仍在活动，在terminate_all中等待..."
                    )
                    # 通常不建议强制终止线程，但守护线程会在主程序退出时结束
                    # instance.loop_thread.join(timeout=5) # 可以尝试再join一下
                del self.instances[ranking_id]
            logger.info("所有自动对战实例已终止并清除。")

    def terminate_ranking_instance(self, ranking_id: int) -> bool:
        """
        彻底停止并移除对指定 ranking_id 的自动对战实例的管理。
        会先尝试正常停止线程，然后从管理器中删除该实例。

        Args:
            ranking_id (int): 要终止的榜单ID。

        Returns:
            bool: 如果实例存在并被终止和移除，则返回True；否则返回False。
        """
        instance_to_terminate: Optional[AutoMatchInstance] = None
        was_on = False

        with self.lock:
            if ranking_id not in self.instances:
                logger.warning(f"尝试终止不存在的榜单实例: Ranking ID {ranking_id}")
                return False

            instance_to_terminate = self.instances[ranking_id]
            was_on = instance_to_terminate.is_on

        # 先尝试正常停止，这会将 is_on 设置为 False 并 join 线程
        if was_on:
            logger.info(f"正在正常停止榜单 {ranking_id} 的自动对战以准备终止...")
            instance_to_terminate.stop()  # stop() 方法会处理 is_on 和线程join

        # 再次获取锁以安全地从字典中删除
        with self.lock:
            if ranking_id in self.instances:  # 再次检查，以防在无锁期间发生变化
                # 确保线程真的结束了 (stop应该已经处理了，但可以再检查)
                if (
                    instance_to_terminate.loop_thread
                    and instance_to_terminate.loop_thread.is_alive()
                ):
                    logger.warning(
                        f"[Rank-{ranking_id}] 线程在终止操作期间未能按预期停止。可能需要等待守护线程随主程序退出。"
                    )

                del self.instances[ranking_id]
                logger.info(
                    f"已终止并移除对 Ranking ID {ranking_id} 的自动对战实例管理。"
                )
                return True
            else:
                # 如果实例在stop()之后因为某些并发原因被移除了 (理论上不应该，因为stop后仍然是同一个对象)
                logger.warning(f"Ranking ID {ranking_id} 在终止过程中从管理器中消失。")
                return False


# 如何在 Flask 应用中使用 AutoMatchManager:
# app.py 或 extensions.py
# automatch_manager = AutoMatchManager(app)
# app.extensions['automatch_manager'] = automatch_manager

# 在你的 admin 蓝图或启动脚本中:
# from flask import current_app
# manager = current_app.extensions['automatch_manager']
# manager.manage_ranking_ids({0, 1, 2}) # 定义要管理的榜单
# manager.start_automatch_for_ranking(0)
# manager.start_automatch_for_ranking(1)
# ...
# status = manager.get_all_statuses()
