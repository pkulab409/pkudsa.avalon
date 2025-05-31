import logging
from queue import Queue, Empty, Full # Import Empty and Full for specific exception handling
from time import sleep, time
from random import sample
from typing import Dict, Any, Optional, List, Tuple, Set, FrozenSet
import threading

from flask import Flask

from database import (
    create_battle as db_create_battle,
    get_active_ai_codes_by_ranking_ids,
)
from database.models import AICode
from utils.battle_manager_utils import get_battle_manager

logger = logging.getLogger("AutoMatch")

# --- Constants ---
MAX_RETRY_DELAY_SECONDS = 60
INITIAL_RETRY_DELAY_SECONDS = 1
PARTICIPANT_REFRESH_INTERVAL_BATTLES = 10  # Refresh participants every N battles
LOOP_SHORT_SLEEP_SECONDS = 0.1  # Short sleep to prevent tight loops when no work
LOOP_POST_BATCH_SLEEP_SECONDS = 1 # Sleep after creating a batch of battles
QUEUE_WAIT_TIMEOUT_SECONDS = 5 # Timeout for getting from queue if we expect it to unblock
BATTLE_STATUS_POLL_INTERVAL_SECONDS = 0.5 # How often to check battle status when waiting

MAX_AUTOMATCH_PARALLEL_GAMES_PER_RANKING = 20
PARTICIPANTS = 7

