"""
图灵阿瓦隆游戏裁判系统
负责执行玩家代码、控制游戏流程，并应用游戏规则
"""

import os
import sys
import json
import random
import importlib
import traceback
from typing import Dict, List, Tuple, Any, Set, Optional
import time
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("avalon_referee")

# 导入辅助模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from avalon_game_helper import set_current_context

# 角色常量
BLUE_ROLES = ["Merlin", "Percival", "Knight"]  # 蓝方角色
RED_ROLES = ["Morgana", "Assassin", "Oberon"]  # 红方角色
ALL_ROLES = BLUE_ROLES + RED_ROLES
EVIL_AWARE_ROLES = ["Morgana", "Assassin"]  # 互相了解的红方角色

# 游戏常量
PLAYER_COUNT = 7  # 玩家数量
MISSION_MEMBER_COUNT = [2, 3, 3, 4, 4]  # 每轮任务需要的队员数
MAP_SIZE = 9  # 地图大小
MAX_MISSION_ROUNDS = 5  # 最大任务轮数
MAX_VOTE_ROUNDS = 5  # 最大投票轮数
HEARING_RANGE = {  # 听力范围（中心格周围的方格数）
    "Merlin": 1,
    "Percival": 1,
    "Knight": 2,  # 骑士听力更大
    "Morgana": 1,
    "Assassin": 1,
    "Oberon": 2   # 奥伯伦听力更大
}

