import uuid
import time
from datetime import datetime
from flask import current_app
from database.models import db, User, AiCode, Battle, BattleParticipant
from game.battle_manager import BattleManager


class RankingMatchmaker:
    """
    天梯匹配系统
    负责管理玩家匹配队列和创建天梯对局
    """

    # 匹配队列 {ranking_id: {queue_id: {user_id, ai_code_id, join_time}}}
    queues = {}

    # 匹配进程是否正在运行
    matcher_running = False

    @classmethod
    def add_to_queue(cls, user_id, ai_code_id, ranking_id):
        """
        将用户添加到匹配队列

        参数:
            user_id: 用户ID
            ai_code_id: 用户选择的AI代码ID
            ranking_id: 排行榜ID

        返回:
            包含队列ID的字典
        """
        # 验证用户和AI代码
        user = User.query.get(user_id)
        ai_code = AiCode.query.get(ai_code_id)

        if not user or not ai_code:
            raise ValueError("用户或AI代码不存在")

        if ai_code.user_id != user_id:
            raise ValueError("AI代码不属于该用户")

        # 初始化对应排行榜的队列
        if ranking_id not in cls.queues:
            cls.queues[ranking_id] = {}

        # 检查用户是否已在该排行榜的队列中
        for queue_id, entry in cls.queues[ranking_id].items():
            if entry["user_id"] == user_id:
                # 更新现有条目
                entry["ai_code_id"] = ai_code_id
                entry["join_time"] = time.time()
                return {"queue_id": queue_id}

        # 创建新的队列条目
        queue_id = str(uuid.uuid4())
        cls.queues[ranking_id][queue_id] = {
            "user_id": user_id,
            "ai_code_id": ai_code_id,
            "join_time": time.time(),
        }

        # 检查是否有足够的玩家进行匹配
        cls.try_match(ranking_id)

        return {"queue_id": queue_id}

    @classmethod
    def remove_from_queue(cls, queue_id, ranking_id):
        """从队列中移除用户"""
        if ranking_id in cls.queues and queue_id in cls.queues[ranking_id]:
            del cls.queues[ranking_id][queue_id]
            return True
        return False

    @classmethod
    def try_match(cls, ranking_id):
        """
        尝试为指定排行榜匹配玩家
        当队列中有至少7名玩家时创建对局
        """
        if ranking_id not in cls.queues:
            return

        queue = cls.queues[ranking_id]
        if len(queue) >= 7:
            # 按加入时间排序
            sorted_entries = sorted(queue.items(), key=lambda x: x[1]["join_time"])

            # 选择前7名玩家
            selected_entries = sorted_entries[:7]

            # 创建参与者列表
            participants = [
                {"user_id": entry[1]["user_id"], "ai_code_id": entry[1]["ai_code_id"]}
                for entry in selected_entries
            ]

            try:
                # 创建天梯对局
                battle_id = cls.create_ranking_battle(participants, ranking_id)

                # 从队列中移除已匹配的玩家
                for entry in selected_entries:
                    queue_id = entry[0]
                    del queue[queue_id]

                current_app.logger.info(
                    f"天梯对局创建成功: battle_id={battle_id}, ranking_id={ranking_id}"
                )
                return battle_id
            except Exception as e:
                current_app.logger.error(f"创建天梯对局失败: {str(e)}")
                raise

    @classmethod
    def create_ranking_battle(cls, participants, ranking_id):
        """
        创建天梯对局

        参数:
            participants: 参与者列表
            ranking_id: 排行榜ID

        返回:
            创建的对局ID
        """
        # 调用现有的对局创建逻辑，但添加ranking_id参数
        battle_id = db_create_battle(participants, ranking_id=ranking_id)

        # 启动对局
        BattleManager.start_battle(battle_id)

        return battle_id


# 修改现有的db_create_battle函数，此函数可能在其他地方定义
# 这里提供一个参考实现
def db_create_battle(participants, ranking_id=0):
    """
    在数据库中创建对局记录

    参数:
        participants: 参与者列表
        ranking_id: 排行榜ID，默认为0（普通对局）

    返回:
        创建的对局ID
    """
    # 创建对局记录
    battle = Battle(status="created", created_at=datetime.now(), ranking_id=ranking_id)
    db.session.add(battle)
    db.session.flush()  # 获取battle.id

    # 创建参与者记录
    for i, p in enumerate(participants):
        participant = BattleParticipant(
            battle_id=battle.id,
            user_id=p["user_id"],
            ai_code_id=p["ai_code_id"],
            position=i,  # 位置从0开始
        )
        db.session.add(participant)

    db.session.commit()
    return battle.id