class AutoMatchInstance:
    def __init__(self, app: Flask, ranking_id: int, parallel_games: int):
        self.app = app
        self.ranking_id = ranking_id
        self.is_on = False
        self.battle_count = 0 # Total battles created by this instance since start
        self.battle_queue = Queue(parallel_games) # Stores IDs of battles that are supposed to be running
        self.loop_thread: Optional[threading.Thread] = None
        self.min_participants = PARTICIPANTS
        self._instance_lock = threading.RLock()
        self.current_participants: List[AICode] = []
        self._battles_since_last_refresh = 0

        # Load participants once during initialization (initial load)
        self._refresh_participants() # Call the new refresh method

    def _refresh_participants(self):
        """Fetches active AI codes for the ranking_id and updates self.current_participants."""
        with self.app.app_context():
            try:
                logger.info(f"[Rank-{self.ranking_id}] Refreshing participant list...")
                fresh_participants = get_active_ai_codes_by_ranking_ids(
                    ranking_ids=[self.ranking_id]
                )
                with self._instance_lock: # Protect assignment
                    self.current_participants = fresh_participants
                    self._battles_since_last_refresh = 0 # Reset counter
                logger.info(
                    f"[Rank-{self.ranking_id}] Refreshed participants. Loaded {len(self.current_participants)} active AI codes."
                )
            except Exception as e:
                logger.error(
                    f"[Rank-{self.ranking_id}] Error fetching AI codes during refresh: {str(e)}",
                    exc_info=True,
                )
                # Optionally, decide if current_participants should be cleared or kept stale
                # with self._instance_lock:
                #     self.current_participants = [] # Example: clear on error

    def _should_refresh_participants(self) -> bool:
        """Determines if participants should be refreshed."""
        with self._instance_lock: # Access shared counter
            if not self.current_participants: # Always refresh if list is empty
                return True
            if self._battles_since_last_refresh >= PARTICIPANT_REFRESH_INTERVAL_BATTLES:
                return True
        return False

    def _loop(self):
        """Single ranking's background battle loop."""
        with self.app.app_context(): # Ensure app context for the whole loop if db calls are frequent
            logger.info(
                f"[Rank-{self.ranking_id}] Auto-match loop thread '{threading.current_thread().name}' started."
            )
            battle_manager = get_battle_manager()
            retry_delay = INITIAL_RETRY_DELAY_SECONDS

            while self.is_on:
                try:
                    # 1. Refresh participants if needed
                    if self._should_refresh_participants():
                        self._refresh_participants()

                    # 2. Check participant count
                    with self._instance_lock: # Access current_participants safely
                        num_current_participants = len(self.current_participants)
                    
                    if num_current_participants < self.min_participants:
                        logger.info(
                            f"[Rank-{self.ranking_id}] Insufficient participants ({num_current_participants}/{self.min_participants}). "
                            f"Waiting {retry_delay}s before retrying participant check."
                        )
                        sleep(retry_delay)
                        retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY_SECONDS)
                        continue # Go to next iteration to re-check/refresh

                    # Reset retry_delay if participant check was successful
                    retry_delay = INITIAL_RETRY_DELAY_SECONDS

                    # 3. Create battles in batch if queue has space
                    batch_size = 5
                    battles_created_in_batch = 0
                    
                    # We can only create battles if the queue is not full.
                    # qsize() is approximate, so loop while !full() is safer for adding.
                    while battles_created_in_batch < batch_size and not self.battle_queue.full():
                        with self._instance_lock: # For reading current_participants
                            if len(self.current_participants) < self.min_participants:
                                break # Not enough participants for another battle in this batch
                            # Sample from a copy to avoid issues if list changes during sampling (though lock helps)
                            participants_ai_codes = sample(
                                list(self.current_participants), self.min_participants 
                            )
                        
                        participant_data = [
                            {"user_id": ai_code.user_id, "ai_code_id": ai_code.id}
                            for ai_code in participants_ai_codes
                        ]

                        battle = db_create_battle(
                            participant_data,
                            ranking_id=self.ranking_id,
                            status="waiting",
                        )

                        if not battle:
                            logger.error(
                                f"[Rank-{self.ranking_id}] Failed to create battle, db_create_battle returned None."
                            )
                            continue # Try next battle creation in batch

                        try:
                            self.battle_queue.put_nowait(battle.id) # Add to queue
                            battles_created_in_batch += 1
                            with self._instance_lock:
                                self.battle_count += 1
                                self._battles_since_last_refresh += 1
                            
                            logger.info(
                                f"[Rank-{self.ranking_id}] Started auto-match battle {self.battle_count} (ID: {battle.id}). "
                                f"Queue size: {self.battle_queue.qsize()}"
                            )
                            battle_manager.start_battle(battle.id, participant_data)
                        except Full:
                            logger.warning(f"[Rank-{self.ranking_id}] Queue became full while trying to add battle {battle.id}. Batch interrupted.")
                            # If db_create_battle created a battle but we can't queue it, it's an orphan.
                            # This scenario should be rare if `not self.battle_queue.full()` check is effective.
                            # Consider how to handle such an orphaned battle (e.g., try to cancel it).
                            break # Exit batch creation loop

                    # 4. If queue is full, wait for a slot to free up.
                    if self.battle_queue.full():
                        logger.debug(
                            f"[Rank-{self.ranking_id}] Battle queue is full ({self.battle_queue.qsize()}). Waiting for a slot..."
                        )
                        try:
                            # Get a battle ID from the queue. This blocks until an item is available.
                            # This ID represents a battle that *was* considered active.
                            finished_battle_id = self.battle_queue.get(block=True, timeout=QUEUE_WAIT_TIMEOUT_SECONDS)
                            
                            # Now, explicitly wait for this specific battle to finish if it's still running.
                            # The slot in the queue is already "freed" by the .get() call.
                            status = battle_manager.get_battle_status(finished_battle_id)
                            logger.debug(f"[Rank-{self.ranking_id}] Polled battle {finished_battle_id} from queue (status: {status}).")

                            while self.is_on and status in ["playing", "waiting"]:
                                sleep(BATTLE_STATUS_POLL_INTERVAL_SECONDS)
                                status = battle_manager.get_battle_status(finished_battle_id)
                            logger.debug(f"[Rank-{self.ranking_id}] Battle {finished_battle_id} (final status: {status}) finished processing. Slot available.")
                        except Empty:
                            logger.warning(f"[Rank-{self.ranking_id}] Timed out waiting for item from supposedly full queue. Inconsistency?")
                            # This case implies the queue became not-full while we were waiting, or qsize/full is tricky.
                        # No need to put the ID back. .get() removes it.
                    
                    # 5. Brief sleep
                    if not self.is_on: break # Check before sleep

                    if battles_created_in_batch > 0:
                        sleep(LOOP_POST_BATCH_SLEEP_SECONDS)
                    else:
                        # If no battles were created (e.g. queue was full, or not enough participants for a full batch but more than min)
                        # Sleep a very short time to prevent tight spinning if conditions don't change immediately.
                        sleep(LOOP_SHORT_SLEEP_SECONDS) 

                except Exception as e:
                    logger.error(
                        f"[Rank-{self.ranking_id}] Error in auto-match loop: {e}",
                        exc_info=True,
                    )
                    if not self.is_on: break # Check before sleep
                    sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY_SECONDS)
            
            logger.info(
                f"[Rank-{self.ranking_id}] Auto-match loop thread '{threading.current_thread().name}' normally ended."
            )

    def start(self) -> bool:
        # ... (rest of the class methods are mostly fine, ensure locks if they access shared state) ...
        if self.is_on:
            logger.warning(f"[Rank-{self.ranking_id}] Auto-match already running.")
            return False

        self.is_on = True
        with self._instance_lock: # Protect shared state
            self.battle_count = 0
            self._battles_since_last_refresh = 0
        
        # Initial participant load on start, in case __init__ was long ago
        self._refresh_participants() 

        logger.info(f"[Rank-{self.ranking_id}] Starting auto-match...")
        self.loop_thread = threading.Thread(
            target=self._loop, name=f"Thread-AutoMatch-Rank-{self.ranking_id}"
        )
        self.loop_thread.daemon = True
        self.loop_thread.start()
        logger.info(
            f"[Rank-{self.ranking_id}] Auto-match thread '{self.loop_thread.name}' started."
        )
        return True

    def stop(self) -> bool:
        if not self.is_on:
            logger.warning(f"[Rank-{self.ranking_id}] Auto-match not running.")
            return False

        self.is_on = False # Signal the loop to stop
        logger.info(f"[Rank-{self.ranking_id}] Stopping auto-match...")
        if self.loop_thread and self.loop_thread.is_alive():
            self.loop_thread.join(timeout=10) # Wait for the thread to finish
            if self.loop_thread.is_alive():
                logger.warning(f"[Rank-{self.ranking_id}] Auto-match thread did not stop in time.")
        logger.info(f"[Rank-{self.ranking_id}] Auto-match stopped.")
        return True

    def get_status(self) -> dict:
        with self._instance_lock: # Ensure consistent read of shared data
            participants_count = len(self.current_participants)
            battle_c = self.battle_count
        
        return {
            "ranking_id": self.ranking_id,
            "is_on": self.is_on,
            "battle_count": battle_c,
            "queue_size": self.battle_queue.qsize(), # qsize is approximate but ok for status
            "queue_max_size": self.battle_queue.maxsize,
            "thread_alive": self.loop_thread.is_alive() if self.loop_thread else False,
            "current_participants_count": participants_count,
            "battles_since_last_refresh": self._battles_since_last_refresh # May need lock if read/write are not atomic
        }

# ... (AutoMatchManager class remains largely the same, as its locking was generally okay) ...
# Ensure AutoMatchManager methods that call instance.start() or instance.get_status()
# are aware that these methods now have more internal locking.
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
