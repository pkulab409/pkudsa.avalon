#!/usr/bin/env python
"""observer 模块：
游戏观察者实例，用于记录指定游戏的快照。
预留快照调用的接口，用于前端的游戏可视化。
"""


import time
from typing import Any, Dict, List
from threading import Lock
import json
import os
from config.config import Config

PLAYER_COUNT = 7
MAP_SIZE = 9


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

        event_type (str) -- event_data 对应关系

            "GameStart"
                -- str battle_id

            "GameEnd"
                -- str battle_id

            "RoleAssign"
                -- dict 角色分配字典

            "NightStart"
                -- str, "Starting Night Phase."

            "NightEnd"
                -- str, "--- Night phase complete ---"

            "RoundStart"
                -- int 轮数

            "RoundEnd"
                -- int 轮数

            "TeamPropose"
                -- list, 组员index

            "PublicSpeech"
                -- tuple(int, str),
                    int: 玩家编号
                    str: 发言内容

            "PrivateSpeech"
                -- tuple(int, str),
                    int: 玩家编号
                    str: 发言内容

            "Positions"
                -- dict 玩家位置

            "DefaultPositions"
                -- dict 玩家初始位置

            "Move"
                -- tuple(int, list),
                    int: 0表示开始,8表示结束,其他数字对应玩家编号
                    list: [valid_moves, new_pos]

            "PublicVote"
                -- tuple(int, str),
                    int: 0表示开始,8表示结束,其他数字对应玩家编号
                    str: 'Approve' if vote else 'Reject'

            "PublicVoteResult"
                -- list[int,int], 支持票数和反对票数

            "MissionRejected"
                -- str, "Team Rejected."

            "Leader"
                -- int, 新队长编号

            "MissionApproved"
                -- list[int, list]
                    int: 轮数
                    list: mission_members

            "MissionForceExecute"
                -- str, "Maximum vote rounds reached. Forcing mission execution with last proposed team."

            "MissionVote"
                -- dict[int, bool]

            "MissionResult"
                -- tuple[int,str],
                    int: 当前轮数
                    str: "Success" or "Fail"

            "ScoreBoard"
                -- list[int, int]
                    蓝：红

            "FinalScore"
                -- list[int, int]
                    蓝：红

            "GameResult"
                -- tuple[str, str]
                    队伍，原因

            "Assass"
                -- list: [assassin_id, target_id, target_role, ('Success' if success else 'Fail')]


            "Information"
                -- 显示成信息提示框内的信息(给观众看)

            "Bug"
                -- 显示成bug信息


        """

        snapshot = {
            "battle_id": self.battle_id,
            "player_count": PLAYER_COUNT,
            "map_size": MAP_SIZE,
            "timestamp": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(time.time())
            ),
            "event_type": event_type,  # 事件类型: referee, player{P}, move
            "event_data": event_data,  # 事件数据，这里保存最后需要显示的内容
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

    def snapshots_to_json(self) -> None:
        """
        将当前的快照列表 snapshots 保存到 JSON 文件中，路径与 visualizer.py 保持一致。
        """
        file_path = os.path.join(
            Config._yaml_config.get("DATA_DIR", "./data"),
            f"game_{self.battle_id}_archive.json",
        )
        print(f"尝试写入文件到: {file_path}")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with self._lock:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.archive, f, ensure_ascii=False, indent=4)
            print(f"文件写入完成: {os.path.exists(file_path)}")
