import random
import re
from game.avalon_game_helper import (
    askLLM, read_public_lib,
    read_private_lib, write_into_private
)


class Player:
    def __init__(self):
        self.index = None
        self.role = None
        self.role_info = {}
        self.map = None
        self.memory = {
            "speech": {},         # {player_index: [utterance1, utterance2, ...]}
            "votes": [],          # [(operators, {pid: vote})]
            "mission_results": [] # [True, False, ...]
        }
        self.teammates = set()   # 推测的可信玩家编号
        self.suspects = set()    # 推测的红方编号

    def set_player_index(self, index: int):
        self.index = index

    def set_role_type(self, role_type: str):
        self.role = role_type

    def pass_role_sight(self, role_sight: dict[str, int]):
        '''
        该函数是系统在夜晚阶段传入的“我方可识别敌方信息”，
        例如：梅林会得到“红方玩家编号”的列表或字典。
        注意：
        1.红方角色根本不会获得任何此类信息，不要误用。
        2.对于派西维尔，看到应该是梅林和莫甘娜的混合视图，
        不应该加入`suspect`
        '''
        self.sight = role_sight
        self.suspects.update(role_sight.values())

    def pass_map(self, map_data: list[list[str]]):
        self.map = map_data

    def pass_message(self, content: tuple[int, str]):
        player_id, speech = content
        self.memory["speech"].setdefault(player_id, []).append(speech)
        if "任务失败" in speech or "破坏" in speech:
            self.suspects.add(player_id)  # 简化的推理：谁喊破坏谁可疑

    def decide_mission_member(self, member_number: int) -> list[int]:
        """
        选择任务队员：
        - 自己一定上
        - 优先选择不在嫌疑列表的人
        """
        candidates = [i for i in range(1, 8) if i != self.index and i not in self.suspects]
        random.shuffle(candidates)
        chosen = [self.index] + candidates[:member_number - 1]
        return chosen[:member_number]

    def pass_mission_members(self, leader: int, members: list[int]):
        self.last_leader = leader # 储存本轮的队长编号
        self.last_team = members # 储存本轮将执行任务的队员编号列表
        self.is_chosen = self.index in self.last_team # 是否被选为任务执行者
        self.memory.setdefault("team_history", []).append({
            "round": len(self.memory.get("team_history", [])) + 1,
            "leader": self.last_leader,
            "team": self.last_team.copy(),
            "included_me": self.is_chosen
        })
        # 记录历史队伍和队长，用于后续的推理

    def walk(self) -> tuple:
        """
        TODO 现在就是随便走
        """
        return "Left", "Up", "Right"

    def say(self) -> str:
        return "这轮信息太混乱，我还在观察。"

    def mission_vote1(self) -> bool:
        """
        投票策略：
        - 如果队伍中全是可信玩家则通过
        - 否则按概率通过
        """
        if all(pid not in self.suspects for pid in self.last_team):
            return True
        return random.random() > 0.3

    def mission_vote2(self) -> bool:
        """
        执行任务投票：
        - 红方一定投False（破坏）
        - 蓝方一定True（成功）
        """
        return self.role not in ["Morgana", "Assassin", "Oberon"]

    def assass(self) -> int:
        """刺杀"""
        possible_targets = [i for i in range(1, 6) if i != self.player_id]
        return random.choice(possible_targets)