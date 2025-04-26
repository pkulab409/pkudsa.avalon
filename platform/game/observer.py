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
        self.archive = []
        self._lock = Lock()  # 添加线程锁

    def make_snapshot(self, event_type: str, event_data) -> None:
        """
        接收一次游戏事件并生成对应快照，加入内部消息队列中。

        event_type: 类型，表示事件类型，具体如下：
            Phase:Night、Global Speech、Move、Limited Speech、Public Vote、Mission。
            Event:阶段中的事件, 如Mission Fail等
            Action:指阶段中导致事件产生的玩家动作, 如Assass等
            Sign:指每轮游戏、每轮中阶段的结束标识，如"Global Speech phase complete"
            Information:过程中产生的信息, 如player_positions、票数比等
            Big_Event:Game Over、Blue Win、Red Win 1、Red Win 2
            Map:用于可视化地图变动
            Bug:suspend_game模块内的快照

        event_type (str): 显示类型：
            "Phase" -- 显示当前阶段
            "Event" -- 显示成旁白中的事件(可在聊天框中，也可单独显示)
            "Action" -- 显示成玩家对话框气泡（说话，移动，刺杀）
            "Sign" -- 显示成阶段结束标识
            "Information" -- 显示成信息提示框内的信息(给观众看)
            "Big_Event" -- 显示成游戏结束(可在聊天框中，也可单独显示)
            "Map" -- 显示成地图
            "Bug" -- 显示成bug信息

        event_data: 事件数据，数据类型语具体状况如下：
            "Phase" -- str
            "Event" -- str
            "Action" -- str
            "Sign" -- str
            "Information" -- str
            "Big_Event" -- str
            "Map" -- dict
            "Bug" -- str
        """
        
        snapshot = {
            "battle_id": self.battle_id,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())),
            "event_type": event_type, # 事件类型: referee, player{P}, move
            "event_data": event_data, # 事件数据，这里保存最后需要显示的内容
        }
        with self._lock:  # 加锁保护写操作
            self.snapshots.append(snapshot)
            self.archive.append(snapshot)

    def pop_snapshots(self) -> List[Dict[str, Any]]:
        """
        获取并清空当前的所有游戏快照，表示已被消费
        """
        with self._lock:  # 加锁保护读取 + 清空操作
            snapshots = self.snapshots
            self.snapshots = []
        return snapshots
    
    def get_archive(self) -> List[Dict[str, Any]]:
        """
        对局结束时获取本局所有快照
        """
        with self._lock:
            archive = self.archive
            return archive

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
