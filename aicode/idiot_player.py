import random
import re
import collections
from game.avalon_game_helper import (
    askLLM,
    read_public_lib,
    read_private_lib,
    write_into_private,
)


class Player:
    def __init__(self):
        # 基本状态
        self.index = None  # 玩家编号
        self.role = None  # 角色类型
        # 地图相关
        self.map = None
        self.player_positions = {}
        self.location = None  # 当前位置
        # 历史记录
        self.memory = {
            "speech": {},  # {player_index: [messages]}
            "teams": [],  # 每轮队伍信息
            "votes": [],  # 每轮投票详情
            "mission_results": [],  # 任务成功/失败
            "movements": [],  # 移动记录
        }
        # 推理辅助
        self.suspects = set()  # 可疑玩家编号集合
        self.trusted = set()  # 信任玩家编号集合
        self.role_sight = {}  # 角色视野信息
        self.round = 0  # 当前回合数
        self.last_leader = None  # 上一轮队长
        self.last_team = []  # 上一轮队伍成员
        self.player_count = 7  # 总玩家数
        self.is_evil = False  # 是否为邪恶方
        self.target_location = None  # 目标位置
        self.speech_strategy = "neutral"  # 发言策略
        self.vote_history = {}  # 投票历史记录
        self.mission_history = {}  # 任务历史记录
        self.known_merlin = None  # 已知的梅林(刺客专用)

        # 关键地点
        self.key_locations = {
            "meeting": (4, 4),  # 会议地点
            "mission": [(2, 2), (6, 6)],  # 任务地点
        }

    def set_player_index(self, index: int):
        self.index = index
        write_into_private(f"你的编号是{index}")
        # 初始化信任集合包含自己
        self.trusted.add(self.index)

    def set_role_type(self, role_type: str):
        self.role = role_type
        self.is_evil = role_type in ["Assassin", "Morgana", "Oberon"]
        write_into_private(f"你的角色是{role_type}")

        # 根据角色设置初始策略
        if role_type == "Merlin":
            self.speech_strategy = "subtle_hint"
        elif role_type == "Percival":
            self.speech_strategy = "identify_merlin"
        elif self.is_evil:
            self.speech_strategy = "deceive"
        else:  # 普通好人
            self.speech_strategy = "cooperate"

    def pass_role_sight(self, role_sight: dict[str, int]):
        self.role_sight = role_sight
        write_into_private(f"角色视野信息: {role_sight}")

        # 根据角色处理视野信息
        if self.role == "Merlin":
            # 梅林知道所有坏人(除了莫德雷德)
            for role, player_id in role_sight.items():
                self.suspects.add(player_id)
                write_into_private(f"标记{player_id}号为可疑(角色:{role})")

        elif self.role == "Percival":
            # 派西维尔知道梅林和莫甘娜(但分不清)
            special_players = list(role_sight.values())
            self.trusted.update(special_players)
            write_into_private(f"特殊玩家: {special_players}")

        elif self.role in ["Assassin", "Morgana"]:
            # 刺客和莫甘娜知道彼此
            for role, player_id in role_sight.items():
                if player_id != self.index:
                    self.trusted.add(player_id)
                    write_into_private(f"队友: {player_id}(角色:{role})")

    def pass_map(self, map_data: list[list[str]]):
        self.map = map_data
        self.map_size = len(map_data)
        # 分析地图寻找关键路径
        self.analyze_map()

    def analyze_map(self):
        """分析地图特征，寻找关键路径和障碍"""
        if not self.map:
            return

        # 清空任务地点列表
        self.key_locations["mission"].clear()

        # 寻找任务地点
        for y in range(len(self.map)):
            for x in range(len(self.map[0])):
                if "mission" in self.map[y][x].lower():
                    self.key_locations["mission"].append((x, y))

        write_into_private(f"关键地点: {self.key_locations}")

    def pass_position_data(self, player_positions: dict[int, tuple]):
        self.player_positions = player_positions
        self.location = player_positions.get(self.index)

        # 记录移动历史
        self.memory["movements"].append(player_positions.copy())

        # 分析玩家聚集情况
        self.analyze_gathering()

    def analyze_gathering(self):
        """分析玩家聚集情况"""
        if not self.player_positions or not self.location:
            return

        # 计算每个玩家与自己的距离
        distances = {}
        for player_id, pos in self.player_positions.items():
            if player_id == self.index:
                continue
            dx = abs(pos[0] - self.location[0])
            dy = abs(pos[1] - self.location[1])
            distances[player_id] = dx + dy

        # 找出最近的玩家
        if distances:
            closest_player = min(distances.items(), key=lambda x: x[1])[0]
            write_into_private(
                f"最近的玩家是{closest_player}号，距离{distances[closest_player]}格"
            )

    def pass_message(self, content: tuple[int, str]):
        speaker, message = content
        if speaker not in self.memory["speech"]:
            self.memory["speech"][speaker] = []
        self.memory["speech"][speaker].append(message)

        # 分析发言内容
        self.analyze_speech(speaker, message)

    def analyze_speech(self, speaker: int, message: str):
        """分析玩家发言内容"""
        # 记录发言频率
        if speaker not in self.vote_history:
            self.vote_history[speaker] = {"agree": 0, "disagree": 0}

        # 关键词分析
        keywords = {
            "trust": ["信任", "好人", "可靠", "支持"],
            "suspect": ["怀疑", "坏人", "反对", "不信任"],
            "mission": ["任务", "成功", "失败", "投票"],
        }

        # 检查关键词
        for category, words in keywords.items():
            for word in words:
                if word in message:
                    write_into_private(f"{speaker}号提到关键词'{word}'")
                    if category == "suspect":
                        if speaker != self.index:
                            self.suspects.add(speaker)
                    elif category == "trust":
                        if speaker != self.index:
                            self.trusted.add(speaker)

        # 使用LLM分析发言
        if len(message) > 10:  # 只分析较长的发言
            prompt = f"""
            在阿瓦隆游戏中，{speaker}号玩家说:"{message}"。
            你是{self.index}号玩家，角色是{self.role}。
            请分析这段话的可信度和可能的阵营。
            回答要简洁，口语化。绝对不要暴露自己的身份。
            """
            analysis = askLLM(prompt)
            write_into_private(f"对{speaker}号发言的分析: {analysis}")

    def pass_mission_members(self, leader: int, members: list[int]):
        self.last_leader = leader
        self.last_team = members
        self.memory["teams"].append({"leader": leader, "members": members})

        # 记录队伍历史
        for player in members:
            if player not in self.mission_history:
                self.mission_history[player] = {"missions": 0, "fails": 0}
            self.mission_history[player]["missions"] += 1

        # 如果你是队长或队员，记录私有信息
        if self.index == leader or self.index in members:
            write_into_private(f"本轮队伍: 队长{leader}, 队员{members}")

    def decide_mission_member(self, team_size: int) -> list[int]:
        """队长选择任务队员"""
        write_into_private(f"作为队长，选择{team_size}名队员")

        # 获取所有玩家编号
        all_players = list(range(1, self.player_count + 1))

        # 善良方策略
        if not self.is_evil:
            # 优先选择信任的玩家
            trusted = list(self.trusted)
            team = []

            # 添加信任的玩家到队伍
            for player in trusted:
                if len(team) < team_size:
                    team.append(player)

            # 如果信任的玩家不足，补充未被怀疑的玩家
            neutral = [
                i
                for i in all_players
                if i not in self.suspects and i != self.index and i not in team
            ]
            while len(team) < team_size and neutral:
                team.append(neutral.pop(0))

            # 如果仍不足，随机补充剩余玩家
            remaining = [i for i in all_players if i not in team and i != self.index]
            while len(team) < team_size and remaining:
                team.append(remaining.pop(0))

            return team[:team_size]

        # 邪恶方策略
        else:
            # 优先选择队友
            trusted = list(self.trusted)
            team = []

            # 添加队友到队伍
            for player in trusted:
                if len(team) < team_size:
                    team.append(player)

            # 确保队伍中不全是队友，避免过于明显
            remaining = [i for i in all_players if i not in team and i != self.index]
            while len(team) < team_size and remaining:
                team.append(remaining.pop(0))

            return team[:team_size]

    def walk(self) -> tuple[str, ...]:
        """最简单的移动策略，确保不出错"""
        if not self.location:
            return tuple()

        x, y = self.location
        directions = [("Up", -1, 0), ("Down", 1, 0), ("Left", 0, -1), ("Right", 0, 1)]
        valid_moves = []

        # 检查每个方向是否有效
        for direction, dx, dy in directions:
            nx, ny = x + dx, y + dy
            if (
                0 <= nx < self.map_size  # 检查水平边界
                and 0 <= ny < self.map_size  # 检查垂直边界
                and (nx, ny)
                not in self.player_positions.values()  # 检查是否与其他玩家位置冲突
            ):
                valid_moves.append(direction)

        # 如果有有效移动，随机选择一个方向
        if valid_moves:
            return (random.choice(valid_moves),)

        # 如果没有有效移动，原地不动
        return tuple()

    
    def say(self) -> str:
        """发言策略"""
        # 根据角色和策略生成发言
        if self.speech_strategy == "subtle_hint" and self.role == "Merlin":
            # 梅林给出隐晦提示
            suspects = list(self.suspects)
            if suspects:
                target = random.choice(suspects)
                return f"我觉得{target}号玩家最近的行为有些可疑。"
            return "目前没有特别可疑的玩家。"

        elif self.speech_strategy == "identify_merlin" and self.role == "Percival":
            # 派西维尔尝试识别梅林
            special_players = list(self.role_sight.values())
            if len(special_players) == 2:
                return f"{special_players[0]}号和{special_players[1]}号中有一位值得特别关注。"
            return "我正在观察各位的行为。"

        elif self.speech_strategy == "deceive" and self.is_evil:
            # 邪恶方欺骗性发言
            good_players = [
                i
                for i in range(1, self.player_count + 1)
                if i not in self.trusted and i != self.index
            ]
            if good_players:
                target = random.choice(good_players)
                return f"我完全信任{target}号玩家，他看起来非常可靠。"
            return "我们需要谨慎选择队伍成员。"

        else:  # 默认合作性发言
            # 分析历史队伍
            if self.memory["teams"]:
                last_team = self.memory["teams"][-1]
                return f"上轮队伍由{last_team['leader']}号领导，队员是{last_team['members']}。"

            # 使用LLM生成更自然的发言
            prompt = f"""
            在阿瓦隆游戏中，你是{self.index}号玩家，角色是{self.role}。
            当前回合是{self.round}，已知信息:
            信任的玩家: {list(self.trusted) if self.trusted else "暂无"}
            可疑的玩家: {list(self.suspects) if self.suspects else "暂无"}
            请生成一句合适的发言，帮助好人阵营但绝对不要暴露身份。
            发言要简短，口语化。
            """
            return askLLM(prompt)

    def mission_vote1(self) -> bool:
        """对队伍提案进行投票"""
        if self.is_evil:
            # 邪恶方策略
            evil_in_team = len([p for p in self.last_team if p in self.trusted])
            if evil_in_team > 0:
                write_into_private(f"支持提案，因为队伍中有{evil_in_team}名队友")
                return True
            return random.random() < 0.3
        else:
            # 善良方策略
            suspicious_in_team = len([p for p in self.last_team if p in self.suspects])
            if suspicious_in_team > 0:
                write_into_private(
                    f"反对提案，因为队伍中有{suspicious_in_team}名可疑玩家"
                )
                return False
            # 根据历史任务结果调整策略
            if (
                len(self.memory["mission_results"]) > 0
                and not self.memory["mission_results"][-1]
            ):
                write_into_private("反对提案，因为上次任务失败")
                return False
            return True

    def mission_vote2(self) -> bool:
        """任务执行投票"""
        if self.is_evil and self.index in self.last_team:
            # 动态调整破坏概率
            good_in_team = len([p for p in self.last_team if p not in self.trusted])
            return random.random() < (0.5 + 0.1 * good_in_team)
        return True

    def assass(self) -> int:
        if self.index == 7 :
            return  1
        else :
            return self.index + 1