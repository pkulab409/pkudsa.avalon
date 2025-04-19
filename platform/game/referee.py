"""
Module: referee.py

主裁判模块，负责协调 Avalon 游戏中各个阶段的流程。

主要功能：
- assign_roles(): 随机分配身份并初始化玩家
- pass_night_info(): 向玩家传递夜晚情报
- single_round(): 执行一轮完整的任务（包括选人、发言、公投与任务执行）
- game_loop(): 控制整局游戏的流程，判断胜负并处理刺杀环节

依赖接口：baselines.Player 必须实现指定的交互接口。
"""

import random
from baselines import Player  # 假设你写好的Player类放在player.py里

class Referee:
    def __init__(self):
        self.players = [None] + [Player(i) for i in range(1, 8)]  # 玩家编号从1到7
        self.roles = ["Merlin", "Percival", "Knight", "Knight", "Morgana", "Assassin", "Oberon"]
        self.role_distribution = {}
        self.map = [["." for _ in range(7)] for _ in range(7)]  # 简单7x7地图

    def assign_roles(self):
        random.shuffle(self.roles)
        for i in range(1, 8):
            role = self.roles[i-1]
            self.players[i].set_role_type(role)
            self.role_distribution[i] = role

    def pass_night_info(self):
        for i in range(1, 8):
            role = self.role_distribution[i]
            if role == "Merlin":
                red_info = {j: "red" for j in range(1, 8)
                            if j != i and self.role_distribution[j] in ["Morgana", "Assassin", "Oberon"]}
                self.players[i].set_role_info(red_info)
            elif role == "Percival":
                maybe_merlin = {j: "maybe_merlin" for j in range(1, 8)
                                if self.role_distribution[j] in ["Merlin", "Morgana"]}
                self.players[i].set_role_info(maybe_merlin)
            elif role in ["Morgana", "Assassin"]:
                red_mates = {j: "red" for j in range(1, 8)
                             if j != i and self.role_distribution[j] in ["Morgana", "Assassin"]}
                self.players[i].set_role_info(red_mates)
            # Oberon不看任何人

    def pass_map_info(self):
        for i in range(1, 8):
            self.players[i].pass_map(self.map)

    def single_round(self, round_num: int, leader_index: int, mission_size: int) -> bool:
        print(f"\n--- Round {round_num}, Leader: {leader_index} ---")

        # 1. 队长选人
        team = self.players[leader_index].decide_mission_member(mission_size)
        for i in range(1, 8):
            self.players[i].pass_mission_members(leader_index, team)

        # 2. 所有玩家发言
        for i in range(1, 8):
            speech = self.players[i].say()
            for j in range(1, 8):
                if i != j:
                    self.players[j].pass_message((i, speech))

        # 3. 所有玩家投票（mission_vote1）
        votes = {i: self.players[i].mission_vote1() for i in range(1, 8)}
        approve_count = sum(votes.values())
        approved = approve_count >= 4
        print(f"Voting result: {votes} -> {'Approved' if approved else 'Rejected'}")

        if not approved:
            return False  # 本轮未进行任务

        # 4. 被选中的玩家进行任务执行（mission_vote2）
        results = [self.players[i].mission_vote2() for i in team]
        fail_count = results.count(False)
        print(f"Mission executed by: {team}, result votes: {results}")
        return fail_count == 0  # 成功返回 True，否则 False

    def game_loop(self):
        self.assign_roles()
        self.pass_night_info()
        self.pass_map_info()

        leader = random.randint(1, 7)
        blue_success = 0
        red_success = 0
        round_num = 1

        while blue_success < 3 and red_success < 3:
            mission_size = [2, 3, 3, 4, 4][round_num - 1]  # 可调整
            success = self.single_round(round_num, leader, mission_size)
            if success:
                blue_success += 1
            else:
                red_success += 1
            round_num += 1
            leader = 1 if leader == 7 else leader + 1

        print(f"\nGame ended: Blue {blue_success} vs Red {red_success}")
        if blue_success >= 3:
            print("Blue wins! Now red attempts assassination.")
            merlin_guess = self.players[[i for i in range(1, 8)
                                         if self.role_distribution[i] == "Assassin"][0]].assass()
            if self.role_distribution[merlin_guess] == "Merlin":
                print(f"Assassin guessed {merlin_guess} correctly. Red wins by assassination!")
            else:
                print(f"Assassin guessed {merlin_guess} wrong. Blue wins!")
        else:
            print("Red wins by completing missions!")