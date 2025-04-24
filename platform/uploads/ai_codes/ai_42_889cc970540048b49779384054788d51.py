class Player:
    def __init__(self):
        self.index = 0
        self.role = None
        self.memory = {}
        self.suspects = set()
        
    def set_player_index(self, index: int):
        self.index = index
        
    def set_role_type(self, role_type: str):
        self.role = role_type
        
    def pass_role_sight(self, role_sight: dict[str, int]):
        self.sight = role_sight
        
    def decide_mission_member(self, team_size: int) -> list[int]:
        return [i for i in range(1, team_size+1)]
        
    def walk(self) -> tuple:
        return ("Up", "Right", "Down")
        
    def say(self) -> str:
        return "测试发言"
        
    def mission_vote1(self) -> bool:
        return True
        
    def mission_vote2(self) -> bool:
        return self.role not in ["Morgana", "Assassin", "Oberon"]
        
    def assass(self) -> int:
        return random.randint(1, 7)
