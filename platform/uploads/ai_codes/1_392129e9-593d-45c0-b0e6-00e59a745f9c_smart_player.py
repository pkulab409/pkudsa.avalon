class Player:
    def __init__(self):
        self.player_id = None
        self.evil_knowledge = set()
        self.team_history = []
        self.vote_history = {}
        self.mission_results = []
        self.suspected_evil = set()  # 疑似邪恶玩家
        self.trusted_good = set()    # 疑似正义玩家
        self.assassination_target = None  # 刺杀目标
        self.is_merlin = False       # 是否为梅林
    
    def set_player_index(self, index):
        self.player_id = index
        # 初始时，没有特别的信任或怀疑
        for i in range(1, 6):
            if i != self.player_id:
                self.vote_history[i] = []
    
    def receive_evil_knowledge(self, evil_ids):
        # 梅林获得的邪恶玩家信息
        self.evil_knowledge = evil_ids
        self.is_merlin = True
        
        # 记录到游戏辅助模块
        from game_helper import write_private_log
        write_private_log(f"梅林视角：邪恶方玩家 {evil_ids}")
    
    def receive_evil_allies(self, evil_ids):
        # 邪恶方获得的盟友信息
        self.evil_knowledge = evil_ids.union({self.player_id})
        
        # 记录到游戏辅助模块
        from game_helper import write_private_log
        write_private_log(f"邪恶视角：邪恶方玩家 {self.evil_knowledge}")
    
    def _analyze_trusted_players(self):
        #分析历史数据，找出可能的好人
        trusted = set()
        
        # 分析任务结果与团队组成的关系
        for round_idx, (team, result) in enumerate(zip(self.team_history, self.mission_results)):
            if result:  # 任务成功
                # 任务成功的队伍成员更可能是好人
                for player in team:
                    if player not in self.evil_knowledge:
                        trusted.add(player)
            else:  # 任务失败
                # 任务失败的队伍中至少有一个坏人，但不确定是谁
                # 如果我是好人，标记这个队伍所有不是我的人为可疑
                if self.player_id not in self.evil_knowledge and self.player_id in team:
                    for player in team:
                        if player != self.player_id:
                            self.suspected_evil.add(player)
        
        # 分析投票模式
        for player, votes in self.vote_history.items():
            if len(votes) < 2:  # 数据不足，跳过
                continue
                
            # 如果玩家的投票模式与任务成功/失败高度相关，进行判断
            approve_success = sum(1 for v, r in zip(votes, self.mission_results) if v and r)
            approve_fail = sum(1 for v, r in zip(votes, self.mission_results) if v and not r)
            
            # 如果玩家倾向于支持成功的任务，和反对失败的任务，可能是好人
            if approve_success > approve_fail * 2:
                trusted.add(player)
            # 如果玩家倾向于支持失败的任务，可能是坏人
            elif approve_fail > approve_success * 2:
                self.suspected_evil.add(player)
        
        # 如果我是梅林，利用这个知识
        if self.is_merlin:
            self.suspected_evil = self.evil_knowledge.copy()
            
        # 如果我是邪恶方，排除我知道的邪恶同伴
        if self.player_id in self.evil_knowledge:
            trusted = trusted - self.evil_knowledge
            self.suspected_evil = self.suspected_evil - self.evil_knowledge
            
        # 合并已信任的好人
        trusted = trusted.union(self.trusted_good)
        
        # 确保没有矛盾
        trusted = trusted - self.suspected_evil
        
        return trusted
    
    def propose_team(self, team_size):
        import random
        # 智能策略：作为好人，选择信任的玩家；作为坏人，混入至少一个坏人
        team = {self.player_id}  # 始终包括自己
        
        # 分析历史数据，找出可能的好人
        trusted_players = self._analyze_trusted_players()
        
        # 如果我是坏人，确保至少一个队友是坏人
        if self.player_id in self.evil_knowledge:
            evil_allies = [pid for pid in self.evil_knowledge if pid != self.player_id]
            if evil_allies and team_size > 1:
                # 选择一个邪恶同伴
                evil_choice = random.choice(evil_allies)
                team.add(evil_choice)
                
                # 记录策略
                from game_helper import write_private_log
                write_private_log(f"作为邪恶方，我选择了邪恶同伴 {evil_choice} 进入队伍")
        
        # 填充剩余位置
        remaining = team_size - len(team)
        # 优先选择信任的玩家
        for player in trusted_players:
            if player not in team and remaining > 0:
                team.add(player)
                remaining -= 1
                
        # 如果还需要更多玩家，随机选择非可疑玩家
        candidates = [p for p in range(1, 6) 
                     if p not in team and p not in self.suspected_evil]
        while remaining > 0 and candidates:
            choice = random.choice(candidates)
            team.add(choice)
            candidates.remove(choice)
            remaining -= 1
            
        # 如果还不够，被迫选择可疑玩家
        if remaining > 0:
            suspicions = [p for p in range(1, 6) if p not in team]
            random.shuffle(suspicions)
            for p in suspicions[:remaining]:
                team.add(p)
        
        # 记录团队选择
        self.team_history.append(team)
        
        # 使用游戏辅助模块记录决策
        from game_helper import write_private_log
        write_private_log(f"提议队伍: {team}, 信任玩家: {trusted_players}, 可疑玩家: {self.suspected_evil}")
        
        return team
    
    def vote_for_team(self, team):
        # 智能投票策略
        
        # 如果自己在队伍中，倾向于赞成
        in_team = self.player_id in team
        
        # 如果是邪恶方，检查队伍中的邪恶成员数量
        if self.player_id in self.evil_knowledge:
            evil_count = sum(1 for p in team if p in self.evil_knowledge)
            # 邪恶方应该支持有邪恶成员的队伍
            if evil_count > 0:
                vote = True
            else:
                # 如果没有邪恶成员，则反对
                vote = False
        else:
            # 作为好人，检查可疑成员数量
            suspect_count = sum(1 for p in team if p in self.suspected_evil)
            
            # 如果队伍中没有可疑成员，或者只有很少的可疑成员且自己在队伍中
            if suspect_count == 0 or (suspect_count <= 1 and in_team):
                vote = True
            else:
                # 如果有多个可疑成员，则反对
                vote = False
                
        # 记录投票历史
        for player in team:
            if player != self.player_id and player in self.vote_history:
                self.vote_history[player].append(vote)
                
        # 使用游戏辅助模块记录决策
        from game_helper import write_private_log
        write_private_log(f"对队伍 {team} 的投票: {'赞成' if vote else '反对'}")
        
        return vote
    
    def mission_action(self):
        # 任务行动策略
        
        # 如果是好人，始终支持任务成功
        if self.player_id not in self.evil_knowledge:
            return True
            
        # 如果是邪恶方，战略性地决定是否破坏
        import random
        
        # 获取当前任务轮次（基于已完成的任务数量）
        current_round = len(self.mission_results) + 1
        
        # 计算当前蓝方和红方的得分
        blue_wins = sum(1 for r in self.mission_results if r)
        red_wins = len(self.mission_results) - blue_wins
        
        # 如果红方已经赢了两轮，这轮必须破坏
        if red_wins == 2:
            sabotage = True
        # 如果蓝方已经赢了两轮，这轮必须破坏
        elif blue_wins == 2:
            sabotage = True
        # 第一轮通常不破坏以避免怀疑
        elif current_round == 1:
            sabotage = random.random() < 0.2  # 20%概率破坏
        # 如果团队较大，更可能破坏，因为怀疑会分散
        elif len(self.team_history[-1]) >= 3:
            sabotage = random.random() < 0.7  # 70%概率破坏
        else:
            sabotage = random.random() < 0.5  # 50%概率破坏
            
        # 记录决策
        from game_helper import write_private_log
        if sabotage:
            write_private_log(f"作为邪恶方，我选择破坏任务")
        else:
            write_private_log(f"作为邪恶方，我选择不破坏任务以混淆视听")
            
        # 返回决定（True表示支持任务，False表示破坏任务）
        return not sabotage
    
    def choose_assassination_target(self):
        # 如果已经确定目标，直接返回
        if self.assassination_target:
            return self.assassination_target
            
        # 分析哪个玩家最可能是梅林
        merlin_candidates = {}
        
        # 检查谁似乎知道邪恶方的身份
        for player_id in range(1, 6):
            if player_id not in self.evil_knowledge:
                merlin_score = 0
                
                # 分析投票模式是否显示出对邪恶方的了解
                for evil_id in self.evil_knowledge:
                    if evil_id in self.vote_history and player_id in self.vote_history:
                        # 检查该玩家是否倾向于反对包含邪恶方的队伍
                        evil_teams = [i for i, team in enumerate(self.team_history) if evil_id in team]
                        player_votes = self.vote_history[player_id]
                        
                        if len(player_votes) >= len(evil_teams):
                            # 计算该玩家反对包含邪恶方的队伍的比例
                            evil_awareness = sum(1 for i in evil_teams if i < len(player_votes) and not player_votes[i])
                            if evil_awareness > len(evil_teams) / 2:
                                merlin_score += 1
                
                # 检查该玩家是否参与了成功的任务
                successful_missions = [i for i, result in enumerate(self.mission_results) if result]
                player_in_success = sum(1 for i in successful_missions if player_id in self.team_history[i])
                
                # 参与成功任务较多的玩家更可能是梅林
                merlin_score += player_in_success
                
                # 记录分数
                merlin_candidates[player_id] = merlin_score
        
        # 选择得分最高的非邪恶玩家作为刺杀目标
        if merlin_candidates:
            best_candidates = sorted(merlin_candidates.items(), key=lambda x: x[1], reverse=True)
            self.assassination_target = best_candidates[0][0]
        else:
            # 如果没有足够信息，随机选择一个非邪恶方玩家
            import random
            good_players = [p for p in range(1, 6) if p not in self.evil_knowledge]
            if good_players:
                self.assassination_target = random.choice(good_players)
            else:
                # 理论上不应该发生，但以防万一
                self.assassination_target = random.randint(1, 5)
        
        # 使用游戏辅助模块记录决策
        from game_helper import write_private_log
        write_private_log(f"刺杀目标: 玩家 {self.assassination_target}, 梅林候选评分: {merlin_candidates}")
        
        return self.assassination_target