class AvalonReferee:
    def __init__(self, game_id: str, data_dir: str = "./data"):
        self.game_id = game_id
        self.data_dir = data_dir
        self.players = {}  # 玩家对象字典 {1: player1, 2: player2, ...}
        self.roles = {}  # 角色分配 {1: "Merlin", 2: "Assassin", ...}
        self.map_data = []  # 地图数据
        self.player_positions = {}  # 玩家位置 {1: (x, y), 2: (x, y), ...}
        self.mission_results = []  # 任务结果 [True, False, ...]
        self.current_round = 0  # 当前任务轮次
        self.blue_wins = 0  # 蓝方胜利次数
        self.red_wins = 0   # 红方胜利次数
        self.public_log = []  # 公共日志
        self.leader_index = 1  # 第一轮队长默认为1号
        
        # 创建数据目录
        os.makedirs(os.path.join(data_dir), exist_ok=True)
        
        # 初始化日志文件
        self.init_logs()
        
    def init_logs(self):
        """初始化游戏日志"""
        # 初始化公共日志文件
        public_log_file = os.path.join(self.data_dir, f"game_{self.game_id}_public.json")
        with open(public_log_file, 'w', encoding='utf-8') as f:
            json.dump([], f)
            
        # 为每个玩家初始化私有日志文件
        for player_id in range(1, PLAYER_COUNT + 1):
            private_log_file = os.path.join(self.data_dir, f"game_{self.game_id}_player_{player_id}_private.json")
            with open(private_log_file, 'w', encoding='utf-8') as f:
                json.dump({"logs": []}, f)
    
    def load_player_code(self, player_modules: Dict[int, Any]):
        """
        加载玩家代码模块
        player_modules: {1: module1, 2: module2, ...}
        """
        for player_id, module in player_modules.items():
            try:
                # 实例化Player类
                player_instance = module.Player()
                self.players[player_id] = player_instance
                # 设置玩家编号
                self.safe_execute(player_id, "set_player_index", player_id)
                logger.info(f"Player {player_id} code loaded successfully")
            except Exception as e:
                logger.error(f"Error loading player {player_id} code: {str(e)}")
                traceback.print_exc()
    
    def init_game(self):
        """初始化游戏：分配角色、初始化地图"""
        # 随机分配角色
        all_roles = BLUE_ROLES.copy()
        # 添加额外的Knight（总共需要2个）
        all_roles.append("Knight")
        all_roles.extend(RED_ROLES)
        random.shuffle(all_roles)
        
        # 分配角色给玩家
        for player_id in range(1, PLAYER_COUNT + 1):
            self.roles[player_id] = all_roles[player_id - 1]
            # 通知玩家角色
            self.safe_execute(player_id, "set_role_type", all_roles[player_id - 1])
            logger.info(f"Player {player_id} assigned role: {all_roles[player_id - 1]}")
        
        # 初始化地图
        self.init_map()
        
        # 记录初始信息到公共日志
        self.log_public_event({
            "type": "game_start",
            "game_id": self.game_id,
            "player_count": PLAYER_COUNT,
            "map_size": MAP_SIZE
        })
    
    def init_map(self):
        """初始化9x9地图并分配玩家初始位置"""
        # 创建空地图
        self.map_data = [[" " for _ in range(MAP_SIZE)] for _ in range(MAP_SIZE)]
        
        # 随机分配玩家位置（不重叠）
        positions = []
        for player_id in range(1, PLAYER_COUNT + 1):
            while True:
                x = random.randint(0, MAP_SIZE - 1)
                y = random.randint(0, MAP_SIZE - 1)
                if (x, y) not in positions:
                    positions.append((x, y))
                    self.player_positions[player_id] = (x, y)
                    self.map_data[x][y] = str(player_id)
                    break
        
        # 通知所有玩家地图信息
        for player_id in range(1, PLAYER_COUNT + 1):
            self.safe_execute(player_id, "pass_map", self.map_data)
    
    def night_phase(self):
        """夜晚阶段：各角色按照视野规则获取信息"""
        # 1. 红方（除奥伯伦）互认
        for player_id, role in self.roles.items():
            if role in EVIL_AWARE_ROLES:  # 互相了解的红方角色
                # 构建包含其他红方（除奥伯伦）玩家的字典
                evil_sight = {}
                for other_id, other_role in self.roles.items():
                    if other_id != player_id and other_role in EVIL_AWARE_ROLES:
                        evil_sight[other_role] = other_id
                
                # 传递给玩家
                self.safe_execute(player_id, "pass_role_sight", evil_sight)
        
        # 2. 梅林看到所有红方
        for player_id, role in self.roles.items():
            if role == "Merlin":
                # 构建包含所有红方玩家的字典
                merlin_sight = {}
                for other_id, other_role in self.roles.items():
                    if other_role in RED_ROLES:
                        merlin_sight[other_role] = other_id
                
                # 传递给梅林
                self.safe_execute(player_id, "pass_role_sight", merlin_sight)
        
        # 3. 派西维尔看到梅林和莫甘娜（但无法区分）
        for player_id, role in self.roles.items():
            if role == "Percival":
                # 找到梅林和莫甘娜
                percival_sight = {}
                for other_id, other_role in self.roles.items():
                    if other_role in ["Merlin", "Morgana"]:
                        percival_sight[other_role] = other_id
                
                # 传递给派西维尔
                self.safe_execute(player_id, "pass_role_sight", percival_sight)
        
        # 记录夜晚阶段完成
        self.log_public_event({
            "type": "night_phase_complete"
        })
    
    def run_mission_round(self):
        """执行一轮任务"""
        self.current_round += 1
        member_count = MISSION_MEMBER_COUNT[self.current_round - 1]
        vote_round = 0
        mission_success = None
        
        self.log_public_event({
            "type": "mission_start",
            "round": self.current_round,
            "leader": self.leader_index,
            "member_count": member_count
        })
        
        # 任务循环，直到有效执行或达到最大投票次数
        while mission_success is None and vote_round < MAX_VOTE_ROUNDS:
            vote_round += 1
            
            # 1. 队长选择队员
            mission_members = self.safe_execute(
                self.leader_index, "decide_mission_member", member_count
            )
            
            # 验证队员数量
            if not isinstance(mission_members, list) or len(mission_members) != member_count:
                logger.warning(f"Player {self.leader_index} returned invalid mission members: {mission_members}")
                # 如果无效，随机选择队员
                mission_members = self.random_select_members(member_count)
            
            # 确保所有队员ID都有效（1-7）
            valid_members = []
            for member in mission_members:
                if isinstance(member, int) and 1 <= member <= PLAYER_COUNT:
                    valid_members.append(member)
            
            # 如果有效队员不足，随机补充
            while len(valid_members) < member_count:
                potential_member = random.randint(1, PLAYER_COUNT)
                if potential_member not in valid_members:
                    valid_members.append(potential_member)
            
            mission_members = valid_members[:member_count]  # 确保只取需要的数量
            
            # 通知所有玩家队伍组成
            for player_id in range(1, PLAYER_COUNT + 1):
                self.safe_execute(player_id, "pass_mission_members", self.leader_index, mission_members)
            
            self.log_public_event({
                "type": "team_proposed",
                "round": self.current_round,
                "vote_round": vote_round,
                "leader": self.leader_index,
                "members": mission_members
            })
            
            # 2. 第一轮发言（全图广播）
            self.conduct_global_speech()
            
            # 3. 玩家移动
            self.conduct_movement()
            
            # 4. 第二轮发言（有限听力范围）
            self.conduct_limited_speech()
            
            # 5. 公投表决
            approve_votes = self.conduct_public_vote(mission_members)
            
            if approve_votes >= (PLAYER_COUNT // 2 + 1):  # 过半数同意
                # 执行任务
                mission_success = self.execute_mission(mission_members)
                break
            else:
                # 否决，更换队长
                self.leader_index = self.leader_index % PLAYER_COUNT + 1
                
                # 记录否决
                self.log_public_event({
                    "type": "team_rejected",
                    "round": self.current_round,
                    "vote_round": vote_round,
                    "approve_count": approve_votes,
                    "next_leader": self.leader_index
                })
                
                # 特殊情况：连续5次否决
                if vote_round == MAX_VOTE_ROUNDS:
                    self.log_public_event({
                        "type": "consecutive_rejections",
                        "round": self.current_round
                    })
                    # 强制执行任务
                    mission_success = self.execute_mission(mission_members)
        
        # 记录任务结果
        self.mission_results.append(mission_success)
        
        if mission_success:
            self.blue_wins += 1
            self.log_public_event({
                "type": "mission_result",
                "round": self.current_round,
                "result": "success",
                "blue_wins": self.blue_wins,
                "red_wins": self.red_wins
            })
        else:
            self.red_wins += 1
            self.log_public_event({
                "type": "mission_result",
                "round": self.current_round,
                "result": "fail",
                "blue_wins": self.blue_wins,
                "red_wins": self.red_wins
            })
        
        # 更新队长
        self.leader_index = self.leader_index % PLAYER_COUNT + 1
    
    def random_select_members(self, member_count: int) -> List[int]:
        """随机选择指定数量的队员"""
        all_players = list(range(1, PLAYER_COUNT + 1))
        random.shuffle(all_players)
        return all_players[:member_count]
    
    def conduct_global_speech(self):
        """进行全局发言（所有玩家都能听到）"""
        speeches = []
        
        # 从队长开始，按编号顺序发言
        ordered_players = [(i - 1) % PLAYER_COUNT + 1 for i in range(self.leader_index, self.leader_index + PLAYER_COUNT)]
        
        for player_id in ordered_players:
            speech = self.safe_execute(player_id, "say")
            
            if not isinstance(speech, str):
                speech = "..."  # 默认发言
            
            speeches.append((player_id, speech))
            
            # 通知所有玩家发言内容
            for listener_id in range(1, PLAYER_COUNT + 1):
                if listener_id != player_id:  # 不需要通知发言者自己
                    self.safe_execute(listener_id, "pass_message", (player_id, speech))
        
        # 记录全局发言
        self.log_public_event({
            "type": "global_speech",
            "round": self.current_round,
            "speeches": speeches
        })
    
    def conduct_movement(self):
        """执行玩家移动"""
        # 从队长开始，按编号顺序移动
        ordered_players = [(i - 1) % PLAYER_COUNT + 1 for i in range(self.leader_index, self.leader_index + PLAYER_COUNT)]
        
        movements = []
        # 清空地图上的玩家标记
        for x in range(MAP_SIZE):
            for y in range(MAP_SIZE):
                if self.map_data[x][y] in [str(i) for i in range(1, PLAYER_COUNT + 1)]:
                    self.map_data[x][y] = " "
        
        for player_id in ordered_players:
            # 获取当前位置
            current_pos = self.player_positions[player_id]
            
            # 获取移动方向
            directions = self.safe_execute(player_id, "walk")
            
            if not isinstance(directions, tuple):
                directions = ()
            
            # 最多移动3步
            steps = min(len(directions), 3)
            new_pos = current_pos
            
            valid_moves = []
            for i in range(steps):
                if i >= len(directions):
                    break
                    
                direction = directions[i].lower() if isinstance(directions[i], str) else ""
                
                x, y = new_pos
                if direction == "up" and x > 0:
                    new_pos = (x - 1, y)
                    valid_moves.append("up")
                elif direction == "down" and x < MAP_SIZE - 1:
                    new_pos = (x + 1, y)
                    valid_moves.append("down")
                elif direction == "left" and y > 0:
                    new_pos = (x, y - 1)
                    valid_moves.append("left")
                elif direction == "right" and y < MAP_SIZE - 1:
                    new_pos = (x, y + 1)
                    valid_moves.append("right")
                else:
                    # 无效移动，跳过
                    continue
                
                # 检查是否与其他玩家重叠
                if new_pos in [self.player_positions[pid] for pid in range(1, PLAYER_COUNT + 1) if pid != player_id]:
                    # 回退到上一个位置
                    new_pos = (x, y)
                    valid_moves.pop()  # 移除最后一个无效移动
                    break
            
            # 更新玩家位置
            self.player_positions[player_id] = new_pos
            x, y = new_pos
            self.map_data[x][y] = str(player_id)
            
            movements.append({
                "player_id": player_id,
                "moves": valid_moves,
                "final_position": new_pos
            })
        
        # 更新所有玩家的地图
        for player_id in range(1, PLAYER_COUNT + 1):
            self.safe_execute(player_id, "pass_map", self.map_data)
        
        # 记录移动
        self.log_public_event({
            "type": "movement",
            "round": self.current_round,
            "movements": movements
        })
    
    def conduct_limited_speech(self):
        """进行有限范围发言（只有在听力范围内的玩家能听到）"""
        # 从队长开始，按编号顺序发言
        ordered_players = [(i - 1) % PLAYER_COUNT + 1 for i in range(self.leader_index, self.leader_index + PLAYER_COUNT)]
        
        speeches = []
        for speaker_id in ordered_players:
            speech = self.safe_execute(speaker_id, "say")
            
            if not isinstance(speech, str):
                speech = "..."  # 默认发言
            
            speeches.append((speaker_id, speech))
            
            # 确定能听到的玩家
            hearers = self.get_players_in_hearing_range(speaker_id)
            
            # 通知能听到的玩家
            for hearer_id in hearers:
                if hearer_id != speaker_id:  # 不需要通知发言者自己
                    self.safe_execute(hearer_id, "pass_message", (speaker_id, speech))
        
        # 记录有限范围发言
        self.log_public_event({
            "type": "limited_speech",
            "round": self.current_round,
            "speeches": speeches
        })
    
    def get_players_in_hearing_range(self, speaker_id: int) -> List[int]:
        """获取能听到指定玩家发言的所有玩家ID"""
        hearers = []
        speaker_x, speaker_y = self.player_positions[speaker_id]
        
        for player_id in range(1, PLAYER_COUNT + 1):
            player_x, player_y = self.player_positions[player_id]
            
            # 计算曼哈顿距离
            distance = abs(player_x - speaker_x) + abs(player_y - speaker_y)
            
            # 获取角色和对应的听力范围
            role = self.roles[player_id]
            hearing_range = HEARING_RANGE.get(role, 1)  # 默认为1
            
            # 如果在听力范围内，加入听者列表
            if distance <= hearing_range:
                hearers.append(player_id)
        
        return hearers
    
    def conduct_public_vote(self, mission_members: List[int]) -> int:
        """
        进行公开投票，决定是否执行任务
        返回支持票数
        """
        votes = {}
        for player_id in range(1, PLAYER_COUNT + 1):
            vote = self.safe_execute(player_id, "mission_vote1")
            
            # 确保投票结果是布尔值
            if not isinstance(vote, bool):
                vote = random.choice([True, False])
            
            votes[player_id] = vote
        
        # 统计支持票
        approve_count = sum(1 for v in votes.values() if v)
        
        # 记录投票结果
        self.log_public_event({
            "type": "public_vote",
            "round": self.current_round,
            "votes": votes,
            "approve_count": approve_count,
            "result": "approved" if approve_count >= (PLAYER_COUNT // 2 + 1) else "rejected"
        })
        
        return approve_count
    
    def execute_mission(self, mission_members: List[int]) -> bool:
        """
        执行任务，返回任务是否成功
        """
        votes = {}
        fail_votes = 0
        
        for player_id in mission_members:
            vote = self.safe_execute(player_id, "mission_vote2")
            
            # 确保投票结果是布尔值
            if not isinstance(vote, bool):
                # 红方默认投失败，蓝方默认投成功
                vote = self.roles[player_id] not in RED_ROLES
            
            votes[player_id] = vote
            
            # 统计失败票
            if not vote:
                fail_votes += 1
        
        # 判断任务结果
        # 第4轮(索引3)为保护轮，需要至少2票失败；其他轮次只需1票失败
        if self.current_round == 4:  # 第4轮
            mission_success = fail_votes < 2
        else:
            mission_success = fail_votes == 0
        
        # 记录任务执行结果（匿名）
        self.log_public_event({
            "type": "mission_execution",
            "round": self.current_round,
            "fail_votes": fail_votes,
            "success": mission_success
        })
        
        return mission_success
    
    def assassinate_phase(self) -> bool:
        """
        刺杀阶段，返回刺杀是否成功（刺中梅林）
        """
        # 找到刺客
        assassin_id = None
        for player_id, role in self.roles.items():
            if role == "Assassin":
                assassin_id = player_id
                break
        
        if not assassin_id:
            logger.error("No Assassin found in the game")
            return False
        
        # 刺客选择目标
        target_id = self.safe_execute(assassin_id, "assass")
        
        # 确保目标是有效玩家ID
        if not isinstance(target_id, int) or target_id < 1 or target_id > PLAYER_COUNT:
            logger.warning(f"Assassin returned invalid target: {target_id}")
            # 随机选择目标
            target_id = random.choice([i for i in range(1, PLAYER_COUNT + 1) if i != assassin_id])
        
        # 判断是否刺中梅林
        success = self.roles[target_id] == "Merlin"
        
        # 记录刺杀结果
        self.log_public_event({
            "type": "assassination",
            "assassin": assassin_id,
            "target": target_id,
            "target_role": self.roles[target_id],
            "success": success
        })
        
        return success
    
    def run_game(self) -> Dict[str, Any]:
        """
        运行游戏，返回游戏结果
        """
        try:
            # 初始化游戏
            self.init_game()
            
            # 夜晚阶段
            self.night_phase()
            
            # 任务阶段
            while self.blue_wins < 3 and self.red_wins < 3 and self.current_round < MAX_MISSION_ROUNDS:
                self.run_mission_round()
            
            # 游戏结束判定
            game_result = {
                "blue_wins": self.blue_wins,
                "red_wins": self.red_wins,
                "rounds_played": self.current_round
            }
            
            # 如果蓝方即将获胜（3轮任务成功），执行刺杀阶段
            if self.blue_wins >= 3:
                assassination_success = self.assassinate_phase()
                
                if assassination_success:
                    # 刺杀成功，红方胜利
                    game_result["winner"] = "red"
                    game_result["win_reason"] = "assassination_success"
                else:
                    # 刺杀失败，蓝方胜利
                    game_result["winner"] = "blue"
                    game_result["win_reason"] = "missions_complete_and_assassination_failed"
            elif self.red_wins >= 3:
                # 红方直接胜利（3轮任务失败）
                game_result["winner"] = "red"
                game_result["win_reason"] = "missions_failed"
            else:
                # 达到最大轮数，根据胜利次数判定
                if self.blue_wins > self.red_wins:
                    game_result["winner"] = "blue"
                    game_result["win_reason"] = "more_successful_missions"
                else:
                    game_result["winner"] = "red"
                    game_result["win_reason"] = "more_failed_missions"
            
            # 记录游戏结果
            self.log_public_event({
                "type": "game_end",
                "result": game_result
            })
            
            return game_result
            
        except Exception as e:
            logger.error(f"Error running game: {str(e)}")
            traceback.print_exc()
            return {
                "error": str(e),
                "blue_wins": self.blue_wins,
                "red_wins": self.red_wins,
                "rounds_played": self.current_round
            }
    
    def safe_execute(self, player_id: int, method_name: str, *args, **kwargs):
        """
        安全执行玩家代码，处理可能的异常
        """
        try:
            # 设置当前上下文
            set_current_context(player_id, self.game_id)
            
            # 获取玩家实例和方法
            player = self.players.get(player_id)
            if not player:
                logger.error(f"Player {player_id} not found")
                return None
                
            method = getattr(player, method_name, None)
            if not method or not callable(method):
                logger.error(f"Method {method_name} not found or not callable in player {player_id}")
                return None
            
            # 执行方法并返回结果
            start_time = time.time()
            result = method(*args, **kwargs)
            execution_time = time.time() - start_time
            
            # 检查执行时间
            if execution_time > 5:  # 超过5秒视为超时
                logger.warning(f"Player {player_id} method {method_name} took {execution_time:.2f} seconds")
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing player {player_id} method {method_name}: {str(e)}")
            traceback.print_exc()
            return None
    
    def log_public_event(self, event: Dict[str, Any]):
        """记录公共事件到日志"""
        # 添加时间戳
        event["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # 添加到内存中的日志
        self.public_log.append(event)
        
        # 写入公共日志文件
        public_log_file = os.path.join(self.data_dir, f"game_{self.game_id}_public.json")
        try:
            with open(public_log_file, 'w', encoding='utf-8') as f:
                json.dump(self.public_log, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error writing public log: {str(e)}")


def run_avalon_game(game_id: str, player_modules: Dict[int, Any], data_dir: str = "./data") -> Dict[str, Any]:
    """
    运行一场阿瓦隆游戏
    
    参数:
        game_id: 游戏ID
        player_modules: 玩家代码模块字典 {1: module1, 2: module2, ...}
        data_dir: 数据目录
        
    返回:
        游戏结果字典
    """
    referee = AvalonReferee(game_id, data_dir)
    referee.load_player_code(player_modules)
    return referee.run_game()


# 测试函数
def test_run_game():
    """测试运行游戏"""
    # 这里可以加载测试用的Player模块
    from avalon.baselines import get_all_baseline_codes
    
    baseline_codes = get_all_baseline_codes()
    player_modules = {}
    
    for i in range(1, PLAYER_COUNT + 1):
        # 动态创建模块
        module_name = f"player_{i}_module"
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        
        # 执行代码
        exec(baseline_codes["basic_player"], module.__dict__)
        player_modules[i] = module
    
    # 运行游戏
    game_id = f"test_{int(time.time())}"
    result = run_avalon_game(game_id, player_modules)
    print(f"Game result: {result}")


if __name__ == "__main__":
    test_run_game()