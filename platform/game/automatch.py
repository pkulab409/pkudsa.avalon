import logging
from queue import Queue
from time import sleep
from random import sample
from typing import Dict, Any, Optional, List, Tuple

# 导入数据库操作和类
from database import (
    create_battle as db_create_battle,
    get_battle_by_id as db_get_battle_by_id,
    get_recent_battles as db_get_recent_battles,
    get_battle_players_for_battle as db_get_battle_players_for_battle,
    get_user_ai_codes as db_get_user_ai_codes,
)
from database.models import User, AICode
from utils.battle_manager_utils import get_battle_manager

# 配置日志
logger = logging.getLogger("AutoMatch")

MAX_AUTOMATCH_PARALLEL_GAMES = 5

class AutoMatch:
    def __init__(self):
        # 自动对战默认关闭
        self.is_on = False
        self.battle_count = 0
        # 历史对战队列，用于限制并行对战数量，防止资源占用过高
        self.battle_queue = Queue(MAX_AUTOMATCH_PARALLEL_GAMES)

    def start(self):
        """启动自动对战，直到调用stop方法停止。"""
        # 设置当前状态
        self.is_on = True
        logger.info("启动自动对战...")

        # 获取当前所有激活AI代码
        all_active_codes: list[AICode] = []
        for user in User.query.all():
            if user.get_active_ai() is not None:
                all_active_codes.append(user.get_active_ai())
        battle_manager = get_battle_manager()
        logger.info(f"加载到激活的AI代码: {all_active_codes}")

        while True:
            participants = sample(all_active_codes, 7)
            participant_data = [{'user_id': ai_code.user_id, 'ai_code_id': ai_code.id} for ai_code in participants]

            # 如果被设置为停止(通过stop)，退出自动对战
            if not self.is_on:
                return

            # 数据库操作
            battle = db_create_battle(participant_data, status="waiting")
            self.battle_queue.put_nowait(battle.id)
            if self.battle_queue.full():
                head = self.battle_queue.get()
                # 等待，直到队头对战停止运行
                while battle_manager.get_battle_status(head) == "playing":
                    sleep(0.5)
            self.battle_count += 1
            logger.info(f"启动第 {self.battle_count} 次自动对战...")
            battle_manager.start_battle(battle.id, participant_data)

    def stop(self):
        """停止自动对战。"""
        self.is_on = False
