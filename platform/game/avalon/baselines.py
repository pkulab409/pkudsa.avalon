"""
定义《图灵阿瓦隆》游戏的基础AI(Baseline)策略。
"""

BASIC_PLAYER_CODE = """
import random

class Player:
    def __init__(self):
        # 基本状态
        self.index = None  # 玩家编号
        self.role = None   # 角色类型
        # 地图
        self.map = None
        # 历史记录
        self.memory = {
            "speech": {},         # {player_index: [messages]}
            "teams": [],          # 每轮队伍信息
            "votes": [],          # 每轮投票详情
            "mission_results": [] # 任务成功/失败
        }
        # 推理辅助
        self.suspects = set()  # 可疑玩家编号集合
    
    def set_player_index(self, index):
        self.index = index
    
    def set_role_type(self, role_type):
        self.role = role_type
    
    def pass_role_sight(self, role_sight):
        # 简单记录
        self.role_sight = role_sight
    
    def pass_map(self, map_data):
        self.map = map_data
        # 找到自己的位置
        for i in range(len(map_data)):
            for j in range(len(map_data[i])):
                if str(self.index) in map_data[i][j]:
                    self.position = (i, j)
                    break
    
    def pass_message(self, content):
        player_id, speech = content
        if player_id not in self.memory["speech"]:
            self.memory["speech"][player_id] = []
        self.memory["speech"][player_id].append(speech)
    
    def pass_mission_members(self, leader, members):
        self.last_leader = leader
        self.last_team = members
        self.memory["teams"].append({"leader": leader, "members": members})
    
    def decide_mission_member(self, member_number):
        # 简单策略：优先选自己，其他随机
        members = [self.index]
        while len(members) < member_number:
            candidate = random.randint(1, 7)
            if candidate != self.index and candidate not in members:
                members.append(candidate)
        return members
    
    def walk(self):
        # 随机移动
        directions = ["up", "down", "left", "right"]
        steps = random.randint(0, 3)
        return tuple(random.choice(directions) for _ in range(steps))
    
    def say(self):
        # 简单发言
        if self.role in ["Morgana", "Assassin", "Oberon"]:  # 红方
            return "我是好人，请信任我。"
        else:  # 蓝方
            return "我们需要找出坏人，请大家仔细观察。"
    
    def mission_vote1(self):
        # 公投策略
        if self.role in ["Morgana", "Assassin", "Oberon"]:  # 红方
            # 如果队伍中有自己或者信任的队友，支持
            if self.index in self.last_team:
                return True
            return random.random() > 0.3  # 70%概率反对
        else:  # 蓝方
            # 简单策略：如果队伍中有自己，支持
            if self.index in self.last_team:
                return True
            return random.random() > 0.3  # 70%概率反对
    
    def mission_vote2(self):
        # 任务执行投票
        if self.role in ["Morgana", "Assassin", "Oberon"]:  # 红方
            return False  # 一定破坏任务
        else:  # 蓝方
            return True   # 一定支持任务
    
    def assass(self):
        # 刺杀策略：随机选择一个非自己的玩家
        targets = [i for i in range(1, 8) if i != self.index]
        return random.choice(targets)
"""

