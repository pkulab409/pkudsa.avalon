import random
import collections
import re
from game.avalon_game_helper import (
    askLLM,
    read_public_lib,
    read_private_lib,
    write_into_private,
)

MAP_SIZE = 9


class Player:
    def __init__(self):
        # 基本状态
        self.index = None  # 玩家编号
        self.role = None  # 角色类型
        self.is_evil = False  # 是否为邪恶方

        # 地图相关
        self.map = None
        self.player_positions = {}
        self.location = None
        self.map_size = 0
        self.key_locations = []  # 关键位置（如任务点）

        # 游戏状态
        self.round = 0  # 当前回合数
        self.player_count = 7  # 总玩家数
        self.mission_team_sizes = [2, 3, 3, 4, 4]  # 每轮任务队伍大小
        self.consecutive_rejections = 0  # 连续拒绝次数
        self.round_fail_size = 1  # 失败所需邪恶玩家

        # 历史记录
        self.memory = {
            "speech": {},  # {player_index: [messages]}
            "teams": [],  # 每轮队伍信息 [(leader, members), ...]
            "votes": [],  # 每轮投票详情 [(round, {player: vote}), ...]
            "mission_results": [],  # 任务成功/失败 [(round, success/fail, fail_count), ...]
            "movements": [],  # 移动记录
        }

        # 推理辅助
        self.suspects = set()  # 可疑玩家编号集合
        self.trusted = set()  # 信任玩家编号集合
        self.role_sight = {}  # 角色视野信息
        self.merlin_candidates = set()  # 梅林可能的玩家
        self.evil_probability = {}  # 每个玩家是邪恶方的概率
        self.last_leader = None  # 上一轮队长
        self.last_team = []  # 上一轮队伍成员
        self.failed_missions = []  # 失败的任务轮次
        self.successful_missions = []  # 成功的任务轮次

        # 贝叶斯推理相关
        self.vote_patterns = {}  # 记录每个玩家的投票模式
        self.mission_participation = {}  # 记录每个玩家参与任务的情况
        self.speech_analysis = {}  # 发言分析结果

        # 策略配置
        self.strategy = {
            "aggressive": False,  # 是否采取激进策略
            "deception": False,  # 是否采取欺骗策略（仅红方）
            "trust_threshold": 0.7,  # 信任阈值
            "suspect_threshold": 0.6,  # 怀疑阈值
        }

    def set_player_index(self, index: int):
        self.index = index
        # 初始化每个玩家的邪恶概率为0.43（3/7的玩家是邪恶的）
        for i in range(1, 8):
            self.evil_probability[i] = 0.43
        # 初始化投票模式和任务参与记录
        for i in range(1, 8):
            self.vote_patterns[i] = {"approve": 0, "reject": 0}
            self.mission_participation[i] = {"success": 0, "fail": 0}
            self.speech_analysis[i] = {"positive": 0, "negative": 0, "neutral": 0}

    def set_role_type(self, role_type: str):
        self.role = role_type
        write_into_private(f"我的角色是: {role_type}")

        # 设置阵营
        evil_roles = ["Assassin", "Morgana", "Oberon"]
        self.is_evil = role_type in evil_roles

        # 根据角色设置策略
        if self.is_evil:
            if role_type == "Assassin":
                self.strategy["aggressive"] = False
                self.strategy["deception"] = True
            elif role_type == "Morgana":
                self.strategy["aggressive"] = True
                self.strategy["deception"] = True
            elif role_type == "Oberon":
                self.strategy["aggressive"] = True
                self.strategy["deception"] = False
        else:  # 正义方
            if role_type == "Merlin":
                self.strategy["aggressive"] = True
            elif role_type == "Percival":
                self.strategy["aggressive"] = True
            else:  # 普通正义方
                self.strategy["aggressive"] = False

    def pass_role_sight(self, role_sight: dict[str, int]):
        self.role_sight = role_sight
        write_into_private(f"夜晚视野信息: {role_sight}")

        # 根据角色处理视野信息
        if self.role == "Merlin":
            # 梅林看到所有邪恶方（除了奥伯伦）
            for role, player_idx in role_sight.items():
                self.suspects.add(player_idx)
                self.evil_probability[player_idx] = 0.95
            write_into_private(f"作为梅林，我看到的邪恶方: {self.suspects}")

        elif self.role == "Percival":
            # 派西维尔看到梅林和莫甘娜，但无法区分
            special_players = list(role_sight.values())
            write_into_private(f"作为派西维尔，我看到的特殊角色: {special_players}")
            self.merlin_candidates = set(special_players)

        elif self.role == "Assassin":
            # 刺客看到莫甘娜
            morgana_idx = role_sight.get("Morgana")
            if morgana_idx:
                write_into_private(f"作为刺客，我看到莫甘娜是: {morgana_idx}")
                self.trusted.add(morgana_idx)
                self.evil_probability[morgana_idx] = 0.0  # 确定是邪恶方

        elif self.role == "Morgana":
            # 莫甘娜看到刺客
            assassin_idx = role_sight.get("Assassin")
            if assassin_idx:
                write_into_private(f"作为莫甘娜，我看到刺客是: {assassin_idx}")
                self.trusted.add(assassin_idx)
                self.evil_probability[assassin_idx] = 0.0  # 确定是邪恶方

    def pass_map(self, map_data: list[list[str]]):
        self.map = map_data
        self.map_size = len(map_data)

        # 识别地图上的关键位置
        self.key_locations = []
        for i in range(self.map_size):
            for j in range(self.map_size):
                if map_data[i][j] == "M":  # 任务点
                    self.key_locations.append((i, j))

    def pass_position_data(self, player_positions: dict[int, tuple]):
        self.player_positions = player_positions
        if self.index in player_positions:
            self.location = player_positions[self.index]

    def pass_message(self, content: tuple[int, str]):
        speaker_idx, message = content

        # 记录发言
        if speaker_idx not in self.memory["speech"]:
            self.memory["speech"][speaker_idx] = []
        self.memory["speech"][speaker_idx].append(message)

        # 分析发言内容
        self._analyze_speech(speaker_idx, message)

    def pass_mission_members(self, leader: int, members: list[int]):
        self.last_leader = leader
        self.last_team = members
        self.memory["teams"].append((leader, members))

        # 记录并分析队伍组成
        write_into_private(f"第{self.round}轮任务队长: {leader}, 队员: {members}")
        self._analyze_team_composition(leader, members)

    def decide_mission_member(self, team_size: int) -> list[int]:
        """选择任务队员"""
        # 获取当前轮次
        self.round = len(self.memory["teams"]) + 1

        # 动态调整策略
        if self.is_evil:
            # 邪恶方策略：在关键轮次更倾向于混入可信玩家
            if self.round in [2, 4]:
                self.strategy["deception"] = True
            else:
                self.strategy["deception"] = False
        else:
            # 正义方策略：在后期更严格地怀疑玩家
            if self.round >= 4:
                self.strategy["suspect_threshold"] = 0.5
            else:
                self.strategy["suspect_threshold"] = 0.6

        # 构建提示词，请求LLM帮助选择队员
        prompt = self._build_prompt_for_team_selection(team_size)
        response = askLLM(prompt)

        # 解析LLM回复，提取队员编号
        try:
            # 尝试直接从回复中提取数字列表
            numbers = re.findall(r"\d+", response)
            team = [int(num) for num in numbers if 1 <= int(num) <= 7][:team_size]

            # 检查并纠正队员列表
            team = self._correct_team_selection(team, team_size)
        except:
            team = self._fallback_team_selection(team_size)

        write_into_private(f"我选择的队员: {team}")
        return team

    def _correct_team_selection(self, team: list[int], team_size: int) -> list[int]:
        """检查并纠正队员列表"""
        # 去重
        team = list(set(team))

        # 移除超出范围的编号
        team = [player for player in team if 1 <= player <= 7]

        # 如果队伍数量不足，顺序递补玩家
        while len(team) < team_size:
            for i in range(1, 8):
                if i not in team:
                    team.append(i)
                    break

        # 如果队伍数量过多，裁剪到正确大小
        team = team[:team_size]

        # 确保自己在队伍中
        if self.index not in team:
            team[0] = self.index

        return team

    def _fallback_team_selection(self, team_size: int) -> list[int]:
        """备选的队员选择策略"""
        team = [self.index]  # 首先选择自己

        # 如果是邪恶方，优先选择已知的邪恶同伴
        if self.is_evil:
            for player in self.trusted:
                if player != self.index and len(team) < team_size:
                    team.append(player)

        # 选择信任度高的玩家
        trusted_players = sorted(
            [
                (i, self.evil_probability.get(i, 0.5))
                for i in range(1, 8)
                if i != self.index
            ],
            key=lambda x: x[1],
        )

        # 正义方选择信任度高的，邪恶方根据策略选择
        if not self.is_evil:
            # 选择最不可能是邪恶方的玩家
            for player, prob in trusted_players:
                if player not in team and len(team) < team_size:
                    team.append(player)
        else:
            # 邪恶方策略：混入一些可信玩家
            if self.strategy["deception"]:
                # 混入一些看起来可信的玩家
                for player, prob in trusted_players:
                    if (
                        player not in team
                        and player not in self.trusted
                        and len(team) < team_size
                    ):
                        team.append(player)
            else:
                # 随机选择其他玩家
                available = [
                    i for i in range(1, 8) if i != self.index and i not in team
                ]
                while len(team) < team_size and available:
                    team.append(random.choice(available))
                    available.remove(team[-1])

        return team[:team_size]

    def walk(self) -> tuple[str, ...]:
        """移动策略，最多走3步，终点不能与其他玩家重合"""
        if not self.map or not self.location:
            return tuple()

        x, y = self.location
        others_pos = [self.player_positions[i] for i in range(1, 8) if i != self.index]

        # 计算到最近任务点的路径
        if self.key_locations:
            target = min(
                self.key_locations, key=lambda pos: abs(pos[0] - x) + abs(pos[1] - y)
            )
            path = self._find_path_to_target(x, y, target)
            if path:
                steps = path[:3]
                # 计算终点
                cx, cy = x, y
                for move in steps:
                    if move == "Up":
                        cx -= 1
                    elif move == "Down":
                        cx += 1
                    elif move == "Left":
                        cy -= 1
                    elif move == "Right":
                        cy += 1
                if (cx, cy) not in others_pos:
                    return tuple(steps)

        # 如果没有找到路径或没有任务点，尝试接近其他玩家
        if not self.is_evil:
            trusted_players = [
                p
                for p, prob in self.evil_probability.items()
                if prob < self.strategy["trust_threshold"] and p != self.index
            ]
            if trusted_players:
                target_pos = self.player_positions[trusted_players[0]]
                path = self._find_path_to_target(x, y, target_pos)
                if path:
                    steps = path[:3]
                    cx, cy = x, y
                    for move in steps:
                        if move == "Up":
                            cx -= 1
                        elif move == "Down":
                            cx += 1
                        elif move == "Left":
                            cy -= 1
                        elif move == "Right":
                            cy += 1
                    if (cx, cy) not in others_pos:
                        return tuple(steps)
        else:
            potential_merlins = [
                p
                for p, prob in self.evil_probability.items()
                if prob < 0.3 and p != self.index
            ]
            if potential_merlins:
                target_pos = self.player_positions[potential_merlins[0]]
                path = self._find_path_to_target(x, y, target_pos)
                if path:
                    steps = path[:3]
                    cx, cy = x, y
                    for move in steps:
                        if move == "Up":
                            cx -= 1
                        elif move == "Down":
                            cx += 1
                        elif move == "Left":
                            cy -= 1
                        elif move == "Right":
                            cy += 1
                    if (cx, cy) not in others_pos:
                        return tuple(steps)

        # 原始有效移动
        valid_moves = []
        directions = [("Up", -1, 0), ("Down", 1, 0), ("Left", 0, -1), ("Right", 0, 1)]
        for direction, dx, dy in directions:
            nx, ny = x + dx, y + dy
            if (
                (0 <= nx < self.map_size)
                and (0 <= ny < self.map_size)
                and ((nx, ny) not in others_pos)
            ):
                valid_moves.append(direction)

        if valid_moves:
            # 只走一步，终点不重合
            nx, ny = x, y
            move = valid_moves[0]
            if move == "Up":
                nx -= 1
            elif move == "Down":
                nx += 1
            elif move == "Left":
                ny -= 1
            elif move == "Right":
                ny += 1
            if (nx, ny) not in others_pos:
                return (move,)

        return tuple()

    def _find_path_to_target(self, x, y, target):
        """使用BFS寻找从(x,y)到target的最短路径"""
        if not self.map:  # 无地图信息则报错
            return []

        queue = collections.deque([(x, y, [])])
        visited = set([(x, y)])
        others_pos = [
            self.player_positions[i] for i in range(1, 8) if i != self.index
        ]  # 其他玩家位置
        bfs_time = 10  # 探路层数，避免被围绕后无法逃出时报错，10与地图大小有关

        while queue and bfs_time:
            bfs_time -= 1

            cx, cy, path = queue.popleft()

            # 如果到达目标
            if (cx, cy) == target:
                return path

            # 尝试四个方向
            directions = [
                ("Up", -1, 0),
                ("Down", 1, 0),
                ("Left", 0, -1),
                ("Right", 0, 1),
            ]
            for direction, dx, dy in directions:
                nx, ny = cx + dx, cy + dy

                # 检查是否有效且未访问
                # 途径位置不得超过边界，不能回到原点，不能经过其他人
                if (
                    (0 <= nx < self.map_size)
                    and (0 <= ny < self.map_size)
                    and ((nx, ny) not in others_pos)
                    and ((nx, ny) not in visited)
                ):
                    new_path = path + [direction]
                    queue.append((nx, ny, new_path))
                    visited.add((nx, ny))

        return []  # 没有找到路径

    def say(self) -> str:
        """发言策略"""
        # 构建提示词
        prompt = self._build_prompt_for_speech()
        # 调用LLM生成发言
        try:
            response = askLLM(prompt)
            # 确保发言不超过长度限制
            if len(response) > 500:
                response = response[:497] + "..."
            return response
        except Exception as e:
            write_into_private(f"生成发言时出错: {str(e)}")
            # 备选发言
            return self._fallback_speech()

    def _fallback_speech(self) -> str:
        """备选发言策略"""
        if self.is_evil:
            # 邪恶方发言策略
            if self.strategy["deception"]:
                return f"我是{self.index}号玩家，我认为我们应该更加关注投票模式。上一轮任务{self.round-1}的结果很值得思考，我们需要找出真正的邪恶方。"
            else:
                return f"我是{self.index}号玩家，我相信目前的队伍组成是合理的。我们应该继续观察，不要轻易否决任务。"
        else:
            # 正义方发言策略
            if self.role == "Merlin":
                # 梅林谨慎提示
                suspicious = list(self.suspects)[:2]
                return f"我是{self.index}号玩家，我认为我们需要仔细观察{random.choice(suspicious)}号和{random.choice(range(1,8))}号玩家的行为，他们的投票模式很可疑。"
            else:
                return f"我是{self.index}号玩家，根据目前的情况，我认为我们需要更加谨慎地选择队伍成员。我们应该避免连续的任务失败。"

    def mission_vote1(self) -> bool:
        """对队长提案进行投票"""
        # 获取当前轮次和队伍信息
        current_round = len(self.memory["teams"])
        team = self.last_team

        # 构建提示词
        prompt = self._build_prompt_for_vote1()

        try:
            # 调用LLM进行决策
            response = askLLM(prompt)

            # 解析回复
            if (
                "同意" in response
                or "赞成" in response
                or "支持" in response
                or "true" in response.lower()
            ):
                vote_result = True
            elif (
                "反对" in response
                or "否决" in response
                or "拒绝" in response
                or "false" in response.lower()
            ):
                vote_result = False
            else:
                # 如果无法解析，使用备选策略
                vote_result = self._fallback_vote1_strategy(team)
        except:
            vote_result = self._fallback_vote1_strategy(team)

        # 记录投票结果
        write_into_private(
            f"第{current_round}轮公投: {'同意' if vote_result else '反对'}"
        )

        return vote_result

    def _fallback_vote1_strategy(self, team) -> bool:
        """备选的公投策略"""

        # 动态调整怀疑和信任阈值
        self._adjust_thresholds()
        protected_round = [2, 4]
        self.round_fail_size = 2 if self.round in protected_round else 1

        # 如果是邪恶方
        if self.is_evil:
            # 如果队伍中有足够多的邪恶方，支持
            evil_count = sum(
                1
                for p in team
                if p in self.trusted or self.evil_probability.get(p, 0.5) > 0.7
            )

            # 如果是第5轮投票，必须通过
            if self.consecutive_rejections >= 4:
                return True

            # 如果队伍中有邪恶方，有较大概率支持
            if evil_count > 0:
                return random.random() < 0.8

            # 如果队伍全是好人，有较大概率反对
            return random.random() < 0.3

        # 如果是正义方
        else:
            # 计算队伍中可疑成员数量
            suspicious_count = sum(
                1
                for p in team
                if p in self.suspects
                or self.evil_probability.get(p, 0.5)
                > self.strategy["suspect_threshold"]
            )

            # 如果是第5轮投票，必须通过
            if self.consecutive_rejections >= 4:
                return True

            # 如果队伍中没有可疑成员，支持
            if suspicious_count == 0:
                return True

            # 如果队伍中有可疑成员，根据可疑程度决定
            return suspicious_count < self.round_fail_size

    def mission_vote2(self) -> bool:
        """任务执行投票"""
        # 如果是正义方，必须投成功
        if not self.is_evil:
            return True

        # 如果是邪恶方，根据策略决定是否破坏任务
        current_round = len(self.memory["teams"])

        # 构建提示词
        prompt = self._build_prompt_for_vote2()

        try:
            # 调用LLM进行决策
            response = askLLM(prompt)

            # 解析回复
            if "破坏" in response or "失败" in response or "false" in response.lower():
                sabotage = True
            elif "成功" in response or "支持" in response or "true" in response.lower():
                sabotage = False
            else:
                # 如果无法解析，使用备选策略
                sabotage = self._fallback_vote2_strategy()
        except:
            sabotage = self._fallback_vote2_strategy()

        # 记录决策
        if sabotage:
            write_into_private(f"第{current_round}轮任务: 我选择破坏")
        else:
            write_into_private(f"第{current_round}轮任务: 我选择不破坏")

        # 返回投票结果（True为成功，False为破坏）
        return not sabotage

    def _fallback_vote2_strategy(self) -> bool:
        """备选的任务投票策略"""
        current_round = len(self.memory["teams"])
        blue_wins = len(self.successful_missions)
        red_wins = len(self.failed_missions)

        # 如果红方已经赢了2轮，有很大概率破坏
        if red_wins >= 2:
            return random.random() < 0.9

        # 如果蓝方已经赢了2轮，必须破坏
        if blue_wins >= 2:
            return True

        # 如果是关键轮次（第3轮），有较大概率破坏
        if current_round == 3:
            return random.random() < 0.8

        # 如果队伍中有多个邪恶方，可能选择不破坏以混淆视听
        evil_count = sum(1 for p in self.last_team if p in self.trusted)
        if evil_count > 1:
            return random.random() < 0.5

        # 默认有较大概率破坏
        return random.random() < 0.7

    def assass(self) -> int:
        """刺客刺杀梅林"""
        # 构建提示词
        prompt = self._build_prompt_for_assassination()

        try:
            # 调用LLM进行决策
            response = askLLM(prompt)

            # 尝试从回复中提取玩家编号
            numbers = re.findall(r"\d+", response)
            candidates = [
                int(num)
                for num in numbers
                if 1 <= int(num) <= 7 and int(num) != self.index
            ]

            if candidates:
                target = candidates[0]
            else:
                # 如果无法从回复中提取，使用备选策略
                target = self._fallback_assassination_strategy()
        except:
            target = self._fallback_assassination_strategy()

        write_into_private(f"我选择刺杀: {target}号玩家")
        return target

    def _fallback_assassination_strategy(self) -> int:
        """备选的刺杀策略"""
        # 根据各种线索推测梅林
        merlin_scores = {}

        # 初始化所有玩家的分数
        for i in range(1, 8):
            if i != self.index and i not in self.trusted:
                merlin_scores[i] = 0

        # 1. 根据邪恶概率评分（越低越可能是梅林）
        for player, prob in self.evil_probability.items():
            if player in merlin_scores:
                merlin_scores[player] += (1 - prob) * 10

        # 2. 分析投票模式
        for player in merlin_scores:
            # 梅林更可能反对有邪恶方的队伍
            approve_count = self.vote_patterns.get(player, {}).get("approve", 0)
            reject_count = self.vote_patterns.get(player, {}).get("reject", 0)
            if reject_count > approve_count:
                merlin_scores[player] += 2

        # 3. 分析发言内容
        for player in merlin_scores:
            # 梅林的发言可能更有洞察力
            positive = self.speech_analysis.get(player, {}).get("positive", 0)
            negative = self.speech_analysis.get(player, {}).get("negative", 0)
            if positive > negative:
                merlin_scores[player] += 3

        # 4. 如果是派西维尔，他可能知道梅林
        if "Percival" in [role for player, role in self.role_sight.items()]:
            percival_candidates = [
                p for p in range(1, 8) if p != self.index and p not in self.trusted
            ]
            for p in percival_candidates:
                merlin_scores[p] = merlin_scores.get(p, 0) + 2

        # 选择得分最高的玩家作为刺杀目标
        if merlin_scores:
            return max(merlin_scores.items(), key=lambda x: x[1])[0]

        # 如果没有有效的目标，随机选择一个非邪恶方玩家
        candidates = [
            i for i in range(1, 8) if i != self.index and i not in self.trusted
        ]
        return (
            random.choice(candidates)
            if candidates
            else random.choice([i for i in range(1, 8) if i != self.index])
        )

    def _adjust_thresholds(self):
        """根据游戏进程动态调整怀疑和信任阈值"""
        if self.round >= 4:
            # 后期更严格地怀疑玩家
            self.strategy["suspect_threshold"] = 0.5
            self.strategy["trust_threshold"] = 0.8
        else:
            # 前期更宽松
            self.strategy["suspect_threshold"] = 0.6
            self.strategy["trust_threshold"] = 0.7

    def _analyze_speech(self, speaker_idx: int, message: str):
        """分析发言内容"""
        # 更新发言分析统计
        if "成功" in message or "支持" in message or "信任" in message:
            self.speech_analysis[speaker_idx]["positive"] = (
                self.speech_analysis.get(speaker_idx, {}).get("positive", 0) + 1
            )
        elif "失败" in message or "反对" in message or "怀疑" in message:
            self.speech_analysis[speaker_idx]["negative"] = (
                self.speech_analysis.get(speaker_idx, {}).get("negative", 0) + 1
            )
        else:
            self.speech_analysis[speaker_idx]["neutral"] = (
                self.speech_analysis.get(speaker_idx, {}).get("neutral", 0) + 1
            )

        # 使用贝叶斯更新对玩家的评估
        # 如果发言中提到了特定玩家
        for i in range(1, 8):
            if str(i) in message:
                if "邪恶" in message or "怀疑" in message or "不信任" in message:
                    # 如果说话者指责玩家i是邪恶的
                    if speaker_idx in self.suspects:
                        # 如果说话者本身可疑，那么被指责的玩家可能是好人
                        self.evil_probability[i] = max(
                            0.1, self.evil_probability.get(i, 0.5) - 0.05
                        )
                    else:
                        # 如果说话者不可疑，那么被指责的玩家可能是邪恶的
                        self.evil_probability[i] = min(
                            0.9, self.evil_probability.get(i, 0.5) + 0.05
                        )
                elif "好人" in message or "信任" in message:
                    # 如果说话者认为玩家i是好人
                    if speaker_idx in self.suspects:
                        # 如果说话者本身可疑，那么被信任的玩家可能是邪恶的
                        self.evil_probability[i] = min(
                            0.9, self.evil_probability.get(i, 0.5) + 0.05
                        )
                    else:
                        # 如果说话者不可疑，那么被信任的玩家可能是好人
                        self.evil_probability[i] = max(
                            0.1, self.evil_probability.get(i, 0.5) - 0.05
                        )

    def _analyze_team_composition(self, leader: int, members: list[int]):
        """分析队伍组成"""
        # 更新队长的评估
        if self.is_evil:
            # 如果自己是邪恶方，评估队长选择的队伍是否有利于邪恶方
            evil_count = sum(1 for p in members if p in self.trusted or p == self.index)
            if evil_count > 0:
                # 队长选了邪恶方，可能是邪恶方或被蒙蔽的好人
                self.evil_probability[leader] = min(
                    0.9, self.evil_probability.get(leader, 0.5) + 0.1
                )
            else:
                # 队长没选邪恶方，可能是好人
                self.evil_probability[leader] = max(
                    0.1, self.evil_probability.get(leader, 0.5) - 0.1
                )
        else:
            # 如果自己是好人，评估队长选择的队伍是否有可疑成员
            suspicious_count = sum(1 for p in members if p in self.suspects)
            if suspicious_count > 0:
                # 队长选了可疑成员，队长可能是邪恶方
                self.evil_probability[leader] = min(
                    0.9, self.evil_probability.get(leader, 0.5) + 0.1
                )
            else:
                # 队长没选可疑成员，队长可能是好人
                self.evil_probability[leader] = max(
                    0.1, self.evil_probability.get(leader, 0.5) - 0.1
                )

    def _update_after_mission_result(self, success: bool, team: list[int]):
        """任务结果后更新评估"""
        if success:
            # 任务成功，队伍成员可能是好人
            for member in team:
                if member != self.index:
                    self.evil_probability[member] = max(
                        0.1, self.evil_probability.get(member, 0.5) - 0.2
                    )
            self.successful_missions.append(self.round)
        else:
            # 任务失败，队伍中可能有邪恶方
            for member in team:
                if member != self.index:
                    self.evil_probability[member] = min(
                        0.9, self.evil_probability.get(member, 0.5) + 0.1
                    )
            self.failed_missions.append(self.round)

    def _build_prompt_for_team_selection(self, team_size: int) -> str:
        """构建队员选择的提示词"""
        # 基本信息
        prompt = f"""
        【任务背景】
        你是阿瓦隆游戏中的{self.index}号玩家，角色是{self.role}。
        现在是第{self.round}轮任务，你需要选择{team_size}名队员执行任务。
        
        【你的身份信息】
        你属于{'邪恶方' if self.is_evil else '正义方'}。
        """

        # 添加视野信息
        if self.role_sight:
            prompt += f"\n【你的夜晚视野】\n{self.role_sight}\n"

        # 添加历史信息
        if self.memory["teams"]:
            prompt += "\n【历史队伍组成】\n"
            for i, (leader, members) in enumerate(self.memory["teams"]):
                prompt += f"第{i+1}轮: 队长{leader}号，队员{members}\n"

        if self.memory["mission_results"]:
            prompt += "\n【历史任务结果】\n"
            for i, (success, fail_count) in enumerate(self.memory["mission_results"]):
                result = "成功" if success else f"失败（失败票数: {fail_count}）"
                prompt += f"第{i+1}轮: {result}\n"

        # 添加玩家评估
        prompt += "\n【玩家评估】\n"
        for player, prob in self.evil_probability.items():
            if player != self.index:
                status = "可疑" if prob > 0.6 else "中立" if prob > 0.4 else "可信"
                prompt += f"{player}号玩家: {status}(邪恶概率: {prob:.2f})\n"

        # 添加决策要求
        if self.is_evil:
            prompt += f"""
            【决策要求】
            作为邪恶方，你需要选择一个能够让任务失败的队伍，本次任务失败需要{self.round_fail_size}个邪恶方在队伍中。
            可以考虑选择自己和其他邪恶方成员，但是尽量不要选择大家一致怀疑的人，在尽可能在避免怀疑的前提下保证任务失败。
            请不要说其他话，直接返回{team_size}个玩家编号，用逗号分隔，例如回复“1，2，3”，确保包含自己({self.index}号)。
            """
        else:
            prompt += f"""
            【决策要求】
            作为正义方，你需要选择一个能够让任务成功的队伍，本次任务如果有{self.round_fail_size}个邪恶方在队伍中就会失败。
            应该选择你最信任的玩家，避免选择可疑的玩家。
            请不要说其他话，直接返回{team_size}个玩家编号，用逗号分隔，例如回复“1，2，3”，确保包含自己({self.index}号)。
            """

        return prompt

    def _build_prompt_for_speech(self) -> str:
        """构建发言的提示词"""
        # 基本信息
        prompt = f"""
        【任务背景】
        你是阿瓦隆游戏中的{self.index}号玩家，角色是{self.role}。
        现在是第{self.round}轮任务，轮到你发言。
        
        【你的身份信息】
        你属于{'邪恶方' if self.is_evil else '正义方'}。
        """

        # 添加视野信息
        if self.role_sight:
            prompt += f"\n【你的夜晚视野】\n{self.role_sight}\n"

        # 添加历史信息
        if self.memory["teams"]:
            prompt += "\n【历史队伍组成】\n"
            for i, (leader, members) in enumerate(self.memory["teams"]):
                prompt += f"第{i+1}轮: 队长{leader}号，队员{members}\n"

        if self.memory["mission_results"]:
            prompt += "\n【历史任务结果】\n"
            for i, result in enumerate(self.memory["mission_results"]):
                prompt += f"第{i+1}轮: {'成功' if result else '失败'}\n"

        # 添加玩家评估
        prompt += "\n【玩家评估】\n"
        for player, prob in self.evil_probability.items():
            if player != self.index:
                status = "可疑" if prob > 0.6 else "中立" if prob > 0.4 else "可信"
                prompt += f"{player}号玩家: {status}\n"

        # 添加其他玩家的发言
        if self.memory["speech"]:
            prompt += "\n【其他玩家的发言】\n"
            for player, speeches in self.memory["speech"].items():
                if player != self.index and speeches:
                    prompt += f"{player}号玩家最近说: {speeches[-1][:100]}...\n"

        # 添加决策要求
        if self.is_evil:
            if self.role == "Morgana":
                prompt += """
                【决策要求】
                作为莫甘娜，你应该尝试伪装成梅林，发表看似有洞察力的言论。
                可以适当指责其他玩家，特别是真正的好人，转移怀疑。
                不要暴露自己的身份，也不要暴露其他邪恶方成员。
                请直接生成一段严格小于100字的发言,不许附带任何其他的文字。
                """
            elif self.role == "Assassin":
                prompt += """
                【决策要求】
                作为刺客，你需要通过发言收集信息，找出谁可能是梅林。
                可以伪装成好人，表现出对任务成功的关心。
                观察其他玩家的反应，特别是那些表现出对邪恶方了解的玩家。
                请直接生成一段严格小于100字的发言,不许附带任何其他的文字。
                """
            else:  # Oberon
                prompt += """
                【决策要求】
                作为奥伯伦，你不知道其他邪恶方是谁，他们也不知道你是谁。
                你可以表现得像一个困惑的好人，或者尝试通过发言找出其他邪恶方。
                不要过于明显地破坏任务，但要确保正义方不会胜利。
                请直接生成一段严格小于100字的发言,不许附带任何其他的文字。
                """
        else:
            if self.role == "Merlin":
                prompt += """
                【决策要求】
                作为梅林，你知道谁是邪恶方（除了奥伯伦）。
                你需要引导好人找出邪恶方，但不能过于明显地暴露自己的身份，否则会被刺客刺杀。
                可以通过暗示和间接方式提供信息，让其他好人信任你。
                请直接生成一段严格小于100字的发言,不许附带任何其他的文字。
                """
            elif self.role == "Percival":
                prompt += """
                【决策要求】
                作为派西维尔，你知道谁可能是梅林（但也可能是莫甘娜）。
                你需要保护真正的梅林，同时帮助好人找出邪恶方。
                可以表现出对某些玩家的信任，但不要明确指出谁是梅林。
                请直接生成一段严格小于100字的发言,不许附带任何其他的文字。
                """
            else:  # 普通好人
                prompt += """
                【决策要求】
                作为普通好人，你需要通过观察和分析找出邪恶方。
                关注任务失败的情况，分析投票模式和发言内容。
                表达你的怀疑和信任，但要基于逻辑和观察。
                请直接生成一段严格小于100字的发言,不许附带任何其他的文字。
                """

        return prompt

    def _build_prompt_for_vote1(self) -> str:
        """构建公投的提示词"""
        # 基本信息
        prompt = f"""
        【任务背景】
        你是阿瓦隆游戏中的{self.index}号玩家，角色是{self.role}。
        现在是第{self.round}轮任务，队长{self.last_leader}号选择了队员{self.last_team}。
        你需要决定是否同意这个队伍执行任务。
        
        【你的身份信息】
        你属于{'邪恶方' if self.is_evil else '正义方'}。
        """

        # 添加视野信息
        if self.role_sight:
            prompt += f"\n【你的夜晚视野】\n{self.role_sight}\n"

        # 添加历史信息
        if self.memory["teams"]:
            prompt += "\n【历史队伍组成】\n"
            for i, (leader, members) in enumerate(self.memory["teams"]):
                prompt += f"第{i+1}轮: 队长{leader}号，队员{members}\n"

        if self.memory["mission_results"]:
            prompt += "\n【历史任务结果】\n"
            for i, result in enumerate(self.memory["mission_results"]):
                prompt += f"第{i+1}轮: {'成功' if result else '失败'}\n"

        # 添加玩家评估
        prompt += "\n【玩家评估】\n"
        for player, prob in self.evil_probability.items():
            if player != self.index:
                status = (
                    "非常可疑"
                    if prob > 0.8
                    else "可疑" if prob > 0.6 else "中立" if prob > 0.4 else "可信"
                )
                prompt += f"{player}号玩家: {status}\n"

        # 添加决策要求
        if self.is_evil:
            prompt += f"""
            【决策要求】
            作为邪恶方，你需要评估这个队伍是否有利于你们。
            如果队伍中有你或其他邪恶方成员，你必须同意。
            如果队伍中可疑的人很多，你必须同意。
            在其他情况下你可以综合考虑进行抉择。
            如果连续4次投票都被否决，第5次会强制通过，需要考虑战略价值。
            当前连续否决次数: {self.consecutive_rejections}
            请直接回答"同意"或"反对"。
            """
        else:
            prompt += f"""
            【决策要求】
            作为正义方，你需要评估这个队伍是否可信。
            如果队伍中可疑程度很高，你需要否定这次任务。
            这次任务有{self.round_fail_size}个邪恶方就会失败，当可疑程度较小时，你需要衡量你的选择。
            如果连续4次投票都被否决，第5次会强制通过，需要考虑战略价值。
            当前连续否决次数: {self.consecutive_rejections}
            请直接回答"同意"或"反对"。
            """
        return prompt

    def _build_prompt_for_vote2(self) -> str:
        """构建任务投票的提示词"""
        # 如果是好人，不需要提示词，必须投成功
        if not self.is_evil:
            return "作为好人，你必须投成功。请回答'成功'。"

        # 基本信息
        prompt = f"""
        【任务背景】
        你是阿瓦隆游戏中的{self.index}号玩家，角色是{self.role}。
        现在是第{self.round}轮任务，你被选为队员参与任务。
        作为邪恶方，你可以选择让任务成功或失败。
        
        【当前游戏状态】
        蓝方胜利次数: {len(self.successful_missions)}
        红方胜利次数: {len(self.failed_missions)}
        """

        # 添加队伍信息
        prompt += (
            f"\n【当前队伍】\n队长: {self.last_leader}号\n队员: {self.last_team}\n"
        )

        # 添加其他邪恶方信息
        if self.trusted:
            prompt += f"\n【已知的其他邪恶方】\n{list(self.trusted)}\n"

        # 添加决策要求
        prompt += """
        【决策要求】
        作为邪恶方，你需要决定是否破坏任务。
        如果破坏，任务将失败，红方获得一分。
        如果不破坏，任务将成功，蓝方获得一分。
        
        考虑因素:
        1. 当前的比分状况
        2. 队伍中是否有其他邪恶方成员
        3. 是否需要隐藏身份
        4. 战略价值
        
        请直接回答"破坏"或"成功"。
        """

        return prompt

    def _build_prompt_for_assassination(self) -> str:
        """构建刺杀的提示词"""
        # 基本信息
        prompt = f"""
        【任务背景】
        你是阿瓦隆游戏中的{self.index}号刺客。
        游戏已经结束，红方失败，现在你有一次刺杀梅林的机会。
        如果刺杀成功，红方将逆转获胜。
        
        【游戏历史】
        """

        # 添加队伍历史
        if self.memory["teams"]:
            prompt += "\n【历史队伍组成】\n"
            for i, (leader, members) in enumerate(self.memory["teams"]):
                prompt += f"第{i+1}轮: 队长{leader}号，队员{members}\n"

        # 添加任务结果
        if self.memory["mission_results"]:
            prompt += "\n【历史任务结果】\n"
            for i, result in enumerate(self.memory["mission_results"]):
                prompt += f"第{i+1}轮: {'成功' if result else '失败'}\n"

        # 添加投票历史
        if self.memory["votes"]:
            prompt += "\n【投票历史】\n"
            for i, votes in enumerate(self.memory["votes"]):
                prompt += f"第{i+1}轮: {votes}\n"

        # 添加发言分析
        prompt += "\n【发言分析】\n"
        for player, speeches in self.memory["speech"].items():
            if player != self.index and speeches:
                prompt += f"{player}号玩家的关键发言: {speeches[-1][:100]}...\n"

        # 添加玩家评估
        prompt += "\n【玩家评估】\n"
        for player, prob in self.evil_probability.items():
            if player != self.index and player not in self.trusted:
                status = "可疑" if prob > 0.6 else "中立" if prob > 0.4 else "可信"
                prompt += (
                    f"{player}号玩家: {status} (梅林可能性: {(1-prob)*100:.1f}%)\n"
                )

        # 添加决策要求
        prompt += """
        【决策要求】
        分析所有信息，找出最可能是梅林的玩家。
        梅林了解所有邪恶方的身份，可能在发言中暗示或引导好人。
        观察哪些玩家表现出对邪恶方的了解，或者在关键时刻做出正确决策。
        
        请直接回答你认为是梅林的玩家编号。
        """

        return prompt
