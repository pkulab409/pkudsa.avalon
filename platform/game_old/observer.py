#!/usr/bin/env python
'''observer 模块：
游戏观察者实例，用于记录指定游戏的快照。
预留快照调用的接口，用于前端的游戏可视化。
'''


import time
from typing import Any, Dict, List
from threading import Lock


class Observer:
    def __init__(self, battle_id):
        """
        创建一个新的观察者实例，用于记录指定游戏的快照。
        game_id: 该实例所对应的游戏对局编号。
        snapshots: List[Dict[str, str]]：该实例所维护的消息队列，每个dict对应一次快照
        """
        self.battle_id = battle_id
        self.snapshots = []
        self._lock = Lock()  # 添加线程锁

    def make_snapshot(self, event_type: str, event_data) -> None:
        """
        接收一次游戏事件并生成对应快照，加入内部消息队列中。

        event_type (str): 显示类型：
            "referee" -- 显示成旁白
            "player1" ~ "player7" -- 显示成玩家对话框气泡
            "move" -- 显示成地图
        event_data: 事件数据，数据类型语具体状况如下：
            * 如果 event_type 是 "referee"： str 类型，表示旁白
            * 如果 event_type 是 "player{P}"： str 类型，表示玩家行为
            * 如果 event_type 是 "move"： dict 类型，表示不同玩家目前的位置
                例： {1: (1, 3), 2: (2, 5), 3: (4, 7), ...}
        """
        snapshot = {
            "battle_id": self.battle_id,
            "timestamp": time.time(),
            "event_type": event_type, # 事件类型: referee, player{P}, move
            "event_data": event_data, # 事件数据，这里保存最后需要显示的内容
        }
        with self._lock:  # 加锁保护写操作
            self.snapshots.append(snapshot)

    def pop_snapshots(self) -> List[Dict[str, Any]]:
        """
        获取并清空当前的所有游戏快照，表示已被消费
        """
        with self._lock:  # 加锁保护读取 + 清空操作
            snapshots = self.snapshots
            self.snapshots = []
        return snapshots
    
    # 下面的两个函数不需要用到
    def get_snapshots(self) -> List[Dict[str, Any]]:
        """
        获取当前已记录的所有游戏快照，读取时不删除。
        返回一个按时间顺序排列的列表。
        """
        return self.snapshots

    def get_latest_snapshot(self) -> Dict[str, Any]:
        """
        获取最近的一条游戏快照记录。如果尚无记录，则返回空字典。
        """
        return self.snapshots[-1] if self.snapshots else {}