SMART_PLAYER_CODE = """
import random
import re

class Player:
    def __init__(self):
        # 基本状态
        self.index = None  # 玩家编号
        self.role = None   # 角色类型
        # 地图
        self.map = None
        # 历史记录
        self.memory = {
            "speech": {},         # {player_index: [messages]}
            "teams": [],          # 每轮队伍信息
            "votes": [],          # 每轮投票详情
            "mission_results": [] # 任务成功/失败
        }
        # 推理辅助
        self.suspects = set()     # 可疑玩家编号集合
        self.trusted = set()      # 信任玩家编号集合
        self.round = 0            # 当前回合
        self.location = None      # 当前位置
        self.last_team = []       # 上一轮队伍
    
    def set_player_index(self, index):
        self.index = index
    
    def set_role_type(self, role_type):
        self.role = role_type
        # 判断阵营
        self.is_evil = role_type in ["Morgana", "Assassin", "Oberon"]
    
    def pass_role_sight(self, role_sight):
        self.role_sight = role_sight
        
        # 根据角色处理视野信息
        if self.role == "Merlin":
            # 梅林知道所有红方
            for role, player_idx in role_sight.items():
                if role in ["Morgana", "Assassin", "Oberon"]:
                    self.suspects.add(player_idx)
        
        elif self.role in ["Morgana", "Assassin"]:
            # 莫甘娜和刺客互相知道
            for role, player_idx in role_sight.items():
                if role in ["Morgana", "Assassin"]:
                    self.trusted.add(player_idx)
    
    def pass_map(self, map_data):
        self.map = map_data
        # 找到自己的位置
        for i in range(len(map_data)):
            for j in range(len(map_data[i])):
                if str(self.index) in map_data[i][j]:
                    self.location = (i, j)
                    break
    
    def pass_message(self, content):
        player_id, speech = content
        if player_id not in self.memory["speech"]:
            self.memory["speech"][player_id] = []
        self.memory["speech"][player_id].append(speech)
        
        # 分析发言
        if "我是好人" in speech and self.role == "Merlin":
            if player_id in self.suspects:
                # 如果梅林知道对方是坏人但对方声称是好人，增加怀疑度
                self.suspects.add(player_id)
    
    def pass_mission_members(self, leader, members):
        self.last_leader = leader
        self.last_team = members
        self.memory["teams"].append({"leader": leader, "members": members})
        
        # 分析队伍
        if self.is_evil:
            # 如果是坏人，注意队伍中的好人
            pass
        else:
            # 如果是好人，分析队伍中可能的坏人
            if len(self.memory["mission_results"]) > 0 and not self.memory["mission_results"][-1]:
                # 上一轮任务失败，增加队员怀疑度
                for member in members:
                    if member not in self.trusted:
                        self.suspects.add(member)
    
    def decide_mission_member(self, member_number):
        self.round += 1
        
        if self.is_evil:
            # 坏人策略：尽量选自己和其他坏人
            members = [self.index]
            # 添加信任的玩家（其他坏人）
            for player in self.trusted:
                if player != self.index and len(members) < member_number:
                    members.append(player)
            # 随机补充
            while len(members) < member_number:
                candidate = random.randint(1, 7)
                if candidate not in members:
                    members.append(candidate)
        else:
            # 好人策略：尽量选自己和信任的玩家，避开可疑玩家
            members = [self.index]
            # 添加信任的玩家
            for player in self.trusted:
                if player != self.index and len(members) < member_number:
                    members.append(player)
            # 添加不可疑的玩家
            players = list(range(1, 8))
            random.shuffle(players)
            for player in players:
                if player != self.index and player not in members and player not in self.suspects:
                    if len(members) < member_number:
                        members.append(player)
            # 如果还不够，随机补充
            while len(members) < member_number:
                candidate = random.randint(1, 7)
                if candidate not in members:
                    members.append(candidate)
                    
        return members
    
    def walk(self):
        # 智能移动：尝试接近特定玩家或远离可疑玩家
        directions = ["up", "down", "left", "right"]
        if self.location:
            x, y = self.location
            # 随机但保持在地图内
            valid_dirs = []
            if x > 0:
                valid_dirs.append("up")
            if x < 8:
                valid_dirs.append("down")
            if y > 0:
                valid_dirs.append("left")
            if y < 8:
                valid_dirs.append("right")
                
            if valid_dirs:
                return tuple(random.choice(valid_dirs) for _ in range(random.randint(1, 3)))
        
        # 默认随机移动
        return tuple(random.choice(directions) for _ in range(random.randint(1, 3)))
    
    def say(self):
        # 根据角色和情况生成发言
        if self.is_evil:
            if self.role == "Morgana":
                # 莫甘娜伪装成梅林
                return "我注意到一些可疑行为，但现在不方便详说。"
            else:
                return "我们需要组建可靠的队伍，我相信上一轮任务失败是因为有坏人混入。"
        else:
            if self.role == "Merlin":
                # 梅林提示但不明示
                if self.suspects:
                    suspect = random.choice(list(self.suspects))
                    return f"我认为队伍组成很重要，应该仔细观察每个人的行为。"
                else:
                    return "我们必须保持警惕，寻找破坏任务的人。"
            else:
                return "让我们专注于任务，找出那些试图破坏的人。"
    
    def mission_vote1(self):
        # 公投策略
        if self.is_evil:
            # 坏人策略
            evil_count = sum(1 for m in self.last_team if m in self.trusted or m == self.index)
            if evil_count > 0:
                # 队伍中有坏人，大概率支持
                return random.random() < 0.8
            else:
                # 队伍中没有坏人，大概率反对
                return random.random() < 0.2
        else:
            # 好人策略
            suspect_count = sum(1 for m in self.last_team if m in self.suspects)
            if suspect_count > 0:
                # 队伍中有可疑人员，大概率反对
                return random.random() < 0.2
            else:
                # 队伍中没有可疑人员，大概率支持
                return random.random() < 0.8
    
    def mission_vote2(self):
        # 任务执行投票
        if self.is_evil:
            # 第一轮可能装好人，之后一定破坏
            if self.round <= 1 and random.random() < 0.3:
                return True  # 装好人
            return False  # 破坏任务
        else:
            return True  # 蓝方一定支持任务
    
    def assass(self):
        # 智能刺杀：分析谁最可能是梅林
        # 分析发言和行为模式
        candidates = {}
        for player_id in range(1, 8):
            if player_id != self.index and player_id not in self.trusted:
                candidates[player_id] = 0
                
                # 分析此人的发言
                if player_id in self.memory["speech"]:
                    for speech in self.memory["speech"][player_id]:
                        # 发言中包含暗示或线索
                        if "可疑" in speech or "观察" in speech:
                            candidates[player_id] += 1
                
                # 分析此人的投票行为
                for team_info in self.memory["teams"]:
                    if player_id in team_info["members"] and self.index in team_info["members"]:
                        # 如果在同一队伍中，且任务失败，增加怀疑
                        candidates[player_id] -= 1
        
        # 选择怀疑度最高的玩家
        if candidates:
            target = max(candidates.items(), key=lambda x: x[1])[0]
            return target
            
        # 默认随机选择一个非自己和非信任的玩家
        targets = [i for i in range(1, 8) if i != self.index and i not in self.trusted]
        if not targets:
            targets = [i for i in range(1, 8) if i != self.index]
        return random.choice(targets)
"""

def get_all_baseline_codes():
    """获取所有预设的基准AI代码"""
    return {
        "basic_player": BASIC_PLAYER_CODE,
        "smart_player": SMART_PLAYER_CODE
    }