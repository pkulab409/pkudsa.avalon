from game.avalon_game_helper import write_into_private, read_private_lib, askLLM
import random
from collections import defaultdict

# 这是一段用 DeepSeek-R1 增强的 Player.

class Player:
    def __init__(self):
        self.index = None
        self.role = None
        self.map = None
        self.memory = set()
        self.trusted_evil = set()
        self.team_history = []
        self.vote_history = defaultdict(list)
        self.mission_results = []
        self.trusted_good = set()
        self.assassination_target = None
        self.suspicion_level = defaultdict(int)
        self.players = [1, 2, 3, 4, 5, 6, 7]

    def set_player_index(self, index: int):
        self.index = index

    def set_role_type(self, role_type: str):
        self.role = role_type
        if self.role == "Merlin":
            write_into_private(f"我是梅林。")
        elif self.role in {"Oberon", "Assassin", "Morgana"}:
            write_into_private(f"我是邪恶阵营。")

    def pass_role_sight(self, role_sight: dict[str, int]):
        self.sight = role_sight
        if self.role == "Merlin":
            self.trusted_evil.update(role_sight.values())
        elif self.role == "Morgana":
            self.trusted_evil.update(role_sight.values())

    def pass_map(self, game_map):
        self.map = game_map

    def pass_message(self, content: tuple[int, str]):
        """消息处理：动态更新信任模型"""
        speaker, msg = content
        self.memory.add(content)
        
        # 分析可疑发言模式
        if "trust" in msg.lower() and "not" in msg.lower():
            mentioned_players = [int(w[1:]) for w in msg.split() if w.startswith("P")]
            for p in mentioned_players:
                self.suspicion_level[p] += 1 if p != speaker else 0
                self.suspicion_level[speaker] += 0.5  # 标记评价他人的玩家

        # 检测矛盾陈述
        if any((msg.lower().count(keyword) > 1 for keyword in ["但", "可能", "好像"])):
            self.suspicion_level[speaker] += 2

        # 记录投票模式异常
        if "approve" in msg.lower() and self.vote_history.get(speaker, [0])[-3:].count(False) > 1:
            self.suspicion_level[speaker] += 3

    def walk(self) -> tuple:
        return ("Up", "Left", "Right")

    def say(self) -> str:
        what_deepseek_says = askLLM("随便生成一句30字以内的玩7人《阿瓦隆》游戏时可能说的话。只给出话，不要别的信息。")
        return what_deepseek_says

    def _generate_smart_param(self, template: str, current_round: int) -> str:
        """根据上下文生成智能参数"""
        if "可疑成员" in template:
            evil_in_team = len([p for p in self.team_history[-1] if p in self.trusted_evil])
            return str(max(1, evil_in_team))
        if "成功任务" in template:
            success_count = sum(self.mission_results)
            return str(success_count if success_count >0 else 3)
        return str(random.randint(1, current_round))

    def pass_mission_members(self, leader: int, mission_members: list):
        self.team_history.append(mission_members)

    def decide_mission_member(self, team_size: int) -> list:
        """动态组队策略"""
        candidates = []
        current_round = len(self.team_history) + 1
        
        # 梅林策略：排除已知邪恶，优先信任好人
        if self.role == "Merlin":
            safe_players = [p for p in self.players if p not in self.trusted_evil]
            candidates = [self.index] + random.sample(safe_players, min(team_size-1, len(safe_players)))
        
        # 莫甘娜策略：混入邪恶成员，模仿好人行为
        elif self.role == "Morgana":
            evil_pool = [p for p in self.trusted_evil if p != self.index]
            if len(evil_pool) >= 1 and current_round >= 3:  # 后期增加破坏概率
                candidates = [self.index] + random.sample(evil_pool, 1)
                candidates += random.sample(self.players, team_size-len(candidates))
            else:
                candidates = random.sample(self.players, team_size)
        
        # 刺客策略：主动加入队伍伺机破坏
        elif self.role == "Assassin":
            candidates = [self.index]
            candidates += random.sample([p for p in self.players if p != self.index], team_size-1)
        
        # 默认策略：信任历史清白玩家
        else:
            clean_players = [p for p in self.players 
                           if sum(self.vote_history.get(p, [])) / max(len(self.vote_history[p]), 1) > 0.5]
            candidates = [self.index] if self.role not in ["Oberon"] else []
            candidates += random.sample(clean_players, min(team_size-len(candidates), len(clean_players)))
        
        return sorted(candidates)[:team_size]

    def mission_vote1(self) -> bool:
        """第一阶段投票策略"""
        current_team = self.team_history[-1] if self.team_history else []
        
        # 邪恶阵营：根据破坏需要决定
        if self.role in {"Morgana", "Assassin", "Oberon"}:
            evil_count = len([p for p in current_team if p in self.trusted_evil])
            if self.index in current_team:
                return True
            return random.random() < 0.7 if evil_count > 0 else random.random() < 0.3
        
        # 好人阵营：分析可疑程度
        suspicion_score = sum(self.suspicion_level[p] for p in current_team)
        team_trust = 1 - (suspicion_score / (len(current_team) * 10))
        return random.random() < (0.6 + team_trust * 0.3)

    def mission_vote2(self) -> bool:
        """任务执行阶段策略"""
        # 好人永远成功，邪恶动态破坏
        if self.role in {"Morgana", "Assassin"}:
                return False if random.random() < 0.8 else True  # 80%概率破坏
        return True

    def assass(self) -> int:
        """刺杀策略：分析梅林特征"""
        candidate_scores = defaultdict(int)
        
        # 分析特征：1) 长期支持成功队伍 2) 组队排除可疑玩家
        for i, (team, result) in enumerate(zip(self.team_history, self.mission_results)):
            for p in team:
                if result:
                    candidate_scores[p] += 2 if p != self.index else 0
                else:
                    candidate_scores[p] -= 1
        
        # 排除已知邪恶阵营
        for evil in self.trusted_evil:
            candidate_scores.pop(evil, None)
        
        # 选择最符合梅林特征的目标
        if candidate_scores:
            max_score = max(candidate_scores.values())
            candidates = [p for p, s in candidate_scores.items() if s == max_score]
            return random.choice(candidates)
        return random.choice([p for p in self.players if p != self.index])
