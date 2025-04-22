"""
裁判系统 - 负责执行游戏规则和管理游戏状态
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
import importlib.util
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime

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
                json.dump({"logs": []}, f)
        logger.info(f"Public and private log files initialized in {self.data_dir}")

    def load_player_code(self, player_modules: Dict[int, Any]):
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
                self.safe_execute(player_id, "set_player_index", player_id)
                logger.info(f"Player {player_id} code loaded and instance created.")
            except Exception as e:
                logger.error(f"Error loading player {player_id} code: {str(e)}")
                traceback.print_exc()
                # Consider how to handle player load failure - maybe replace with a default bot?

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
        if percival_id:
            percival_id = percival_id[0]
            targets = {
                r: pid for pid, r in self.roles.items() if r in ["Merlin", "Morgana"]
            }
            logger.debug(
                f"Sending Merlin/Morgana info to Percival (Player {percival_id}): {targets}"
            )
            self.safe_execute(percival_id, "pass_role_sight", targets)

        # 记录夜晚阶段完成
        self.log_public_event({"type": "night_phase_complete"})
        logger.info("Night Phase complete.")

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
            mission_members = self.safe_execute(
                self.leader_index, "decide_mission_member", member_count
            )
            logger.debug(f"Leader {self.leader_index} proposed: {mission_members}")

            # 验证队员数量和有效性 (Adding logs for validation steps)
            if (
                not isinstance(mission_members, list)
                or len(mission_members) != member_count
            ):
                logger.warning(
                    f"Player {self.leader_index} returned invalid mission members: {mission_members}. Selecting randomly."
                )
                mission_members = self.random_select_members(member_count)
                logger.info(f"Randomly selected team: {mission_members}")
            else:
                valid_members = []
                invalid_found = False
                for member in mission_members:
                    if isinstance(member, int) and 1 <= member <= PLAYER_COUNT:
                        if (
                            member not in valid_members
                        ):  # Prevent duplicates from player
                            valid_members.append(member)
                        else:
                            logger.warning(
                                f"Leader {self.leader_index} proposed duplicate member {member}. Ignored."
                            )
                            invalid_found = True
                    else:
                        logger.warning(
                            f"Leader {self.leader_index} proposed invalid member ID {member}. Ignored."
                        )
                        invalid_found = True

                if len(valid_members) != member_count or invalid_found:
                    logger.warning(
                        f"Correcting team proposal from leader {self.leader_index}. Original: {mission_members}"
                    )
                    # If not enough valid members, fill randomly
                    current_members = set(valid_members)
                    needed = member_count - len(valid_members)
                    if needed > 0:
                        all_players = list(range(1, PLAYER_COUNT + 1))
                        random.shuffle(all_players)
                        for p in all_players:
                            if p not in current_members:
                                valid_members.append(p)
                                current_members.add(p)
                                if len(valid_members) == member_count:
                                    break
                    # Ensure correct count even if too many valid were initially proposed (due to duplicates ignored)
                    mission_members = valid_members[:member_count]
                    logger.info(f"Corrected/Completed team: {mission_members}")
                else:
                    mission_members = valid_members  # Use the validated list
                    logger.info(
                        f"Leader {self.leader_index} proposed valid team: {mission_members}"
                    )

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
            self.conduct_global_speech()

            # 3. 玩家移动
            logger.info("Starting Movement phase.")
            self.conduct_movement()

            # 4. 第二轮发言（有限听力范围）
            logger.info("Starting Limited Speech phase.")
            self.conduct_limited_speech()

            # 5. 公投表决
            logger.info("Starting Public Vote phase.")
            approve_votes = self.conduct_public_vote(mission_members)
            logger.info(
                f"Public vote result: {approve_votes} Approve vs {PLAYER_COUNT - approve_votes} Reject."
            )

            if approve_votes >= (PLAYER_COUNT // 2 + 1):  # 过半数同意
                logger.info("Team Approved. Executing mission.")
                # 执行任务
                mission_success = self.execute_mission(mission_members)
                break  # Exit vote loop
            else:
                logger.info("Team Rejected.")
                # 否决，更换队长
                old_leader = self.leader_index
                self.leader_index = self.leader_index % PLAYER_COUNT + 1
                logger.info(f"Leader changed from {old_leader} to {self.leader_index}.")

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

        # 更新队长 (Moved outside the loop, happens once per mission round end)
        # self.leader_index = self.leader_index % PLAYER_COUNT + 1 # Already updated on rejection, needs careful thought if approved
        # Let's update leader *after* the mission result is logged, regardless of approval/rejection outcome for simplicity
        old_leader_for_next_round = self.leader_index
        self.leader_index = self.leader_index % PLAYER_COUNT + 1
        logger.debug(
            f"Leader for next round will be {self.leader_index} (previous was {old_leader_for_next_round})"
        )
        logger.info(f"--- End of Mission Round {self.current_round} ---")

    def random_select_members(self, member_count: int) -> List[int]:
        """随机选择指定数量的队员"""
        logger.debug(f"Randomly selecting {member_count} members.")
        all_players = list(range(1, PLAYER_COUNT + 1))
        random.shuffle(all_players)
        return all_players[:member_count]

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

            if not isinstance(speech, str):
                logger.warning(
                    f"Player {player_id} returned non-string speech: {type(speech)}. Using default."
                )
                speech = "..."  # 默认发言

            logger.info(
                f"Global Speech - Player {player_id}: {speech[:100]}{'...' if len(speech) > 100 else ''}"
            )
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
            # 获取当前位置
            current_pos = self.player_positions[player_id]
            logger.debug(
                f"Requesting movement from Player {player_id} at {current_pos}"
            )

            # 获取移动方向
            directions = self.safe_execute(player_id, "walk")

            if not isinstance(directions, tuple) and not isinstance(
                directions, list
            ):  # Allow list too
                logger.warning(
                    f"Player {player_id} returned invalid directions type: {type(directions)}. No movement."
                )
                directions = ()

            # 最多移动3步
            steps = min(len(directions), 3)
            new_pos = current_pos

            valid_moves = []
            logger.debug(f"Player {player_id} requested moves: {directions[:steps]}")
            for i in range(steps):
                if i >= len(directions):
                    break

                direction = (
                    directions[i].lower() if isinstance(directions[i], str) else ""
                )

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
                if new_pos in [
                    self.player_positions[pid]
                    for pid in range(1, PLAYER_COUNT + 1)
                    if pid != player_id
                ]:
                    # 回退到上一个位置
                    new_pos = (x, y)
                    valid_moves.pop()  # 移除最后一个无效移动
                    break

            # 更新玩家位置
            if new_pos != current_pos:
                logger.info(
                    f"Movement - Player {player_id}: {current_pos} -> {new_pos} via {valid_moves}"
                )
            else:
                logger.info(
                    f"Movement - Player {player_id}: No valid movement from {current_pos} with request {directions[:steps]}"
                )

            self.player_positions[player_id] = new_pos
            x, y = new_pos
            self.map_data[x][y] = str(player_id)  # Place marker after all checks

            movements.append(
                {
                    "player_id": player_id,
                    "requested_moves": list(directions[:steps]),  # Log requested moves
                    "executed_moves": valid_moves,  # Log executed moves
                    "final_position": new_pos,
                }
            )

        # 更新所有玩家的地图
        logger.debug("Updating all players with the new map state.")
        for player_id in range(1, PLAYER_COUNT + 1):
            self.safe_execute(player_id, "pass_map", self.map_data)

        # 记录移动
        self.log_public_event(
            {"type": "movement", "round": self.current_round, "movements": movements}
        )
        logger.info("Movement phase complete.")

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
                logger.warning(
                    f"Player {speaker_id} returned non-string speech: {type(speech)}. Using default."
                )
                speech = "..."  # 默认发言

            logger.info(
                f"Limited Speech - Player {speaker_id}: {speech[:100]}{'...' if len(speech) > 100 else ''}"
            )
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
                "speeches": speeches,
            }
        )
        logger.info("Limited Speech phase complete.")

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
        logger.debug(f"Requesting public votes for team: {mission_members}")
        for player_id in range(1, PLAYER_COUNT + 1):
            vote = self.safe_execute(player_id, "mission_vote1")

            # 确保投票结果是布尔值
            if not isinstance(vote, bool):
                logger.warning(
                    f"Player {player_id} returned invalid public vote: {type(vote)}. Assigning random vote."
                )
                vote = random.choice([True, False])

            votes[player_id] = vote
            logger.debug(
                f"Public Vote - Player {player_id}: {'Approve' if vote else 'Reject'}"
            )

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
        logger.debug("Requesting mission execution votes (vote2).")

        for player_id in mission_members:
            vote = self.safe_execute(player_id, "mission_vote2")

            # 确保投票结果是布尔值
            if not isinstance(vote, bool):
                # 红方默认投失败，蓝方默认投成功
                is_evil = self.roles[player_id] in RED_ROLES
                logger.warning(
                    f"Player {player_id} ({self.roles[player_id]}) returned invalid mission vote: {type(vote)}. Defaulting based on role ({'Fail' if is_evil else 'Success'})."
                )
                vote = not is_evil  # True for blue (Success), False for red (Fail)

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
        # 找到刺客
        assassin_id = None
        for player_id, role in self.roles.items():
            if role == "Assassin":
                assassin_id = player_id
                break

        if not assassin_id:
            logger.error("No Assassin found! Skipping assassination.")
            return False  # Cannot assassinate without an assassin

        logger.info(f"Assassin (Player {assassin_id}) is choosing a target.")
        # 刺客选择目标
        target_id = self.safe_execute(assassin_id, "assass")
        logger.debug(f"Assassin {assassin_id} chose target: {target_id}")

        # 确保目标是有效玩家ID
        if not isinstance(target_id, int) or target_id < 1 or target_id > PLAYER_COUNT:
            logger.warning(
                f"Assassin returned invalid target: {target_id}. Choosing random target."
            )
            # 随机选择目标
            possible_targets = [
                i
                for i in range(1, PLAYER_COUNT + 1)
                if self.roles[i] not in RED_ROLES and i != assassin_id
            ]
            if not possible_targets:  # Should not happen if blue won, but safety check
                possible_targets = [
                    i for i in range(1, PLAYER_COUNT + 1) if i != assassin_id
                ]
            target_id = (
                random.choice(possible_targets) if possible_targets else assassin_id
            )  # Avoid error if list empty
            logger.info(f"Randomly selected target: {target_id}")
        elif target_id == assassin_id:
            logger.warning(
                f"Assassin {assassin_id} targeted themselves. Invalid. Choosing random target."
            )
            # Same random logic as above
            possible_targets = [
                i
                for i in range(1, PLAYER_COUNT + 1)
                if self.roles[i] not in RED_ROLES and i != assassin_id
            ]
            if not possible_targets:
                possible_targets = [
                    i for i in range(1, PLAYER_COUNT + 1) if i != assassin_id
                ]
            target_id = (
                random.choice(possible_targets) if possible_targets else assassin_id
            )
            logger.info(f"Randomly selected target: {target_id}")

        # 判断是否刺中梅林
        target_role = self.roles[target_id]
        success = target_role == "Merlin"
        logger.info(
            f"Assassination: Player {assassin_id} targeted Player {target_id} ({target_role}). Result: {'Success' if success else 'Fail'}"
        )

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
            logger.info(
                f"Final Score: Blue {self.blue_wins} - Red {self.red_wins} after {self.current_round} rounds."
            )

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
                assassination_success = self.assassinate_phase()

                if assassination_success:
                    # 刺杀成功，红方胜利
                    game_result["winner"] = "red"
                    game_result["win_reason"] = "assassination_success"
                    logger.info("Game Result: Red wins (Assassination Success)")
                else:
                    # 刺杀失败，蓝方胜利
                    game_result["winner"] = "blue"
                    game_result["win_reason"] = (
                        "missions_complete_and_assassination_failed"
                    )
                    logger.info("Game Result: Blue wins (Assassination Failed)")
            elif self.red_wins >= 3:
                # 红方直接胜利（3轮任务失败）
                game_result["winner"] = "red"
                game_result["win_reason"] = "missions_failed"
                logger.info("Game Result: Red wins (3 Failed Missions)")
            else:
                # 达到最大轮数，根据胜利次数判定
                logger.warning(
                    f"Max rounds ({MAX_MISSION_ROUNDS}) reached without 3 wins for either team."
                )
                if self.blue_wins > self.red_wins:
                    game_result["winner"] = "blue"
                    game_result["win_reason"] = "more_successful_missions_at_max_rounds"
                    logger.info(
                        "Game Result: Blue wins (More missions succeeded at max rounds)"
                    )
                else:  # Includes draw in mission wins, red wins draws
                    game_result["winner"] = "red"
                    game_result["win_reason"] = (
                        "more_or_equal_failed_missions_at_max_rounds"
                    )
                    logger.info(
                        "Game Result: Red wins (More or equal missions failed at max rounds)"
                    )

            # 记录游戏结果
            self.log_public_event({"type": "game_end", "result": game_result})
            logger.info(f"===== Game {self.game_id} Finished =====")
            return game_result

        except Exception as e:
            logger.error(
                f"Critical error during game {self.game_id}: {str(e)}", exc_info=True
            )
            # traceback.print_exc() # Already logged with exc_info=True
            return {
                "error": f"Critical Referee Error: {str(e)}",
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
            return None  # Or raise an error?

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
            # Timeout logic should ideally be handled by a separate process supervisor
            # This check is just a warning
            if execution_time > 3:  # Lowered threshold for warning
                logger.warning(
                    f"Player {player_id} ({self.roles.get(player_id)}) method {method_name} took {execution_time:.2f} seconds (potential timeout issue)"
                )

            return result

        except Exception as e:
            logger.error(
                f"Error executing Player {player_id} ({self.roles.get(player_id)}) method '{method_name}': {str(e)}",
                exc_info=True,  # Include traceback in log
            )
            # traceback.print_exc() # Already logged with exc_info=True
            # Provide default behavior on error too
            if method_name == "mission_vote1":
                return random.choice([True, False])
            if method_name == "mission_vote2":
                return self.roles.get(player_id) not in RED_ROLES
            if method_name == "decide_mission_member":
                return self.random_select_members(args[0])
            if method_name == "assass":
                return random.choice(
                    [i for i in range(1, PLAYER_COUNT + 1) if i != player_id]
                )
            if method_name == "say":
                return f"[Error executing say: {str(e)}]"
            if method_name == "walk":
                return ()
            return None  # Default return on error for other methods

    def log_public_event(self, event: Dict[str, Any]):
        """记录公共事件到日志"""
        # 添加时间戳
        event["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[
            :-3
        ]  # Use datetime with ms
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


def run_avalon_game(
    game_id: str, player_modules: Dict[int, Any], data_dir: str = "./data"
) -> Dict[str, Any]:
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
    logger.info("--- Starting Test Game Run ---")
    # 这里可以加载测试用的Player模块
    from game.baselines import get_all_baseline_codes  # Ensure import is here

    baseline_codes = get_all_baseline_codes()
    player_modules = {}
    player_codes = {}  # Store code content for potential debugging

    for i in range(1, PLAYER_COUNT + 1):
        # Choose different baselines? For now, all basic.
        code_key = "basic_player"  # or "smart_player" or randomly assign
        code_content = baseline_codes[code_key]
        player_codes[i] = code_content
        logger.info(f"Loading {code_key} for Player {i}")

        # 动态创建模块
        module_name = f"player_{i}_module_{int(time.time()*1000)}"  # More unique name
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        if spec is None:
            logger.error(f"Failed to create spec for {module_name}")
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module  # Register module

        # 执行代码
        try:
            exec(code_content, module.__dict__)
            # Check if Player class exists after exec
            if not hasattr(module, "Player"):
                logger.error(
                    f"Code for player {i} executed but 'Player' class not found in module."
                )
                # Handle error - maybe skip this player or use a default?
                continue
            player_modules[i] = module
        except Exception as e:
            logger.error(f"Failed to execute code for player {i}: {e}", exc_info=True)
            # Handle error

    if len(player_modules) != PLAYER_COUNT:
        logger.error(
            f"Could not load all players ({len(player_modules)}/{PLAYER_COUNT}). Aborting test game."
        )
        return

    # 运行游戏
    game_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    data_dir = os.path.join("./data", "test_runs")  # Separate dir for test runs
    os.makedirs(data_dir, exist_ok=True)
    logger.info(f"Running test game with ID: {game_id}")
    result = run_avalon_game(game_id, player_modules, data_dir=data_dir)
    logger.info(f"--- Test Game Run Finished ---")
    # Use logger instead of print for final result
    logger.info(f"Game result: {json.dumps(result, indent=2)}")


def run_single_round(code1, code2):
    """
    执行一场完整的阿瓦隆游戏对决

    Args:
        code1: 玩家1代码内容
        code2: 玩家2代码内容

    Returns:
        tuple: (player1_result, player2_result, result_code)
            player1_result: 玩家1结果描述
            player2_result: 玩家2结果描述
            result_code: 比赛结果代码 ("player1_win", "player2_win", "draw", "error")
    """
    try:
        # 预处理代码，创建玩家实例
        player1_instance = execute_player_code(code1, "player1")
        player2_instance = execute_player_code(code2, "player2")

        if "error" in str(player1_instance) or "error" in str(player2_instance):
            # 如果有玩家代码执行错误
            if "error" in str(player1_instance) and "error" not in str(
                player2_instance
            ):
                return f"执行错误: {player1_instance}", "有效", "player2_win"
            elif "error" not in str(player1_instance) and "error" in str(
                player2_instance
            ):
                return "有效", f"执行错误: {player2_instance}", "player1_win"
            else:
                return (
                    f"执行错误: {player1_instance}",
                    f"执行错误: {player2_instance}",
                    "error",
                )

        # 简化的Avalon对决逻辑 - 基于策略评分
        # 注意：这是一个简化版本，真实的Avalon需要更复杂的实现

        # 假设每个Player类都有一个get_strategy方法返回策略字符串
        try:
            strategy1 = evaluate_strategy(player1_instance, "player1")
            strategy2 = evaluate_strategy(player2_instance, "player2")

            # 比较策略分数决定胜负
            if strategy1 > strategy2:
                return f"策略评分: {strategy1}", f"策略评分: {strategy2}", "player1_win"
            elif strategy2 > strategy1:
                return f"策略评分: {strategy1}", f"策略评分: {strategy2}", "player2_win"
            else:
                return f"策略评分: {strategy1}", f"策略评分: {strategy2}", "draw"

        except Exception as e:
            logging.error(f"策略评估错误: {e}")
            return f"评估错误: {str(e)[:100]}", f"评估错误: {str(e)[:100]}", "error"

    except Exception as e:
        logging.error(f"运行对战时发生错误: {e}", exc_info=True)
        return f"系统错误: {str(e)[:100]}", f"系统错误: {str(e)[:100]}", "error"


def execute_player_code(code_content, player_id):
    """安全执行玩家代码并返回Player实例"""
    try:
        # 创建模块
        module_name = f"player_module_{player_id}"
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        # 重定向标准输出和错误
        stdout = StringIO()
        stderr = StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            # 执行代码
            exec(code_content, module.__dict__)

            # 检查Player类
            if hasattr(module, "Player"):
                return module.Player()
            else:
                return "error: Player类未找到"

    except Exception as e:
        error_msg = traceback.format_exc()
        logging.error(f"执行玩家代码时出错 ({player_id}): {error_msg}")
        return f"error: {str(e)[:100]}"
