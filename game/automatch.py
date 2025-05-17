import logging
from queue import Queue
from time import sleep
from random import sample, choice # choice 可能用于从多个 target_ranking_ids 中选择一个
from typing import Dict, Any, Optional, List, Tuple, Set
import threading

from flask import Flask

from database import (
    create_battle as db_create_battle,
    get_active_ai_codes_by_ranking_ids  # 使用 action.py 中的函数
)
from database.models import AICode # User 模型可能不再直接在此使用
from utils.battle_manager_utils import get_battle_manager

logger = logging.getLogger("AutoMatch")

MAX_AUTOMATCH_PARALLEL_GAMES_PER_RANKING = 10 # 每个榜单的并行对战数
MIN_PARTICIPANTS_FOR_BATTLE = 7 # 至少需要多少AI才能开始一场对战

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

    def _fetch_participants(self):
        """获取当前榜单的激活AI代码"""
        with self.app.app_context():
            # ranking_ids 参数需要一个列表
            self.current_participants = get_active_ai_codes_by_ranking_ids(
                ranking_ids=[self.ranking_id]
            )
            logger.info(
                f"[Rank-{self.ranking_id}] 加载到 {len(self.current_participants)} 个激活AI代码。"
            )

    def _loop(self):
        """单个榜单的后台对战循环"""
        with self.app.app_context():
            logger.info(
                f"[Rank-{self.ranking_id}] 自动对战循环线程 '{threading.current_thread().name}' 开始运行。"
            )
            battle_manager = get_battle_manager()
            self._fetch_participants() # 初始获取

            while self.is_on:
                if len(self.current_participants) < self.min_participants:
                    logger.debug(
                        f"[Rank-{self.ranking_id}] 参与者不足 ({len(self.current_participants)}/{self.min_participants})，等待5秒后重新获取..."
                    )
                    sleep(5)
                    self._fetch_participants() # 重新获取参与者
                    continue

                try:
                    # 确保抽样数量不超过可用参与者数量，且至少为最小数量
                    num_to_sample = min(7, len(self.current_participants)) # 假设每场最多7人
                    if num_to_sample < self.min_participants:
                        logger.warning(
                            f"[Rank-{self.ranking_id}] 当前可用参与者 {len(self.current_participants)}，不足以抽取 {self.min_participants} 人进行对战，等待后重试。"
                        )
                        sleep(1)
                        self._fetch_participants() # 尝试重新获取更多参与者
                        continue
                    
                    # 从当前获取的参与者中随机抽取
                    participants_ai_codes = sample(self.current_participants, num_to_sample)
                    participant_data = [
                        {"user_id": ai_code.user_id, "ai_code_id": ai_code.id}
                        for ai_code in participants_ai_codes
                    ]

                    # 数据库操作，创建对战时指定 ranking_id
                    battle = db_create_battle(
                        participant_data,
                        ranking_id=self.ranking_id, # 关键：为对战设置ranking_id
                        status="waiting"
                    )

                    if not battle:
                        logger.error(f"[Rank-{self.ranking_id}] 创建对战失败，db_create_battle 返回 None。")
                        sleep(5) # 等待一段时间再重试
                        continue

                    self.battle_queue.put_nowait(battle.id)
                    logger.debug(f"[Rank-{self.ranking_id}] 对战 {battle.id} 已加入队列。队列大小: {self.battle_queue.qsize()}")

                    if self.battle_queue.full():
                        head_battle_id = self.battle_queue.get_nowait()
                        logger.debug(
                            f"[Rank-{self.ranking_id}] 对战队列已满，等待队头对战 {head_battle_id} 结束..."
                        )
                        while self.is_on and battle_manager.get_battle_status(head_battle_id) == "playing":
                            sleep(0.5)
                        if not self.is_on:
                            logger.info(f"[Rank-{self.ranking_id}] 在等待队头对战时收到停止信号。")
                            break 
                    
                    if not self.is_on: # 再次检查停止信号
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
                        f"[Rank-{self.ranking_id}] 自动对战循环中发生错误: {e}", exc_info=True
                    )
                    sleep(5) # 发生错误后等待一段时间

            logger.info(
                f"[Rank-{self.ranking_id}] 自动对战循环线程 '{threading.current_thread().name}' 正常结束。"
            )

    def start(self) -> bool:
        if self.is_on:
            logger.warning(f"[Rank-{self.ranking_id}] 自动对战已在运行，无法重复启动。")
            return False

        self.is_on = True
        self.battle_count = 0 # 重置计数器
        logger.info(f"[Rank-{self.ranking_id}] 启动自动对战...")

        self.loop_thread = threading.Thread(
            target=self._loop,
            name=f"Thread-AutoMatch-Rank-{self.ranking_id}"
        )
        self.loop_thread.daemon = True # 设置为守护线程，主程序退出时会自动结束
        self.loop_thread.start()
        logger.info(f"[Rank-{self.ranking_id}] 自动对战线程 '{self.loop_thread.name}' 已启动。")
        return True

    def stop(self) -> bool:
        if not self.is_on:
            logger.warning(f"[Rank-{self.ranking_id}] 自动对战未运行。")
            return False
        
        self.is_on = False
        logger.info(f"[Rank-{self.ranking_id}] 正在停止自动对战...")
        if self.loop_thread and self.loop_thread.is_alive():
            self.loop_thread.join(timeout=10) # 等待线程结束，设置超时
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
            "current_participants_count": len(self.current_participants)
        }

