class Player:
    def __init__(self):
        self.player_id = None
        self.evil_knowledge = set()
    
    def set_player_index(self, index):
        self.player_id = index
    
    def receive_evil_knowledge(self, evil_ids):
        self.evil_knowledge = evil_ids
    
    def receive_evil_allies(self, evil_ids):
        self.evil_knowledge = evil_ids
    
    def propose_team(self, team_size):
        # 最简单的策略：选择自己和连续的几个玩家
        team = set()
        for i in range(team_size):
            player = ((self.player_id - 1 + i) % 5) + 1
            team.add(player)
        return team
    
    def vote_for_team(self, team):
        # 如果自己在队伍中或没有明确知识，就投赞成票
        return self.player_id in team
    
    def mission_action(self):
        # 作为好人，总是确保任务成功；作为坏人，有30%概率执行破坏
        import random
        if self.player_id in self.evil_knowledge:
            return random.random() > 0.3  # 70%概率任务成功
        return True  # 好人总是让任务成功
    
    def choose_assassination_target(self):
        # 随机选择一个非自己的玩家作为刺杀目标
        import random
        possible_targets = [i for i in range(1, 6) if i != self.player_id]
        return random.choice(possible_targets)
           