import logging
from queue import Queue
from time import sleep, time
from random import sample, choice, choices, random  # 添加choices和random
from typing import Dict, Any, Optional, List, Tuple, Set, FrozenSet
import threading
import collections  # 添加collections用于OrderedDict

from flask import Flask

from database import (
    create_battle as db_create_battle,
    get_active_ai_codes_by_ranking_ids,  # 使用 action.py 中的函数
    db_create_battles_batch,  # 新增：批量创建对战的数据库操作
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
        # 添加缓存有效期属性
        self._cache_validity_period = 60  # 缓存有效期（秒）
        self._cache_valid = False  # 缓存是否有效的标志

        # 添加组合缓存相关属性
        self._combination_pool = []  # 预计算的组合池
        self._used_combinations = collections.OrderedDict()  # 有序字典记录已使用组合
        self._max_used_combinations = 200  # 增大已使用组合的记录上限
        self._last_participation_time = {}  # 记录每个AI最后参与时间
        self._max_pool_size = 50  # 预计算组合池的最大大小

    def _fetch_participants(self, force_refresh=False):
        """
        获取当前榜单的激活AI代码，使用缓存策略控制查询频率

        Args:
            force_refresh: 是否强制刷新缓存
        """
        current_time = time()

        with self._instance_lock:
            # 检查缓存是否有效
            cache_age = current_time - self._last_fetch_time

            # 如果缓存有效且未强制刷新，直接返回
            if (
                self._cache_valid
                and cache_age < self._cache_validity_period
                and not force_refresh
            ):
                return

            # 如果不强制刷新且距离上次获取时间不足最小间隔，则跳过
            if not force_refresh and cache_age < self._min_fetch_interval:
                return

            # 标记获取时间
            self._last_fetch_time = current_time

        with self.app.app_context():
            # 确保只获取当前榜单的AI代码
            try:
                ai_codes = get_active_ai_codes_by_ranking_ids(
                    ranking_ids=[self.ranking_id]
                )

                with self._instance_lock:
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

                    # 标记缓存为有效
                    self._cache_valid = True

                logger.info(
                    f"[Rank-{self.ranking_id}] 加载到 {len(self.current_participants)} 个激活AI代码。"
                )
            except Exception as e:
                with self._instance_lock:
                    self._cache_valid = False  # 发生错误时标记缓存为无效

                logger.error(
                    f"[Rank-{self.ranking_id}] 获取AI代码时出错: {str(e)}",
                    exc_info=True,
                )

    def _refresh_combination_pool(self):
        """预先计算并缓存可行的参与者组合"""
        with self._instance_lock:
            # 清空现有的组合池
            self._combination_pool.clear()

            participants_count = len(self.current_participants)
            num_to_sample = min(7, participants_count)  # 每场对战的参与者数量

            # 如果参与者不足，直接返回
            if participants_count < self.min_participants:
                return

            current_time = time()

            # 计算每个AI的参与频率权重 (优先选择长时间未参与的AI)
            weights = {}
            for ai_code in self.current_participants:
                last_time = self._last_participation_time.get(ai_code.id, 0)
                # 权重与上次参与的时间间隔成正比
                time_gap = max(1, current_time - last_time)  # 至少为1秒防止除零
                weights[ai_code.id] = time_gap

            # 预计算策略: 当参与者数量较少时，考虑全部组合，否则随机生成
            if participants_count <= 15:  # 较小数量时可以考虑更全面的组合
                self._generate_diverse_combinations(num_to_sample, weights)
            else:
                self._generate_random_combinations(num_to_sample, weights)

            logger.debug(
                f"[Rank-{self.ranking_id}] 已预计算 {len(self._combination_pool)} 个AI组合。"
            )

    def _generate_diverse_combinations(self, num_to_sample, weights):
        """生成多样化的组合，确保每个AI都有机会参与"""
        # 基于参与频率权重生成多样化组合
        all_ai_ids = [ai_code.id for ai_code in self.current_participants]

        # 尝试生成不同的组合
        attempts = 0
        max_attempts = 200  # 最大尝试次数

        while (
            len(self._combination_pool) < self._max_pool_size
            and attempts < max_attempts
        ):
            attempts += 1

            # 根据权重选择AI
            selected_ids = []
            temp_weights = weights.copy()
            available_ids = all_ai_ids.copy()

            while len(selected_ids) < num_to_sample and available_ids:
                # 计算当前可用AI的总权重
                weight_sum = sum(temp_weights[ai_id] for ai_id in available_ids)
                if weight_sum == 0:
                    # 防止所有权重为0的情况
                    ai_id = choice(available_ids)
                else:
                    # 按权重随机选择
                    ai_id = choices(
                        available_ids,
                        weights=[temp_weights[ai_id] for ai_id in available_ids],
                        k=1,
                    )[0]

                selected_ids.append(ai_id)
                available_ids.remove(ai_id)
                # 降低已选AI相邻AI的权重，促进多样性
                for neighbor_id in available_ids:
                    temp_weights[neighbor_id] *= 0.9

            # 生成组合对象
            combination_id = frozenset(selected_ids)

            # 如果这个组合没有被使用过，加入池中
            if (
                combination_id not in self._used_combinations
                and combination_id not in [c[0] for c in self._combination_pool]
            ):
                # 存储(组合ID, 参与者ID列表)
                self._combination_pool.append((combination_id, selected_ids))

    def _generate_random_combinations(self, num_to_sample, weights):
        """生成随机组合填充组合池"""
        # 当参与者数量较多时，使用随机方法生成组合
        participants_by_id = {
            ai_code.id: ai_code for ai_code in self.current_participants
        }

        attempts = 0
        max_attempts = 200

        while (
            len(self._combination_pool) < self._max_pool_size
            and attempts < max_attempts
        ):
            attempts += 1

            # 使用权重随机抽样
            all_ids = list(participants_by_id.keys())
            weights_list = [weights[ai_id] for ai_id in all_ids]

            try:
                # 根据权重随机选择
                selected_ids = sample(all_ids, k=num_to_sample)

                # 确保没有重复
                if len(set(selected_ids)) < num_to_sample:
                    continue

                combination_id = frozenset(selected_ids)

                # 检查是否已被使用
                if (
                    combination_id not in self._used_combinations
                    and combination_id not in [c[0] for c in self._combination_pool]
                ):
                    self._combination_pool.append((combination_id, selected_ids))
            except Exception as e:
                logger.error(
                    f"[Rank-{self.ranking_id}] 生成随机组合时出错: {e}", exc_info=True
                )

    def _get_next_combination(self):
        """从组合池中获取下一个组合"""
        with self._instance_lock:
            # 如果池为空，尝试刷新
            if not self._combination_pool:
                self._refresh_combination_pool()

                # 如果刷新后仍为空，进行最后的随机尝试
                if not self._combination_pool:
                    return self._fallback_random_combination()

            # 从池中取出一个组合
            combination_id, selected_ids = self._combination_pool.pop(0)

            # 记录为已使用
            self._used_combinations[combination_id] = time()

            # 如果已使用组合太多，移除最早的
            if len(self._used_combinations) > self._max_used_combinations:
                self._used_combinations.popitem(
                    last=False
                )  # OrderedDict特性，移除最早插入的

            # 更新每个AI的最后参与时间
            current_time = time()
            for ai_id in selected_ids:
                self._last_participation_time[ai_id] = current_time

            # 返回选中的AI ID列表
            return selected_ids

    def _fallback_random_combination(self):
        """当组合池为空时的备选方案"""
        num_to_sample = min(7, len(self.current_participants))
        if len(self.current_participants) < self.min_participants:
            return None

        # 简单随机选择
        selected_ai_codes = sample(self.current_participants, num_to_sample)
        return [ai_code.id for ai_code in selected_ai_codes]

    def _loop(self):
        """单个榜单的后台对战循环"""
        with self.app.app_context():
            logger.info(
                f"[Rank-{self.ranking_id}] 自动对战循环线程 '{threading.current_thread().name}' 开始运行。"
            )
            battle_manager = get_battle_manager()
            self._fetch_participants(force_refresh=True)  # 初始强制获取

            # 添加指数退避重试逻辑
            retry_delay = 1  # 初始延迟1秒
            max_retry_delay = 60  # 最大延迟60秒

            # 记录上次缓存检查时间
            last_cache_check_time = time()

            while self.is_on:
                try:
                    current_time = time()

                    # 定期检查缓存是否需要更新（在主循环中进行）
                    cache_check_interval = min(
                        30, self._cache_validity_period / 2
                    )  # 设置一个合理的检查间隔
                    if current_time - last_cache_check_time >= cache_check_interval:
                        # 检查并可能更新缓存
                        self._fetch_participants()
                        last_cache_check_time = current_time

                    # 检查参与者数量
                    if len(self.current_participants) < self.min_participants:
                        logger.debug(
                            f"[Rank-{self.ranking_id}] 参与者不足 ({len(self.current_participants)}/{self.min_participants})，等待{retry_delay}秒后重新获取..."
                        )
                        sleep(retry_delay)
                        retry_delay = min(
                            retry_delay * 2, max_retry_delay
                        )  # 指数增加延迟
                        self._fetch_participants(force_refresh=True)  # 重新获取参与者
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
                        self._fetch_participants(
                            force_refresh=True
                        )  # 尝试重新获取更多参与者
                        continue
                    else:
                        retry_delay = 1  # 重置延迟

                    # 替换原有的参与者选择算法
                    try:
                        # 使用新的组合选择算法
                        selected_ai_ids = self._get_next_combination()

                        if not selected_ai_ids:
                            logger.warning(
                                f"[Rank-{self.ranking_id}] 无法获取有效的AI组合，等待后重试。"
                            )
                            sleep(retry_delay)
                            retry_delay = min(retry_delay * 2, max_retry_delay)
                            self._fetch_participants(force_refresh=True)
                            continue

                        # 根据ID查找完整的AI对象信息
                        participants_by_id = {
                            ai_code.id: ai_code for ai_code in self.current_participants
                        }
                        participants_ai_codes = [
                            participants_by_id[ai_id] for ai_id in selected_ai_ids
                        ]

                        # 创建参与者数据
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

        # 重置缓存状态
        with self._instance_lock:
            self._cache_valid = False
            self._last_fetch_time = 0

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
        current_time = time()
        with self._instance_lock:
            cache_age = current_time - self._last_fetch_time
            cache_status = (
                "valid"
                if (self._cache_valid and cache_age < self._cache_validity_period)
                else "invalid"
            )

        return {
            "ranking_id": self.ranking_id,
            "is_on": self.is_on,
            "battle_count": self.battle_count,
            "queue_size": self.battle_queue.qsize(),
            "thread_alive": self.loop_thread.is_alive() if self.loop_thread else False,
            "current_participants_count": len(self.current_participants),
            "cache_status": cache_status,
            "cache_age_seconds": int(cache_age) if self._last_fetch_time > 0 else 0,
        }

    def _batch_create_battles(self, size=5):
        """
        批量创建对战

        Args:
            size: 批量大小，默认5

        Returns:
            创建的对战列表
        """
        battles = []
        for _ in range(size):
            # 准备参与者数据
            if len(self.current_participants) < self.min_participants:
                logger.warning(
                    f"[Rank-{self.ranking_id}] 当前可用参与者不足 ({len(self.current_participants)})，无法批量创建对战。"
                )
                return []  # 参与者不足，返回空列表

            # 随机抽取参与者
            participants_ai_codes = sample(
                self.current_participants, min(size, len(self.current_participants))
            )
            participant_data = [
                {"user_id": ai_code.user_id, "ai_code_id": ai_code.id}
                for ai_code in participants_ai_codes
            ]
            battles.append(participant_data)

        # 一次性创建多场对战
        return db_create_battles_batch(battles, ranking_id=self.ranking_id)


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
