"""
裁判系统 - 负责执行游戏规则和管理游戏状态
"""

import os
import sys
import json
import random
import importlib
import traceback
from typing import Dict, List, Any
import time
import logging
import importlib.util
from datetime import datetime
from observer import Observer
from avalon_game_helper import INIT_PRIVA_LOG_DICT
from restrictor import RESTRICTED_BUILTINS

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Referee")

# 导入辅助模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 确保导入成功
try:
    from game.avalon_game_helper import set_current_context
except ImportError:
    logger.error("Failed to import set_current_context from game.avalon_game_helper")

    # 可以选择退出或提供默认实现
    def set_current_context(player_id: int, game_id: str):
        pass  # 空实现或记录错误


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
    "Oberon": 2,  # 奥伯伦听力更大
}


class AvalonReferee:
    def __init__(self, game_id: str, battle_observer: Observer, data_dir: str = "./data"):
        self.game_id = game_id
        self.data_dir = data_dir
        self.players = {}  # 玩家对象字典 {1: player1, 2: player2, ...}
        self.roles = {}  # 角色分配 {1: "Merlin", 2: "Assassin", ...}
        self.map_data = []  # 地图数据
        self.player_positions = {}  # 玩家位置 {1: (x, y), 2: (x, y), ...}
        self.mission_results = []  # 任务结果 [True, False, ...]
        self.current_round = 0  # 当前任务轮次
        self.blue_wins = 0  # 蓝方胜利次数
        self.red_wins = 0  # 红方胜利次数
        self.public_log = []  # 公共日志
        self.leader_index = random.randint(1, PLAYER_COUNT)  # 随机选择初始队长
        logger.info(
            f"Game {game_id} initialized. Data dir: {data_dir}. Initial leader: {self.leader_index}"
        )

        # 创建数据目录
        os.makedirs(os.path.join(data_dir), exist_ok=True)

        # 初始化日志文件
        self.init_logs()

        # Observer实例
        self.battle_observer = battle_observer

    def init_logs(self):
        """初始化游戏日志"""
        logger.info(f"Initializing logs for game {self.game_id}")
        # 初始化公共日志文件
        public_log_file = os.path.join(
            self.data_dir, f"game_{self.game_id}_public.json"
        )
        with open(public_log_file, "w", encoding="utf-8") as f:
            json.dump([], f)

        # 为每个玩家初始化私有日志文件
        for player_id in range(1, PLAYER_COUNT + 1):
            private_log_file = os.path.join(
                self.data_dir, f"game_{self.game_id}_player_{player_id}_private.json"
            )
            with open(private_log_file, "w", encoding="utf-8") as f:
                json.dump(INIT_PRIVA_LOG_DICT, f)
        logger.info(f"Public and private log files initialized in {self.data_dir}")

    def _load_codes(self, player_codes):
        player_modules = {}

        for player_id, code_content in player_codes.items():
            # 创建唯一模块名
            module_name = f"player_{player_id}_module_{int(time.time()*1000)}"
            logger.info(f"为玩家 {player_id} 创建模块: {module_name}")

            try:
                # 创建模块规范
                spec = importlib.util.spec_from_loader(module_name, loader=None)
                if spec is None:
                    logger.error(f"为 {module_name} 创建规范失败")
                    continue

                # 从规范创建模块
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module  # 注册模块

                # 执行代码（限制 builtins）
                module.__dict__['__builtins__'] = RESTRICTED_BUILTINS
                exec(code_content, module.__dict__)

                # 检查Player类是否存在
                if not hasattr(module, "Player"):
                    logger.error(f"玩家 {player_id} 的代码已执行但未找到 'Player' 类")
                    self.suspend_game(
                        "critical_player_ERROR", player_id, "Player",
                        f"玩家 {player_id} 的代码已执行但未找到 'Player' 类"
                    )
                # 存储模块
                player_modules[player_id] = module
                logger.info(f"玩家 {player_id} 代码加载成功")

            except Exception as e:
                logger.error(f"加载玩家 {player_id} 代码时出错: {str(e)}")
                traceback.print_exc()

        return player_modules

    def load_player_codes(self, player_modules: Dict[int, Any]):
        """
        加载玩家代码模块
        player_modules: {1: module1, 2: module2, ...}
        """
        logger.info(f"Loading player code for {len(player_modules)} players.")
        for player_id, module in player_modules.items():
            try:
                # 实例化Player类
                player_instance = module.Player()
                self.players[player_id] = player_instance
                # 设置玩家编号
            except Exception as e:  # 玩家代码 __init__ 报错
                logger.error(
                    f"Error executing Player {player_id} method '__init__': {str(e)}",
                    exc_info=True,  # Include traceback in log
                )
                try:
                    self.suspend_game(  # 统一走过 suspend 过程，会报一个错，这边倒到 e_
                        "critical_player_ERROR", player_id, "__init__", str(e)
                    )
                except Exception as e_:  # suspend_game 抛出的错误导到这里
                    logger.error(
                        f"Critical error during game {self.game_id}: {str(e)}",
                        exc_info=True
                    )
                    raise RuntimeError(e_)
            
            # 分配编号
            self.safe_execute(player_id, "set_player_index", player_id)
            logger.info(f"Player {player_id} code loaded and instance created.")

    def init_game(self):
        """初始化游戏：分配角色、初始化地图"""
        logger.info("Initializing game: Assigning roles and map.")
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
        logger.info(f"Roles assigned: {self.roles}")

        # 初始化地图
        self.init_map()

        # 记录初始信息到公共日志
        self.log_public_event(
            {
                "type": "game_start",
                "game_id": self.game_id,
                "player_count": PLAYER_COUNT,
                "map_size": MAP_SIZE,
            }
        )
        logger.info("Game initialization complete.")

    def init_map(self):
        """初始化9x9地图并分配玩家初始位置"""
        logger.info("Initializing map and player positions.")
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
        logger.info(f"Player positions: {self.player_positions}")
        self.battle_observer.make_snapshot("move", self.player_positions)

        # 通知所有玩家地图信息
        for player_id in range(1, PLAYER_COUNT + 1):
            logger.debug(f"Sending map data to player {player_id}")
            self.safe_execute(player_id, "pass_map", self.map_data)
        logger.info("Map initialized and sent to players.")

    def night_phase(self):
        """夜晚阶段：各角色按照视野规则获取信息"""
        logger.info("Starting Night Phase.")
        # 1. 红方（除奥伯伦）互认
        evil_team_ids = [pid for pid, r in self.roles.items() if r in EVIL_AWARE_ROLES]
        logger.info(f"Evil team (aware): {evil_team_ids}")
        for player_id, role in self.roles.items():
            if role in EVIL_AWARE_ROLES:  # 互相了解的红方角色
                # 构建包含其他红方（除奥伯伦）玩家的字典
                evil_sight = {}
                for other_id, other_role in self.roles.items():
                    if other_id != player_id and other_role in EVIL_AWARE_ROLES:
                        evil_sight[other_role] = other_id

                logger.debug(
                    f"Sending evil sight info to Player {player_id} ({role}): {evil_sight}"
                )
                # 传递给玩家
                self.safe_execute(player_id, "pass_role_sight", evil_sight)

        # 2. 梅林看到所有红方
        merlin_id = [pid for pid, r in self.roles.items() if r == "Merlin"]
        if merlin_id:
            merlin_id = merlin_id[0]
            red_team_ids = {r: pid for pid, r in self.roles.items() if r in RED_ROLES}
            logger.debug(
                f"Sending red team info to Merlin (Player {merlin_id}): {red_team_ids}"
            )
            self.safe_execute(merlin_id, "pass_role_sight", red_team_ids)

        # 3. 派西维尔看到梅林和莫甘娜（但无法区分）
        percival_id = [pid for pid, r in self.roles.items() if r == "Percival"]
        morgana_id = [pid for pid, r in self.roles.items() if r == "Morgana"]
        if percival_id and morgana_id:
            percival_id = percival_id[0]
            morgana_id = morgana_id[0]
            merlin_morgana_id = sorted([merlin_id, morgana_id])
            targets = {f"Special{i+1}": merlin_morgana_id[i] for i in range(2)}
            logger.debug(
                f"Sending Merlin/Morgana info to Percival (Player {percival_id}): {targets}"
            )
            self.safe_execute(percival_id, "pass_role_sight", targets)

        # 记录夜晚阶段完成
        self.log_public_event({"type": "night_phase_complete"})
        logger.info("Night Phase complete.") 
        self.battle_observer.make_snapshot('referee', 'night')

    def run_mission_round(self):
        """执行一轮任务"""
        self.current_round += 1
        member_count = MISSION_MEMBER_COUNT[self.current_round - 1]
        vote_round = 0
        mission_success = None

        logger.info(f"--- Starting Mission Round {self.current_round} ---")
        logger.info(
            f"Leader: Player {self.leader_index}, Members needed: {member_count}"
        )
        self.log_public_event(
            {
                "type": "mission_start",
                "round": self.current_round,
                "leader": self.leader_index,
                "member_count": member_count,
            }
        )

        # 任务循环，直到有效执行或达到最大投票次数
        while mission_success is None and vote_round < MAX_VOTE_ROUNDS:
            vote_round += 1
            logger.info(
                f"Starting Vote Round {vote_round} for Mission {self.current_round}."
            )

            # 1. 队长选择队员
            logger.info(f"Leader {self.leader_index} is proposing a team.")
            self.battle_observer.make_snapshot('referee', f"Leader {self.leader_index} is proposing a team.")
            mission_members = self.safe_execute(
                self.leader_index, "decide_mission_member", member_count
            )
            logger.debug(f"Leader {self.leader_index} proposed: {mission_members}")

            # 验证队员数量和有效性 (Adding logs for validation steps)
            if not isinstance(mission_members, list):
                logger.error(
                    f"Leader {self.leader_index} returned non-list: {type(mission_members)}.",
                    exc_info=True,  # Include traceback in log
                )
                self.suspend_game(
                    "player_ruturn_ERROR", self.leader_index, "decide_mission_member",
                    f"Leader {self.leader_index} returned non-list: {type(mission_members)}"
                )
                
            else:
                valid_members = []
                for member in mission_members:
                    if isinstance(member, int) and 1 <= member <= PLAYER_COUNT:
                        if (
                            member not in valid_members
                        ):  # 防止队员重复
                            valid_members.append(member)
                        else:
                            logger.error(
                                f"Leader {self.leader_index} proposed duplicate member {member}.",
                                exc_info=True,  # Include traceback in log
                                )
                            self.suspend_game(
                                "player_ruturn_ERROR", self.leader_index, "decide_mission_member",
                                f"Leader {self.leader_index} proposed duplicate member: {mission_members}"
                            )
                    else:
                        logger.error(
                            f"Leader {self.leader_index} proposed invalid member {member}.",
                            exc_info=True,  # Include traceback in log
                            )
                        self.suspend_game(
                            "player_ruturn_ERROR", self.leader_index, "decide_mission_member",
                            f"Leader {self.leader_index} proposed invalid member: {mission_members}"
                        )                      

                if len(valid_members) != member_count:
                    logger.error(
                        f"Leader {self.leader_index} proposed too many(few) members: {member}.",
                        exc_info=True,  # Include traceback in log
                        )
                    self.suspend_game(
                        "player_ruturn_ERROR", self.leader_index, "decide_mission_member",
                        f"Leader {self.leader_index} proposed too many(few) members: {mission_members}"
                    )

                else:
                    mission_members = valid_members  # Use the validated list
                    logger.info(
                        f"Leader {self.leader_index} proposed team: {mission_members}"
                    )

                self.battle_observer.make_snapshot(  # snapshot
                        'referee',
                        f"Leader {self.leader_index} proposed team: {mission_members}")

            # 通知所有玩家队伍组成
            logger.debug("Notifying all players of the proposed team.")
            for player_id in range(1, PLAYER_COUNT + 1):
                self.safe_execute(
                    player_id,
                    "pass_mission_members",
                    self.leader_index,
                    mission_members,
                )
            self.log_public_event(
                {
                    "type": "team_proposed",
                    "round": self.current_round,
                    "vote_round": vote_round,
                    "leader": self.leader_index,
                    "members": mission_members,
                }
            )

            # 2. 第一轮发言（全图广播）
            logger.info("Starting Global Speech phase.")
            self.battle_observer.make_snapshot('referee', "Starting Global Speech phase.")
            self.conduct_global_speech()

            # 3. 玩家移动
            logger.info("Starting Movement phase.")
            self.battle_observer.make_snapshot('referee', "Starting Movement phase.")
            self.conduct_movement()

            # 4. 第二轮发言（有限听力范围）
            logger.info("Starting Limited Speech phase.")
            self.battle_observer.make_snapshot('referee', "Starting Limited Speech phase.")
            self.conduct_limited_speech()

            # 5. 公投表决
            logger.info("Starting Public Vote phase.")
            self.battle_observer.make_snapshot('referee', "Starting Public Vote phase.")
            approve_votes = self.conduct_public_vote(mission_members)
            logger.info(
                f"Public vote result: {approve_votes} Approve vs {PLAYER_COUNT - approve_votes} Reject."
            )
            self.battle_observer.make_snapshot('referee', f"Public vote result: {approve_votes} Approve vs {PLAYER_COUNT - approve_votes} Reject.")

            if approve_votes >= (PLAYER_COUNT // 2 + 1):  # 过半数同意
                logger.info("Team Approved. Executing mission.")
                self.battle_observer.make_snapshot('referee',"Team Approved. Executing mission.")
                # 执行任务
                mission_success = self.execute_mission(mission_members)
                break  # 退出循环
            else:
                logger.info("Team Rejected.")
                self.battle_observer.make_snapshot('referee',"Team Rejected.")
                # 否决，更换队长
                old_leader = self.leader_index
                self.leader_index = self.leader_index % PLAYER_COUNT + 1
                logger.info(f"Leader changed from {old_leader} to {self.leader_index}.")
                self.battle_observer.make_snapshot('referee',f"Leader changed from {old_leader} to {self.leader_index}.")

                # 记录否决
                self.log_public_event(
                    {
                        "type": "team_rejected",
                        "round": self.current_round,
                        "vote_round": vote_round,
                        "approve_count": approve_votes,
                        "next_leader": self.leader_index,
                    }
                )

                # 特殊情况：连续5次否决
                if vote_round == MAX_VOTE_ROUNDS:
                    logger.warning(
                        "Maximum vote rounds reached. Forcing mission execution with last proposed team."
                    )
                    self.battle_observer.make_snapshot('referee',"Maximum vote rounds reached. Forcing mission execution with last proposed team.")
                    self.log_public_event(
                        {"type": "consecutive_rejections", "round": self.current_round}
                    )
                    # 强制执行任务
                    mission_success = self.execute_mission(mission_members)
                    # No break needed, loop condition will handle exit

        # 记录任务结果
        logger.info(
            f"Mission {self.current_round} Result: {'Success' if mission_success else 'Fail'}"
        )
        self.battle_observer.make_snapshot('referee',f"Mission {self.current_round} Result: {'Success' if mission_success else 'Fail'}")
        self.mission_results.append(mission_success)

        if mission_success:
            self.blue_wins += 1
            self.log_public_event(
                {
                    "type": "mission_result",
                    "round": self.current_round,
                    "result": "success",
                    "blue_wins": self.blue_wins,
                    "red_wins": self.red_wins,
                }
            )
        else:
            self.red_wins += 1
            self.log_public_event(
                {
                    "type": "mission_result",
                    "round": self.current_round,
                    "result": "fail",
                    "blue_wins": self.blue_wins,
                    "red_wins": self.red_wins,
                }
            )
        logger.info(f"Score: Blue {self.blue_wins} - Red {self.red_wins}")
        self.battle_observer.make_snapshot('referee',f"Score: Blue {self.blue_wins} - Red {self.red_wins}")

        # 更新队长 (Moved outside the loop, happens once per mission round end)
        # self.leader_index = self.leader_index % PLAYER_COUNT + 1 # Already updated on rejection, needs careful thought if approved
        # Let's update leader *after* the mission result is logged, regardless of approval/rejection outcome for simplicity
        old_leader_for_next_round = self.leader_index
        self.leader_index = self.leader_index % PLAYER_COUNT + 1
        logger.debug(
            f"Leader for next round will be {self.leader_index} (previous was {old_leader_for_next_round})"
        )
        logger.info(f"--- End of Mission Round {self.current_round} ---")
        self.battle_observer.make_snapshot('referee',f"--- End of Mission Round {self.current_round} ---")

    def conduct_global_speech(self):
        """进行全局发言（所有玩家都能听到）"""
        speeches = []

        # 从队长开始，按编号顺序发言
        ordered_players = [
            (i - 1) % PLAYER_COUNT + 1
            for i in range(self.leader_index, self.leader_index + PLAYER_COUNT)
        ]
        logger.debug(f"Global speech order: {ordered_players}")

        for player_id in ordered_players:
            logger.debug(f"Requesting speech from Player {player_id}")
            speech = self.safe_execute(player_id, "say")

            if not isinstance(speech, str):  # 用户给的 speech 异常
                logger.error(
                    f"Player {player_id} returned non-string speech: {type(speech)}.",
                    exc_info=True,  # Include traceback in log
                    )
                self.suspend_game(
                    "player_ruturn_ERROR", player_id, "say",
                    f"Returned non-string speech: {type(speech)} during global speech"
                )

            logger.info(
                f"Global Speech - Player {player_id}: {speech[:100]}{'...' if len(speech) > 100 else ''}"
            )
            self.battle_observer.make_snapshot(f"player{player_id}", f"{speech[:100]}{'...' if len(speech) > 100 else ''}")
            speeches.append((player_id, speech))

            # 通知所有玩家发言内容
            logger.debug(f"Broadcasting Player {player_id}'s speech to others.")
            for listener_id in range(1, PLAYER_COUNT + 1):
                if listener_id != player_id:  # 不需要通知发言者自己
                    self.safe_execute(listener_id, "pass_message", (player_id, speech))

        # 记录全局发言
        self.log_public_event(
            {"type": "global_speech", "round": self.current_round, "speeches": speeches}
        )
        logger.info("Global Speech phase complete.")
        self.battle_observer.make_snapshot("referee","Global Speech phase complete.")


    def conduct_movement(self):
        """执行玩家移动"""
        # 从队长开始，按编号顺序移动
        ordered_players = [
            (i - 1) % PLAYER_COUNT + 1
            for i in range(self.leader_index, self.leader_index + PLAYER_COUNT)
        ]
        logger.debug(f"Movement order: {ordered_players}")

        movements = []
        # 清空地图上的玩家标记 (log this action)
        logger.debug("Clearing player markers from map before movement.")
        for x in range(MAP_SIZE):
            for y in range(MAP_SIZE):
                if self.map_data[x][y] in [str(i) for i in range(1, PLAYER_COUNT + 1)]:
                    self.map_data[x][y] = " "

        for player_id in ordered_players:
            # 每个玩家分别循环一次

            # 告知玩家当前地图情况
            self.safe_execute(player_id, "pass_position_data", self.player_positions)
            logger.debug("Sending current map to player {player_id}.")
            
            # 获取当前位置
            current_pos = self.player_positions[player_id]
            logger.debug(
                f"Requesting movement from Player {player_id} at {current_pos}"
            )

            # 获取移动方向
            directions = self.safe_execute(player_id, "walk")

            if not isinstance(directions, tuple):
                logger.error(
                    f"Player {player_id} returned invalid directions type: {type(directions)}. No movement."
                )
                self.suspend_game(
                    "player_ruturn_ERROR", player_id, "walk",
                    f"Returned invalid directions type: {type(directions)}"
                    )

            # 最多移动3步
            steps = len(directions)
            if steps > 3:
                logger.error(
                    f"Player {player_id} returned invalid directions length: {len(directions)}. No movement."
                )
                self.suspend_game(
                    "player_ruturn_ERROR", player_id, "walk",
                    f"Returned invalid directions length: {len(directions)}"
                )

            new_pos = current_pos

            # 默认directions合法
            # 保留valid_moves，最后用于格式化显示
            valid_moves = []
            logger.debug(f"Player {player_id} requested moves: {directions}")
            for i in range(steps):
                # 处理每一步
                if not isinstance(directions[i], str):
                    logger.error(
                        f"Player {player_id} returned invalid direction type: {type(directions[i])}. i_index: {i}"
                    )
                    self.suspend_game(
                        "player_ruturn_ERROR", player_id, "walk",
                        f"Returned invalid direction type: {type(directions[i])}. i_index: {i}"
                    )
    
                direction = directions[i].lower()

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
                    # 无效移动，报错
                    logger.error(
                        f"Player {player_id} attempted invalid move: {direction}. i_index: {i}"
                    )
                    self.suspend_game(
                        "player_ruturn_ERROR", player_id, "walk",
                        f"Attempted invalid move: {direction}. i_index: {i}"
                    )

                # 检查是否与其他玩家重叠
                if new_pos in [
                    self.player_positions[pid]
                    for pid in range(1, PLAYER_COUNT + 1)
                    if pid != player_id
                ]:
                    # 回退到上一个位置
                    logger.error(
                        f"Player {player_id} attempted to move to occupied position: {new_pos}. i_index: {i}"
                    )
                    self.suspend_game(
                        "player_ruturn_ERROR", player_id, "walk",
                        f"Attempted to move to occupied position: {new_pos}. i_index: {i}"
                    )


            # 更新玩家位置
            logger.info(
                f"Movement - Player {player_id}: {current_pos} -> {new_pos} via {valid_moves}"
            )
            self.player_positions[player_id] = new_pos
            x, y = new_pos
            self.map_data[x][y] = str(player_id)  # Place marker after all checks

            movements.append(
                {
                    "player_id": player_id,
                    "requested_moves": list(directions),  # Log requested moves
                    "executed_moves": valid_moves,  # Log executed moves
                    "final_position": new_pos,
                }
            )

        # 更新所有玩家的地图
        logger.debug("Updating all players with the new map state and data of positions.")
        for player_id in range(1, PLAYER_COUNT + 1):
            # 传递给玩家两种数据
            self.safe_execute(player_id, "pass_position_data", self.player_positions)
            self.safe_execute(player_id, "pass_map", self.map_data)

        # 记录移动
        self.log_public_event(
            {"type": "movement", "round": self.current_round, "movements": movements}
        )
        logger.info("Movement phase complete.")

        # 面向前端的记录
        self.battle_observer.make_snapshot("referee", "Movement phase complete.")
        self.battle_observer.make_snapshot("move", self.player_positions)

    def conduct_limited_speech(self):
        """进行有限范围发言（只有在听力范围内的玩家能听到）"""
        # 从队长开始，按编号顺序发言
        ordered_players = [
            (i - 1) % PLAYER_COUNT + 1
            for i in range(self.leader_index, self.leader_index + PLAYER_COUNT)
        ]
        logger.debug(f"Limited speech order: {ordered_players}")

        speeches = []
        for speaker_id in ordered_players:
            logger.debug(f"Requesting limited speech from Player {speaker_id}")
            speech = self.safe_execute(speaker_id, "say")

            if not isinstance(speech, str):
                logger.error(
                    f"Player {speaker_id} returned non-string speech: {type(speech)}.",
                    exc_info=True,  # Include traceback in log
                    )
                self.suspend_game(
                    "player_ruturn_ERROR", speaker_id, "say",
                    f"Returned non-string speech: {type(speech)} during limited speech"
                )

            logger.info(
                f"Limited Speech - Player {speaker_id}: {speech[:100]}{'...' if len(speech) > 100 else ''}"
            )
            self.battle_observer.make_snapshot(f"player{speaker_id}",f"{speech[:100]}{'...' if len(speech) > 100 else ''}")
            speeches.append((speaker_id, speech))

            # 确定能听到的玩家
            hearers = self.get_players_in_hearing_range(speaker_id)
            logger.debug(f"Player {speaker_id}'s speech heard by: {hearers}")

            # 通知能听到的玩家
            for hearer_id in hearers:
                if hearer_id != speaker_id:  # 不需要通知发言者自己
                    self.safe_execute(hearer_id, "pass_message", (speaker_id, speech))

        # 记录有限范围发言
        self.log_public_event(
            {
                "type": "limited_speech",
                "round": self.current_round,
                # "speeches": speeches,  这里的speech不能人尽皆知
            }
        )
        logger.info("Limited Speech phase complete.")
        self.battle_observer.make_snapshot("referee", "Limited Speech phase complete.")

    def get_players_in_hearing_range(self, speaker_id: int) -> List[int]:
        """获取能听到指定玩家发言的所有玩家ID (修改版，原版的“曼哈顿距离”不符合游戏规则)"""
        hearers = []
        speaker_x, speaker_y = self.player_positions[speaker_id]

        for player_id in range(1, PLAYER_COUNT + 1):
            player_x, player_y = self.player_positions[player_id]

            # 计算水平/垂直距离的最大值
            distance = max(abs(player_x - speaker_x), abs(player_y - speaker_y))

            # 获取角色和对应的听力范围
            role = self.roles[player_id]
            hearing_range = HEARING_RANGE.get(role, 1)

            # 如果在听力范围内，加入听者列表
            # 解释：如果上面的水平/垂直距离的最大值不大于对应角色的 HEARING_RANGE 那就可以听到
            if distance <= hearing_range:
                hearers.append(player_id)

        return hearers

    def conduct_public_vote(self, mission_members: List[int]) -> int:
        """
        进行公开投票，决定是否执行任务
        返回支持票数
        """
        votes = {}
        logger.debug(f"Requesting public votes for team: {mission_members}")
        for player_id in range(1, PLAYER_COUNT + 1):
            vote = self.safe_execute(player_id, "mission_vote1")

            # 确保投票结果是布尔值
            if not isinstance(vote, bool):
                logger.error(
                    f"Player {player_id} returned non-bool public vote: {type(vote)}.",
                    exc_info=True,  # Include traceback in log
                    )
                self.suspend_game(
                    "player_ruturn_ERROR", player_id, "mission_vote1", 
                    f"Returned non-bool public vote: {type(vote)}"
                )

            votes[player_id] = vote
            logger.debug(
                f"Public Vote - Player {player_id}: {'Approve' if vote else 'Reject'}"
            )
            self.battle_observer.make_snapshot(f"player{player_id}", f"{'Approve' if vote else 'Reject'}")

        # 统计支持票
        approve_count = sum(1 for v in votes.values() if v)

        # 记录投票结果
        self.log_public_event(
            {
                "type": "public_vote",
                "round": self.current_round,
                "votes": votes,
                "approve_count": approve_count,
                "result": (
                    "approved"
                    if approve_count >= (PLAYER_COUNT // 2 + 1)
                    else "rejected"
                ),
            }
        )
        logger.info("Public Vote phase complete.")
        return approve_count

    def execute_mission(self, mission_members: List[int]) -> bool:
        """
        执行任务，返回任务是否成功
        """
        votes = {}
        fail_votes = 0
        logger.info(
            f"Executing Mission {self.current_round} with members: {mission_members}"
        )
        self.battle_observer.make_snapshot("referee", f"Executing Mission {self.current_round} with members: {mission_members}")
        logger.debug("Requesting mission execution votes (vote2).")

        for player_id in mission_members:
            vote = self.safe_execute(player_id, "mission_vote2")

            # 确保投票结果是布尔值
            if not isinstance(vote, bool):
                logger.error(
                    f"Player {player_id} returned non-bool mission vote: {type(vote)}.",
                    exc_info=True
                    )
                self.suspend_game(
                    "player_ruturn_ERROR", player_id, "mission_vote2",
                    f"Returned non-bool mission vote: {type(vote)}"
                )

            # 检查蓝方投失败票
            if not vote and self.roles[player_id] in BLUE_ROLES:
                logger.error(
                    f"Blue player {player_id} voted against execution.",
                    exc_info=True
                    )
                self.suspend_game(
                    "player_ruturn_ERROR", player_id, "mission_vote2",
                    f"Blue player {player_id} voted against execution."
                )

            votes[player_id] = vote
            logger.debug(
                f"Mission Vote - Player {player_id} ({self.roles[player_id]}): {'Success' if vote else 'Fail'}"
            )

            # 统计失败票
            if not vote:
                fail_votes += 1

        # 判断任务结果
        # 第4轮(索引3)为保护轮，需要至少2票失败；其他轮次只需1票失败
        is_fourth_round = self.current_round == 4
        required_fails = (
            2 if is_fourth_round and PLAYER_COUNT >= 7 else 1
        )  # Standard Avalon rule for 7+ players on round 4
        mission_success = fail_votes < required_fails

        logger.info(
            f"Mission Execution: {fail_votes} Fail votes submitted. Required fails for failure: {required_fails}. Result: {'Success' if mission_success else 'Fail'}"
        )
        self.battle_observer.make_snapshot("referee", f"Mission Execution: {fail_votes} Fail votes submitted. Required fails for failure: {required_fails}. Result: {'Success' if mission_success else 'Fail'}")
        # 记录任务执行结果（匿名）
        self.log_public_event(
            {
                "type": "mission_execution",
                "round": self.current_round,
                "fail_votes": fail_votes,
                "success": mission_success,
            }
        )

        return mission_success

    def assassinate_phase(self) -> bool:
        """
        刺杀阶段，返回刺杀是否成功（刺中梅林）
        """
        logger.info("--- Starting Assassination Phase ---")
        self.battle_observer.make_snapshot("referee","--- Starting Assassination Phase ---")
        # 找到刺客
        assassin_id = None
        for player_id, role in self.roles.items():
            if role == "Assassin":
                assassin_id = player_id
                break

        if not assassin_id:
            logger.error(
                f"No Assassin found!",
                exc_info=True,  # Include traceback in log
            )
            self.suspend_game(
                "critical_referee_ERROR", 0, "assassinate_phase", "no assassin found"
            )

        logger.info(f"Assassin (Player {assassin_id}) is choosing a target.")
        self.battle_observer.make_snapshot(f"player{assassin_id}","choosing a target.")
        # 刺客选择目标
        target_id = self.safe_execute(assassin_id, "assass")
        logger.debug(f"Assassin {assassin_id} chose target: {target_id}")

        # 确保目标是有效玩家ID
        if not isinstance(target_id, int) or target_id < 1 or target_id > PLAYER_COUNT:
            logger.error(
                f"Assassin returned invalid target: {target_id}.",
                exc_info=True,  # Include traceback in log
                )
            self.suspend_game(
                "player_ruturn_ERROR", assassin_id,
                "assass", f"Assassin returned invalid target: {target_id}"
            )
        # 不考虑刺客刺杀自己，因为无法改变游戏结果
        # 我倒是觉得可以做个彩蛋，刺杀自己就是蠢蛋，而且刺杀自己属于代码问题，就是用户的bug
        if target_id == assassin_id:
            logger.error(
                f"Assassin {assassin_id} targeted himself.",
                exc_info=True,  # Include traceback in log
                )
            self.suspend_game(
                "player_ruturn_ERROR", assassin_id, "assass",
                f"""Assassin {assassin_id} targeted himself.  
                    FOOL Assassin! FOOL Assassin! FOOL Assassin! FOOL Assassin!"""
                )


        # 判断是否刺中梅林
        target_role = self.roles[target_id]
        success = target_role == "Merlin"
        logger.info(
            f"Assassination: Player {assassin_id} targeted Player {target_id} ({target_role}). Result: {'Success' if success else 'Fail'}"
        )
        self.battle_observer.make_snapshot(f"player{assassin_id}",f"Assassination: Player {assassin_id} targeted Player {target_id} ({target_role}). Result: {'Success' if success else 'Fail'}")

        # 记录刺杀结果
        self.log_public_event(
            {
                "type": "assassination",
                "assassin": assassin_id,
                "target": target_id,
                "target_role": self.roles[target_id],
                "success": success,
            }
        )
        logger.info("--- Assassination Phase Complete ---")
        return success

    def run_game(self) -> Dict[str, Any]:
        """
        运行游戏，返回游戏结果
        """
        logger.info(f"===== Starting Game {self.game_id} =====")
        try:
            # 初始化游戏
            self.init_game()

            # 夜晚阶段
            self.night_phase()

            # 任务阶段
            while (
                self.blue_wins < 3
                and self.red_wins < 3
                and self.current_round < MAX_MISSION_ROUNDS
            ):
                self.run_mission_round()

            # 游戏结束判定
            logger.info("===== Game Over =====")
            self.battle_observer.make_snapshot('referee','===== Game Over =====')
            logger.info(
                f"Final Score: Blue {self.blue_wins} - Red {self.red_wins} after {self.current_round} rounds."
            )
            self.battle_observer.make_snapshot('referee',f"Final Score: Blue {self.blue_wins} - Red {self.red_wins} after {self.current_round} rounds.")

            game_result = {
                "blue_wins": self.blue_wins,
                "red_wins": self.red_wins,
                "rounds_played": self.current_round,
                "roles": self.roles,  # Include roles in final result
                "public_log_file": os.path.join(
                    self.data_dir, f"game_{self.game_id}_public.json"
                ),  # Path to log
            }

            # 如果蓝方即将获胜（3轮任务成功），执行刺杀阶段
            if self.blue_wins >= 3:
                logger.info(
                    "Blue team completed 3 missions. Proceeding to assassination."
                )
                self.battle_observer.make_snapshot('referee',"Blue team completed 3 missions. Proceeding to assassination.")
                assassination_success = self.assassinate_phase()

                if assassination_success:
                    # 刺杀成功，红方胜利
                    game_result["winner"] = "red"
                    game_result["win_reason"] = "assassination_success"
                    logger.info("Game Result: Red wins (Assassination Success)")
                    self.battle_observer.make_snapshot('referee',"Game Result: Red wins (Assassination Success)")
                else:
                    # 刺杀失败，蓝方胜利
                    game_result["winner"] = "blue"
                    game_result["win_reason"] = (
                        "missions_complete_and_assassination_failed"
                    )
                    logger.info("Game Result: Blue wins (Assassination Failed)")
                    self.battle_observer.make_snapshot('referee',"Game Result: Blue wins (Assassination Failed)")
            elif self.red_wins >= 3:
                # 红方直接胜利（3轮任务失败）
                game_result["winner"] = "red"
                game_result["win_reason"] = "missions_failed"
                logger.info("Game Result: Red wins (3 Failed Missions)")
                self.battle_observer.make_snapshot('referee',"Game Result: Red wins (3 Failed Missions)")
            ##### 貌似没用 #####
            # else:
            #     # 达到最大轮数，根据胜利次数判定
            #     logger.warning(
            #         f"Max rounds ({MAX_MISSION_ROUNDS}) reached without 3 wins for either team."
            #     )
            #     self.battle_observer.make_snapshot('referee',f"Max rounds ({MAX_MISSION_ROUNDS}) reached without 3 wins for either team.")
            #     if self.blue_wins > self.red_wins:
            #         game_result["winner"] = "blue"
            #         game_result["win_reason"] = "more_successful_missions_at_max_rounds"
            #         logger.info(
            #             "Game Result: Blue wins (More missions succeeded at max rounds)"
            #         )
            #         self.battle_observer.make_snapshot('referee',"Game Result: Blue wins (More missions succeeded at max rounds)")
            #     else:  # Includes draw in mission wins, red wins draws
            #         game_result["winner"] = "red"
            #         game_result["win_reason"] = (
            #             "more_or_equal_failed_missions_at_max_rounds"
            #         )
            #         logger.info(
            #             "Game Result: Red wins (More or equal missions failed at max rounds)"
            #         )
            #         self.battle_observer.make_snapshot('referee',"Game Result: Red wins (More or equal missions failed at max rounds)")

            # 记录游戏结果
            self.log_public_event({"type": "game_end", "result": game_result})
            logger.info(f"===== Game {self.game_id} Finished =====")
            self.battle_observer.make_snapshot('referee',f"===== Game {self.game_id} Finished =====")
            return game_result

        except Exception as e:  # suspend_game 抛出的错误导到这里
            logger.error(
                f"Critical error during game {self.game_id}: {str(e)}", exc_info=True
            )
            # traceback.print_exc() # Already logged with exc_info=True
            return {
                "error": f"Critical Error: {str(e)}",
                "blue_wins": self.blue_wins,
                "red_wins": self.red_wins,
                "rounds_played": self.current_round,
                "roles": self.roles,
                "public_log_file": os.path.join(
                    self.data_dir, f"game_{self.game_id}_public.json"
                ),
            }

    def safe_execute(self, player_id: int, method_name: str, *args, **kwargs):
        """
        安全执行玩家代码，处理可能的异常
        """
        player = self.players.get(player_id)
        if not player:
            logger.error(
                f"Attempted to execute method '{method_name}' for non-existent player {player_id}"
            )
            

        method = getattr(player, method_name, None)
        if not method or not callable(method):
            logger.error(
                f"Method '{method_name}' not found or not callable in player {player_id} ({self.roles.get(player_id, 'Unknown Role')})"
            )
            # Provide default behavior based on method?
            if method_name == "mission_vote1":
                return random.choice([True, False])
            if method_name == "mission_vote2":
                return (
                    self.roles.get(player_id) not in RED_ROLES
                )  # Default based on role
            if method_name == "decide_mission_member":
                return self.random_select_members(
                    args[0]
                )  # args[0] should be member_count
            if method_name == "assass":
                return random.choice(
                    [i for i in range(1, PLAYER_COUNT + 1) if i != player_id]
                )
            if method_name == "say":
                return "..."
            if method_name == "walk":
                return ()
            if method_name == "pass_message":
                return None
            if method_name == "pass_map":
                return None
            if method_name == "pass_position_data":
                return None
            return None

        try:
            # 设置当前上下文
            set_current_context(player_id, self.game_id)
            logger.debug(
                f"Executing Player {player_id}.{method_name} with args: {args}, kwargs: {kwargs}"
            )

            start_time = time.time()
            # Capture stdout/stderr from player code if needed
            # stdout_capture = StringIO()
            # stderr_capture = StringIO()
            # with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            result = method(*args, **kwargs)
            execution_time = time.time() - start_time

            # player_stdout = stdout_capture.getvalue()
            # player_stderr = stderr_capture.getvalue()
            # if player_stdout: logger.debug(f"Player {player_id} stdout: {player_stdout.strip()}")
            # if player_stderr: logger.warning(f"Player {player_id} stderr: {player_stderr.strip()}")

            logger.debug(
                f"Player {player_id}.{method_name} returned: {result} (took {execution_time:.4f}s)"
            )

            # 检查执行时间
            # This check is just a warning
            if execution_time > 3:  # Lowered threshold for warning
                logger.warning(
                    f"Player {player_id} ({self.roles.get(player_id)}) method {method_name} took {execution_time:.2f} seconds (potential timeout issue)"
                )

            return result

        except Exception as e:  # 玩家代码运行过程中报错
            logger.error(
                f"Error executing Player {player_id} ({self.roles.get(player_id)}) method '{method_name}': {str(e)}",
                exc_info=True,  # Include traceback in log
            )
            self.suspend_game(
                "critical_player_ERROR", player_id, method_name, str(e)
            )
            
    def log_public_event(self, event: Dict[str, Any]):
        """记录公共事件到日志"""
        # 添加时间戳
        event["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        event["round"] = self.current_round  # Ensure round number is always present

        logger.debug(f"Logging public event: {event}")
        # 添加到内存中的日志
        self.public_log.append(event)

        # 写入公共日志文件
        public_log_file = os.path.join(
            self.data_dir, f"game_{self.game_id}_public.json"
        )
        try:
            with open(public_log_file, "w", encoding="utf-8") as f:
                json.dump(self.public_log, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error writing public log: {str(e)}")

    def suspend_game(
        self,
        game_error_type: str,
        # - 来自服务器 referee 的错误 - "critical_referee_ERROR"
        # - 来自用户的代码出错 - "critical_player_ERROR"
        # - 用户代码的 return 不符合要求 - "player_return_ERROR"
        error_code_pid: int,  # 服务器出错则为0
        error_code_method_name: str,
        error_msg: str
    ):
        "一键中止游戏。代替前文反反复复出现的堆积如山的 raise RuntimeError。"

        SUSPEND_BROADCAST_MSG = (
            f"Error executing Player {error_code_pid} method {error_code_method_name}: "
            + error_msg + ". Game suspended."
        ) if error_code_pid > 0 else (
            f"Referee error during {error_code_method_name}: {error_msg}. Game suspended."
        )

        # 1. 给公有库添加报错信息
        self.log_public_event({
            "type": game_error_type,
            "error_code_pid": error_code_pid,
            "error_code_method": error_code_method_name,
            "error_msg": error_msg
        })

        # 2. 给observer添加报错信息
        self.battle_observer.make_snapshot("referee", SUSPEND_BROADCAST_MSG)

        # 3. 抛出错误，终止游戏
        raise RuntimeError(SUSPEND_BROADCAST_MSG)
