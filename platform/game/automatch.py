import time
import random
import threading
import logging
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Set
from database import (
    create_battle,
    User,
    AICode,
    get_game_stats_by_user_id,
    get_user_active_ai_code,
)
from .battle_manager import BattleManager

logger = logging.getLogger(__name__)


class AutoMatch:
    """
    自动匹配系统
    支持基于ranking_id的多队列匹配和ELO智能匹配
    """

    # 类变量 - 每个ranking_id对应一个匹配队列
    _match_queues: Dict[int, List[dict]] = defaultdict(list)

    # 线程控制
    _running: bool = False
    _match_thread: Optional[threading.Thread] = None
    _lock = threading.Lock()

    # ELO匹配参数
    ELO_RANGE_INITIAL = 100  # 初始ELO分差范围
    ELO_RANGE_INCREMENT = 50  # 每次扩大的ELO分差
    ELO_RANGE_MAX = 500  # 最大ELO分差
    MATCH_CHECK_INTERVAL = 5  # 匹配检查间隔(秒)
    QUEUE_TIMEOUT = 300  # 队列超时时间(秒)

    @classmethod
    @property
    def is_on(cls) -> bool:
        return cls._running

    @classmethod
    def add_to_queue(cls, user_id: int, ai_code_id: int, ranking_id: int) -> str:
        """将用户加入到匹配队列"""
        # 验证用户和AI代码
        user = User.query.get(user_id)

        # 如果是天梯赛，只使用活跃AI并检查用户是否有天梯统计
        if ranking_id > 0:
            # 检查用户是否有天梯统计
            stats = get_game_stats_by_user_id(user_id, ranking_id)
            if not stats:
                raise ValueError(f"用户 {user_id} 未加入排行榜 {ranking_id}")

            # 获取用户的活跃AI
            active_ai = get_user_active_ai_code(user_id)
            if not active_ai:
                raise ValueError(f"用户 {user_id} 没有设置活跃AI")

            # 使用活跃AI替代传入的AI
            ai_code = active_ai
            ai_code_id = active_ai.id
        else:
            # 普通对局使用指定的AI
            ai_code = AICode.query.get(ai_code_id)

        if not user or not ai_code:
            raise ValueError("用户或AI代码不存在")

        if ai_code.user_id != user_id:
            raise ValueError("AI代码不属于该用户")

        # 获取用户的ELO分数
        elo_score = 1200  # 默认值
        if ranking_id > 0:
            stats = get_game_stats_by_user_id(user_id, ranking_id)
            if stats:
                elo_score = stats.elo_score

        with cls._lock:
            # 初始化队列
            if ranking_id not in cls._match_queues:
                cls._match_queues[ranking_id] = []

            # 检查用户是否已在队列中
            for entry in cls._match_queues[ranking_id]:
                if entry["user_id"] == user_id:
                    # 更新现有条目
                    entry["ai_code_id"] = ai_code_id
                    entry["join_time"] = time.time()
                    return entry["queue_entry_id"]

            # 创建新的队列条目
            queue_entry_id = f"{user_id}_{int(time.time())}"
            entry = {
                "queue_entry_id": queue_entry_id,
                "user_id": user_id,
                "username": user.username,
                "ai_code_id": ai_code_id,
                "elo_score": elo_score,
                "join_time": time.time(),
                "ranking_id": ranking_id,
            }

            cls._match_queues[ranking_id].append(entry)
            logger.info(
                f"用户 {user.username}(ID: {user_id}) 加入了ranking_id={ranking_id}的匹配队列"
            )

            # 确保匹配线程在运行
            if not cls._running:
                cls.start()

            return queue_entry_id

    @classmethod
    def remove_from_queue(cls, user_id: int, ranking_id: int) -> bool:
        """从匹配队列中移除用户"""
        with cls._lock:
            queue = cls._match_queues.get(ranking_id, [])
            initial_length = len(queue)

            # 移除该用户的所有条目
            cls._match_queues[ranking_id] = [
                entry for entry in queue if entry["user_id"] != user_id
            ]

            removed = len(cls._match_queues[ranking_id]) < initial_length
            if removed:
                logger.info(
                    f"用户ID {user_id} 已从ranking_id={ranking_id}的匹配队列中移除"
                )

            return removed

    @classmethod
    def get_queue_status(cls, user_id: int, ranking_id: int) -> dict:
        """获取用户在队列中的状态"""
        with cls._lock:
            queue = cls._match_queues.get(ranking_id, [])

            # 查找用户在队列中的位置
            for idx, entry in enumerate(queue):
                if entry["user_id"] == user_id:
                    wait_time = int(time.time() - entry["join_time"])
                    return {
                        "in_queue": True,
                        "position": idx + 1,
                        "queue_length": len(queue),
                        "wait_time": wait_time,
                        "queue_entry_id": entry["queue_entry_id"],
                        "ranking_id": ranking_id,
                    }

            return {"in_queue": False}

    @classmethod
    def _match_users_by_elo(cls, ranking_id: int) -> Optional[List[dict]]:
        """
        基于ELO分数匹配用户

        使用逐步扩大ELO范围的策略，优先匹配分数接近的玩家
        """
        with cls._lock:
            queue = cls._match_queues.get(ranking_id, [])
            if len(queue) < 7:
                return None  # 队列中的人数不足以创建一场对局

            # 计算队列中每个用户的等待时间
            current_time = time.time()
            for entry in queue:
                entry["wait_time"] = current_time - entry["join_time"]

            # 按等待时间排序，优先考虑等待时间长的玩家
            sorted_queue = sorted(queue, key=lambda x: x["wait_time"], reverse=True)

            # 从等待时间最长的玩家开始尝试匹配
            for anchor_idx, anchor_entry in enumerate(sorted_queue):
                if anchor_idx + 6 >= len(sorted_queue):
                    break  # 剩余玩家不足以组成一场对局

                anchor_elo = anchor_entry["elo_score"]
                anchor_wait_time = anchor_entry["wait_time"]

                # 根据等待时间动态调整ELO范围
                # 等待时间越长，允许的ELO差异越大
                wait_factor = min(anchor_wait_time / cls.QUEUE_TIMEOUT, 1.0)
                elo_range = cls.ELO_RANGE_INITIAL + wait_factor * (
                    cls.ELO_RANGE_MAX - cls.ELO_RANGE_INITIAL
                )

                # 在ELO范围内查找匹配的玩家
                candidates = [anchor_entry]
                candidates_set = {anchor_entry["user_id"]}

                for other_entry in sorted_queue:
                    if other_entry["user_id"] in candidates_set:
                        continue

                    other_elo = other_entry["elo_score"]
                    if abs(anchor_elo - other_elo) <= elo_range:
                        candidates.append(other_entry)
                        candidates_set.add(other_entry["user_id"])

                        if len(candidates) == 7:
                            # 找到了足够的玩家，从队列中移除它们
                            for candidate in candidates:
                                cls._match_queues[ranking_id].remove(candidate)

                            logger.info(
                                f"在ranking_id={ranking_id}中成功匹配了7位玩家: {[c['username'] for c in candidates]}"
                            )
                            return candidates

            # 如果等待时间足够长的玩家数量达到7个，直接匹配它们
            long_waiting = [
                entry
                for entry in sorted_queue
                if entry["wait_time"] >= cls.QUEUE_TIMEOUT
            ]
            if len(long_waiting) >= 7:
                selected = long_waiting[:7]

                # 从队列中移除这些玩家
                for entry in selected:
                    cls._match_queues[ranking_id].remove(entry)

                logger.info(
                    f"基于等待时间在ranking_id={ranking_id}中匹配了7位玩家: {[e['username'] for e in selected]}"
                )
                return selected

            return None

    @classmethod
    def _create_match(cls, participants: List[dict], ranking_id: int) -> int:
        """
        创建一场对局

        参数:
            participants: 参与者列表，每个元素包含user_id和ai_code_id
            ranking_id: 排行榜ID

        返回:
            battle_id: 创建的对局ID
        """
        # 准备对局参与者数据
        battle_participants = [
            {"user_id": p["user_id"], "ai_code_id": p["ai_code_id"]}
            for p in participants
        ]

        # 创建对局
        battle_id = cls._db_create_battle(battle_participants, ranking_id)

        # 启动对局
        BattleManager.start_battle(battle_id)

        logger.info(f"成功创建了ranking_id={ranking_id}的对局: battle_id={battle_id}")
        return battle_id

    @classmethod
    def _db_create_battle(cls, participants: List[dict], ranking_id: int = 0) -> int:
        """
        创建对局并保存到数据库，使用 database.action 中的 centralized_create_battle 函数。
        原有的直接操作 db.session 的逻辑已移至 centralized_create_battle。
        """
        try:
            battle_id = create_battle(
                participants_details=participants,
                ranking_id=ranking_id,
            )
            if battle_id is None:
                logger.error(
                    f"create_battle failed for ranking_id {ranking_id} with participants {participants}"
                )
                raise Exception(
                    "Failed to create battle using centralized database function."
                )
            return battle_id
        except Exception as e:
            logger.error(
                f"Error calling centralized_create_battle for ranking_id {ranking_id}: {str(e)}"
            )
            raise  # 将异常向上传播，由调用方处理

    @classmethod
    def _match_loop(cls):
        """匹配主循环，持续检查各个排行榜的匹配队列"""
        logger.info("自动匹配系统已启动")

        while cls._running:
            try:
                # 获取所有活跃的排行榜ID
                ranking_ids = list(cls._match_queues.keys())

                for ranking_id in ranking_ids:
                    # 跳过普通对局(ranking_id=0)
                    if ranking_id == 0:
                        continue

                    with cls._lock:
                        queue_size = len(cls._match_queues.get(ranking_id, []))

                    # 只有当队列中有足够多的玩家时才尝试匹配
                    if queue_size >= 7:
                        matched_players = cls._match_users_by_elo(ranking_id)

                        if matched_players:
                            try:
                                # 创建对局
                                battle_id = cls._create_match(
                                    matched_players, ranking_id
                                )
                                logger.info(
                                    f"成功为ranking_id={ranking_id}创建了对局: battle_id={battle_id}"
                                )
                            except Exception as e:
                                logger.error(f"创建对局时出错: {str(e)}")
                                # 将这些玩家重新加入队列
                                with cls._lock:
                                    cls._match_queues[ranking_id].extend(
                                        matched_players
                                    )

                # 清理超时的队列条目
                cls._cleanup_queues()

                # 休眠一段时间
                time.sleep(cls.MATCH_CHECK_INTERVAL)

            except Exception as e:
                logger.error(f"匹配循环中发生错误: {str(e)}")
                time.sleep(cls.MATCH_CHECK_INTERVAL)

    @classmethod
    def _cleanup_queues(cls):
        """清理所有队列中的超时条目"""
        current_time = time.time()
        timeout_threshold = current_time - cls.QUEUE_TIMEOUT * 2  # 两倍的超时时间

        with cls._lock:
            for ranking_id, queue in list(cls._match_queues.items()):
                # 移除超时的条目
                updated_queue = [
                    entry for entry in queue if entry["join_time"] >= timeout_threshold
                ]

                removed_count = len(queue) - len(updated_queue)
                if removed_count > 0:
                    logger.info(
                        f"从ranking_id={ranking_id}的队列中移除了{removed_count}个超时条目"
                    )

                cls._match_queues[ranking_id] = updated_queue

                # 如果队列为空，移除该队列
                if not updated_queue:
                    del cls._match_queues[ranking_id]

    @classmethod
    def start(cls):
        """启动自动匹配系统"""
        with cls._lock:
            if cls._running:
                return False

            cls._running = True
            cls._match_thread = threading.Thread(target=cls._match_loop, daemon=True)
            cls._match_thread.start()
            logger.info("自动匹配系统线程已启动")
            return True

    @classmethod
    def stop(cls):
        """停止自动匹配系统"""
        with cls._lock:
            if not cls._running:
                return False

            cls._running = False
            if cls._match_thread:
                cls._match_thread.join(timeout=5.0)
                cls._match_thread = None

            logger.info("自动匹配系统已停止")
            return True

    @classmethod
    def get_status(cls) -> dict:
        """获取自动匹配系统状态"""
        with cls._lock:
            status = {"running": cls._running, "queues": {}}

            # 获取每个排行榜队列的状态
            for ranking_id, queue in cls._match_queues.items():
                status["queues"][ranking_id] = {
                    "size": len(queue),
                    "oldest_join": (
                        min([entry["join_time"] for entry in queue]) if queue else None
                    ),
                    "newest_join": (
                        max([entry["join_time"] for entry in queue]) if queue else None
                    ),
                }

            return status

    @classmethod
    def get_queue_for_ranking(cls, ranking_id: int) -> List[dict]:
        """获取指定排行榜的匹配队列（用于管理界面）"""
        with cls._lock:
            queue = cls._match_queues.get(ranking_id, [])

            # 返回队列的副本，避免外部修改
            result = []
            for entry in queue:
                entry_copy = entry.copy()
                entry_copy["wait_time"] = int(time.time() - entry["join_time"])
                result.append(entry_copy)

            return result
