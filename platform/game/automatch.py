import logging
from queue import Queue
from time import sleep
from random import sample
from typing import Dict, Any, Optional, List, Tuple
import threading

from flask import Flask

# 导入数据库操作和类
from database import (
    create_battle as db_create_battle,
)
from database.models import User, AICode
from utils.battle_manager_utils import get_battle_manager

# 配置日志
logger = logging.getLogger("AutoMatch")

MAX_AUTOMATCH_PARALLEL_GAMES = 5


class AutoMatch:
    def __init__(self, app: Flask):
        # 自动对战默认关闭
        self.is_on = False
        self.battle_count = 0
        # 历史对战队列，用于限制并行对战数量，防止资源占用过高
        self.battle_queue = Queue(MAX_AUTOMATCH_PARALLEL_GAMES)
        self.loop_thread = None
        self.app = app

    def start(self):
        """启动自动对战，直到调用stop方法停止。"""
        # 如已启动，返回启动失败
        if self.is_on:
            return False

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

        def loop(app: Flask) -> bool:
            """
            后台对战循环。
            app参数用于为数据库操作设置上下文，采用了和BattleManager相同的实现方案，
            即从app被实例化开始沿app.py -> utils(引入此文件，创建AutoMatch单例并提供给下游)传递app引用，来为所有数据库操作提供上下文。
            """
            with app.app_context():
                while True:
                    # 对战生成逻辑，现为随机抽人
                    participants = sample(all_active_codes, 7)
                    participant_data = [
                        {"user_id": ai_code.user_id, "ai_code_id": ai_code.id}
                        for ai_code in participants
                    ]

                    # 如果被设置为停止(通过stop)，退出自动对战
                    if not self.is_on:
                        break

                    # 数据库操作
                    battle = db_create_battle(participant_data, status="waiting")
                    self.battle_queue.put_nowait(battle.id)
                    if self.battle_queue.full():
                        head = self.battle_queue.get_nowait()
                        # 等待，直到队头对战停止运行
                        while battle_manager.get_battle_status(head) == "playing":
                            sleep(0.5)
                    self.battle_count += 1
                    logger.info(f"启动第 {self.battle_count} 次自动对战...")
                    battle_manager.start_battle(battle.id, participant_data)

        # 创建并启动后台线程
        self.loop_thread = threading.Thread(
            target=loop, name="Thread-AutoMatch", args=(self.app,)
        )
        logger.info("自动对战线程已启动！")
        self.loop_thread.start()

        # 返回启动成功
        return True

    def stop(self) -> bool:
        """停止自动对战。"""
        if self.is_on:
            self.is_on = False
            return True
        else:
            return False

    def terminate(self):
        """终止并重置自动对战。"""
        self.is_on = False
        self.battle_count = 0
        self.battle_queue = Queue(MAX_AUTOMATCH_PARALLEL_GAMES)
        if self.loop_thread is not None:
            while self.loop_thread.is_alive():
                sleep(1)
            self.loop_thread = None
        return