class AutoMatchManager:
    def __init__(self, app: Flask):
        self.app = app
        self.instances: Dict[int, AutoMatchInstance] = {}
        self.lock = threading.Lock() # 用于同步对 instances 字典的访问

    def start_automatch_for_ranking(self, ranking_id: int, parallel_games: int = MAX_AUTOMATCH_PARALLEL_GAMES_PER_RANKING) -> bool:
        """为指定的 ranking_id 启动自动对战"""
        with self.lock:
            if ranking_id in self.instances and self.instances[ranking_id].is_on:
                logger.warning(f"Ranking ID {ranking_id} 的自动对战已在运行。")
                return False
            
            instance = AutoMatchInstance(self.app, ranking_id, parallel_games)
            self.instances[ranking_id] = instance
        
        return instance.start() # start 方法现在返回 bool

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
                results[ranking_id] = False # 实例可能在迭代间隙被移除
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
    
    def manage_ranking_ids(self, target_ranking_ids: Set[int], parallel_games_per_ranking: int = MAX_AUTOMATCH_PARALLEL_GAMES_PER_RANKING):
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
                    instance.stop() # 停止它
                # 可以选择是否从 self.instances 中移除
                # del self.instances[rank_id] # 如果希望彻底移除管理

            # 为新的目标榜单创建实例（如果尚不存在）
            ids_to_create = target_ranking_ids - current_managed_ids
            for rank_id in ids_to_create:
                if rank_id not in self.instances: # 双重检查
                    logger.info(f"为新的目标榜单 {rank_id} 创建自动对战实例。")
                    self.instances[rank_id] = AutoMatchInstance(self.app, rank_id, parallel_games_per_ranking)
            
            logger.info(f"当前管理的榜单: {list(self.instances.keys())}")

    # 注意：原来的 terminate 可能需要调整，是终止所有还是单个？
    # 这里提供一个终止所有的版本
    def terminate_all_and_clear(self):
        """停止所有自动对战并清除所有实例"""
        self.stop_all_automatch() # 先尝试正常停止
        with self.lock:
            for ranking_id, instance in list(self.instances.items()): # list() for safe iteration while deleting
                if instance.loop_thread and instance.loop_thread.is_alive():
                    logger.warning(f"[Rank-{instance.ranking_id}] 线程仍在活动，在terminate_all中等待...")
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
            instance_to_terminate.stop() # stop() 方法会处理 is_on 和线程join

        # 再次获取锁以安全地从字典中删除
        with self.lock:
            if ranking_id in self.instances: # 再次检查，以防在无锁期间发生变化
                # 确保线程真的结束了 (stop应该已经处理了，但可以再检查)
                if instance_to_terminate.loop_thread and instance_to_terminate.loop_thread.is_alive():
                    logger.warning(f"[Rank-{ranking_id}] 线程在终止操作期间未能按预期停止。可能需要等待守护线程随主程序退出。")
                
                del self.instances[ranking_id]
                logger.info(f"已终止并移除对 Ranking ID {ranking_id} 的自动对战实例管理。")
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