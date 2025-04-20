import random
import re
from avalon_game_helper import askLLM, read_public_lib, read_private_lib, write_into_private

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
        self.trusted = set()   # 信任玩家编号集合
        self.role_sight = {}   # 角色视野信息
        self.round = 0         # 当前回合数
        self.last_leader = None  # 上一轮队长
        self.last_team = []      # 上一轮队伍成员
        self.player_count = 7    # 总玩家数
        self.is_evil = False     # 是否为邪恶方
        self.location = None     # 当前位置
        
    def set_player_index(self, index: int):
        """设置玩家编号"""
        self.index = index
        
    def set_role_type(self, role_type: str):
        """设置角色类型"""
        self.role = role_type
        # 判断是否为邪恶方
        if role_type in ["Morgana", "Assassin", "Oberon"]:
            self.is_evil = True
        try:
            # 记录角色初始信息到私有库
            write_into_private(f"role: {role_type}, index: {self.index}")
        except Exception as e:
            pass  # 忽略错误
            
    def pass_role_sight(self, role_sight: dict[str, int]):
        """传递角色视野信息"""
        self.role_sight = role_sight
        try:
            # 记录角色视野信息到私有库
            write_into_private(f"role_sight: {role_sight}")
            
            # 如果是好人方，把看到的邪恶角色加入怀疑名单
            if not self.is_evil and self.role == "Merlin":
                for role, player_idx in role_sight.items():
                    if role in ["Morgana", "Assassin"]:
                        self.suspects.add(player_idx)
            
            # 如果是邪恶方，把看到的其他邪恶角色加入信任名单
            if self.is_evil and self.role != "Oberon":
                for role, player_idx in role_sight.items():
                    if role in ["Morgana", "Assassin", "Oberon"]:
                        self.trusted.add(player_idx)
        except Exception as e:
            pass
            
    def pass_map(self, map_data: list[list[str]]):
        """传递地图数据"""
        self.map = map_data
        # 找到自己的初始位置
        for i in range(len(map_data)):
            for j in range(len(map_data[i])):
                if str(self.index) in map_data[i][j]:
                    self.location = (i, j)
                    break
        
    def pass_message(self, content: tuple[int, str]):
        """传递其他玩家发言"""
        speaker, message = content
        # 初始化该玩家的发言列表（如果不存在）
        if speaker not in self.memory["speech"]:
            self.memory["speech"][speaker] = []
        # 添加发言
        self.memory["speech"][speaker].append(message)
        
        # 分析发言内容，更新怀疑和信任
        try:
            # 检查发言中是否有直接指认梅林的内容
            if "梅林" in message or "merlin" in message.lower():
                match = re.search(r'(\d+)\s*[是号].*梅林', message)
                if match:
                    accused = int(match.group(1))
                    if not self.is_evil:
                        # 如果好人方，被指认为梅林的玩家可信度降低
                        if self.role == "Merlin" and accused == self.index:
                            self.suspects.add(speaker)  # 将指认者加入怀疑名单
                        elif accused != self.index:
                            # 权衡是否相信指认
                            if speaker not in self.suspects:
                                self.suspects.add(accused)
                    else:
                        # 如果邪恶方，记录被指认为梅林的玩家
                        write_into_private(f"possible_merlin: {accused}, mentioned_by: {speaker}")
        except Exception as e:
            pass
            
    def pass_mission_members(self, leader: int, members: list[int]):
        """告知任务队长和队员"""
        self.last_leader = leader
        self.last_team = members
        
        # 记录队伍信息
        self.memory["teams"].append({"leader": leader, "members": members})
        
        # 分析队伍组成
        try:
            # 记录到私有库
            write_into_private(f"round_{self.round}_team: leader={leader}, members={members}")
            
            # 如果队长选择了可疑成员，增加对队长的怀疑
            if not self.is_evil:
                suspicious_count = sum(1 for m in members if m in self.suspects)
                if suspicious_count > 0 and leader not in self.trusted:
                    self.suspects.add(leader)
                    
            # 如果队长没有选自己但选了其他邪恶方，增加信任
            if self.is_evil:
                evil_count = sum(1 for m in members if m in self.trusted)
                if self.index not in members and evil_count > 0:
                    self.trusted.add(leader)
                    
        except Exception as e:
            pass
            
    def decide_mission_member(self, member_number: int) -> list[int]:
        """选择任务队员"""
        self.round += 1  # 增加回合计数
        
        try:
            # 尝试使用LLM辅助选择队员
            prompt = f"""
            我是阿瓦隆游戏中的{self.role}角色，编号{self.index}。
            现在需要选择{member_number}名玩家组队执行任务。
            我怀疑的玩家编号有：{list(self.suspects)}
            我信任的玩家编号有：{list(self.trusted)}
            历史队伍信息：{self.memory['teams']}
            历史任务结果：{self.memory['mission_results']}
            请帮我选择最优的队伍组成，只返回玩家编号列表。
            """
            
            llm_response = askLLM(prompt)
            # 尝试从LLM回复中提取数字列表
            members = re.findall(r'\b[1-7]\b', llm_response)
            members = [int(m) for m in members if 1 <= int(m) <= 7]
            
            # 确保包含自己（如果是好人或为了伪装）
            if self.index not in members:
                members.append(self.index)
                
            # 确保长度符合要求
            while len(members) > member_number:
                # 优先移除可疑成员
                for suspect in self.suspects:
                    if suspect in members and len(members) > member_number:
                        members.remove(suspect)
                # 如果还是超长，随机移除
                if len(members) > member_number:
                    members.remove(random.choice(members))
                    
            # 如果长度不足，添加信任成员或随机成员
            while len(members) < member_number:
                candidates = []
                for i in range(1, self.player_count + 1):
                    if i not in members and i not in self.suspects:
                        candidates.append(i)
                if candidates:
                    members.append(random.choice(candidates))
                else:  # 如果没有合适候选人，从全部玩家中随机选择
                    candidates = [i for i in range(1, self.player_count + 1) if i not in members]
                    if candidates:
                        members.append(random.choice(candidates))
                    
            # 记录选择结果
            write_into_private(f"round_{self.round}_my_team: {members}")
            return members
            
        except Exception as e:
            # 出错时使用基本策略
            write_into_private(f"decide_team_error: {str(e)}")
            
            # 基本策略：包含自己和不可疑的玩家
            members = [self.index]
            candidates = []
            for i in range(1, self.player_count + 1):
                if i != self.index and i not in self.suspects:
                    candidates.append(i)
                    
            # 如果候选人不足，考虑所有非自己玩家
            if len(candidates) < member_number - 1:
                candidates = [i for i in range(1, self.player_count + 1) if i != self.index]
                
            # 随机选择剩余成员
            random.shuffle(candidates)
            members.extend(candidates[:member_number - len(members)])
            
            return members
            
    def walk(self) -> tuple[str, ...]:
        """走步，返回(方向,...)"""
        # 简单移动策略
        directions = ["up", "down", "left", "right"]
        
        # 随机选择一个方向
        return (random.choice(directions),)
        
    def say(self) -> str:
        """发言"""
        try:
            # 根据角色和游戏状态生成发言
            if self.round <= 1:  # 游戏初期
                return self._generate_opening_statement()
            else:  # 根据历史进行分析
                return self._generate_analysis_statement()
        except Exception as e:
            write_into_private(f"say_error: {str(e)}")
            return "我需要更多信息来分析当前局势。"
            
    def _generate_opening_statement(self) -> str:
        """生成开场发言"""
        if self.is_evil:  # 邪恶方
            if self.role == "Morgana":  # 装作梅林
                return "大家好，我能够看到一些有用的信息，但现在还不方便多说。让我们先观察一下。"
            else:
                return "大家好，我是普通村民。我会全力支持对抗邪恶势力的任务。"
        else:  # 正义方
            if self.role == "Merlin":
                return "我们需要仔细选择任务队员，确保任务成功。我会关注每一轮的组队和投票。"
            else:
                return "作为忠诚的亚瑟支持者，我会尽力帮助辨别谁是朋友谁是敌人。请大家分享您的看法。"
                
    def _generate_analysis_statement(self) -> str:
        """根据历史生成分析性发言"""
        try:
            # 尝试用LLM生成分析性发言
            history = read_public_lib()
            prompt = f"""
            我是阿瓦隆游戏中的{self.role}角色，编号{self.index}。
            游戏历史记录：{history}
            根据以上信息，请生成一段不超过100字的游戏分析发言。
            如果我是好人方，应该帮助识别邪恶方；如果我是邪恶方，应该混淆视听。
            """
            
            response = askLLM(prompt)
            # 确保发言不会直接暴露自己的角色
            if "我是" + self.role in response:
                response = response.replace("我是" + self.role, "我认为")
                
            # 限制长度
            if len(response) > 200:
                response = response[:197] + "..."
                
            return response
                
        except Exception as e:
            # LLM失败时的备选方案
            suspicious_players = list(self.suspects)
            if suspicious_players:
                return f"我认为{random.choice(suspicious_players)}号玩家的行为很可疑，建议大家关注一下。"
            else:
                return "目前还没有足够的线索，继续观察各位的行动吧。"
        
    def mission_vote1(self) -> bool:
        """公投表决"""
        # 这里是对组队结果的投票
        try:
            # 对自己的队伍一定投赞成
            if self.last_leader == self.index:
                return True
                
            # 好人方策略
            if not self.is_evil:
                # 计算队伍中可疑成员的比例
                suspicious_count = sum(1 for m in self.last_team if m in self.suspects)
                team_size = len(self.last_team)
                
                # 如果可疑比例超过一半，反对
                if suspicious_count > team_size / 2:
                    return False
                # 如果全都不可疑，支持
                elif suspicious_count == 0:
                    return True
                # 否则根据当前轮数决定
                else:
                    # 轮数越高越倾向于通过，避免游戏自动失败
                    if self.round >= 4:
                        return random.random() > 0.3
                    else:
                        return random.random() > 0.6
            
            # 邪恶方策略
            else:
                evil_count = sum(1 for m in self.last_team if m in self.trusted or m == self.index)
                team_size = len(self.last_team)
                
                # 如果有邪恶方，大概率支持
                if evil_count > 0:
                    return random.random() > 0.2
                # 如果没有邪恶方，大概率反对
                else:
                    # 但在后期轮数要小心，避免因连续拒绝而失败
                    if self.round >= 4:
                        return random.random() > 0.6
                    else:
                        return random.random() > 0.8
                        
        except Exception as e:
            write_into_private(f"vote1_error: {str(e)}")
            # 出错时的默认策略
            return random.random() > 0.5
            
    def mission_vote2(self) -> bool:
        """任务执行投票"""
        # 执行任务的成功/失败投票
        try:
            # 好人方角色必须投真（任务成功）
            if not self.is_evil:
                return True
                
            # 邪恶方策略
            else:
                # 记录投票决定
                write_into_private(f"round_{self.round}_vote2: false (sabotage)")
                # 执行任务时破坏任务（投失败）
                return False
                
        except Exception as e:
            write_into_private(f"vote2_error: {str(e)}")
            # 邪恶方默认破坏，好人方默认支持
            return not self.is_evil
            
    def assass(self) -> int:
        """刺杀（只有刺客角色会被调用）"""
        try:
            # 读取所有积累的信息
            private_data = read_private_lib()
            public_data = read_public_lib()
            
            # 尝试找出最可能是梅林的玩家
            prompt = f"""
            我是阿瓦隆游戏中的刺客，需要选择刺杀目标。
            游戏历史记录：{public_data}
            我的私人记录：{private_data}
            
            分析上述信息，哪个玩家最可能是梅林？只返回一个玩家编号（1-7之间的数字）。
            """
            
            response = askLLM(prompt)
            # 从回答中提取数字
            matches = re.findall(r'\b[1-7]\b', response)
            if matches:
                target = int(matches[0])
                write_into_private(f"assassinate_target: {target}, reason: LLM analysis")
                return target
                
            # 如果LLM没给出明确答案，从怀疑度最低的玩家中选择
            suspects_in_game = set(range(1, self.player_count + 1)) - self.suspects - {self.index}
            if suspects_in_game:
                target = random.choice(list(suspects_in_game))
                write_into_private(f"assassinate_target: {target}, reason: lowest suspicion")
                return target
            else:
                # 随机选择非自己的玩家
                target = random.choice([i for i in range(1, self.player_count + 1) if i != self.index])
                write_into_private(f"assassinate_target: {target}, reason: random choice")
                return target
                
        except Exception as e:
            write_into_private(f"assass_error: {str(e)}")
            # 出错时随机选择非自己的玩家
            return random.choice([i for i in range(1, self.player_count + 1) if i != self.index])