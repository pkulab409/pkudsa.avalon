import time
from typing import Any, Dict, List
from threading import Lock

class Observer:
    def __init__(self, battle_id):
        """
        创建一个新的观察者实例，用于记录指定游戏的快照。
        game_id: 该实例所对应的游戏对局编号。
        snapshots: List[Dict[str, Any]]：该实例所维护的消息队列，每个dict对应一次快照
        """
        self.battle_id = battle_id
        self.snapshots = []
        self._lock = Lock()  # 添加线程锁


    def make_snapshot(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """
        接收一次游戏事件并生成对应快照，加入内部消息队列中。

        event_type：事件类型，例如 "mission_vote1_result"。
        event_data：事件数据，格式任意，由调用者决定。
        """
        snapshot = {
            "battle_id": self.battle_id,
            "timestamp": time.time(),
            "event_type": event_type, # 事件类型: 系统消息/玩家行动
            "event_data": event_data, # 事件数据，这里保存最后需要显示的文字
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