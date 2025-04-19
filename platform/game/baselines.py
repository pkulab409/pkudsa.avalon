# filepath: /home/eric/qhw/platform/game/baselines.py

import random
from avalon_game_helper import askLLM, read_public_lib, read_private_lib, write_into_private

class Player:
    def __init__(self):
        self.player_index = None
        self.role_type = None
        self.role_sight = {}
        self.mapdata = []
        self.messages = []
        self.mission_members = []
        self.last_leader = None
        self.last_team = []
        self.is_chosen = False

    def set_player_index(self, index: int):
        self.player_index = index

    def set_role_type(self, role_type: str):
        self.role_type = role_type

    def pass_role_sight(self, role_sight: dict[str, int]):
        self.role_sight = role_sight

    def pass_map(self, map_data: list[list[str]]):
        self.mapdata = map_data

    def pass_message(self, content: tuple[int, str]):
        self.messages.append(content)

    def pass_mission_members(self, leader: int, members: list[int]):
        self.last_leader = leader
        self.last_team = members
        self.is_chosen = self.player_index in members

    def decide_mission_member(self, member_number: int) -> list[int]:
        # 默认自己一定上，随机挑选其他人
        others = [i for i in range(1, 8) if i != self.player_index]
        random.shuffle(others)
        return [self.player_index] + others[:member_number - 1]

    def walk(self) -> tuple:
        # 随机选择最多3步方向
        directions = ['Up', 'Down', 'Left', 'Right']
        random.shuffle(directions)
        return tuple(directions[:random.randint(0, 3)])

    def say(self) -> str:
        # 默认说一句简单的话（可拓展调用 LLM）
        return f"我是玩家{self.player_index}，我支持当前任务。"

    def mission_vote1(self) -> bool:
        # 默认投赞成票
        return True

    def mission_vote2(self) -> bool:
        # 敌人投反对票，其他人投赞成票
        if self.role_type in ["Assassin", "Morgana", "Oberon"]:
            return False
        return True

    def assass(self) -> int:
        # 随机刺杀一个非自己玩家
        candidates = [i for i in range(1, 8) if i != self.player_index]
        return random.choice(candidates)
