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
from copy import deepcopy
import logging
import importlib.util
from datetime import datetime
from .observer import Observer
from .avalon_game_helper import INIT_PRIVA_LOG_DICT
from .restrictor import RESTRICTED_BUILTINS
from .avalon_game_helper import GameHelper
from database.models import Battle
from database.base import db
from database import (
    get_battle_by_id as db_get_battle_by_id,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Referee")

# 导入辅助模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 确保导入成功
# try:
#     from game.avalon_game_helper import set_current_context, set_current_round
# except ImportError:
#     logger.error("Failed to import modules from game.avalon_game_helper")

#     # 可以选择退出或提供默认实现
#     def set_current_context(player_id: int, game_id: str):
#         pass  # 空实现或记录错误

#     def set_current_round(round_: int):
#         pass


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
MAX_EXECUTION_TIME = 100


class GameTerminationError(Exception):
    """Exception raised when game needs to be terminated due to battle status change"""

    pass


class BattleStatusChecker:
    """用于安全检查对战状态的辅助类，不直接依赖Flask上下文"""

    def __init__(self, battle_id):
        """初始化状态检查器"""
        self.battle_id = battle_id
        self.last_known_status = "playing"  # 默认状态
        self.check_interval = 2  # 状态检查间隔（秒）
        self.last_check_time = 0  # 上次检查时间

        # 初始化时立即检查一次状态
        self.get_battle_status(force=True)

    def get_battle_status(self, force=False):
        """
        获取当前对战状态，使用直接SQL查询避免Flask上下文依赖

        参数:
            force (bool): 是否强制检查，忽略时间间隔限制
        """
        current_time = time.time()

        # 如果距离上次检查时间不足check_interval且不是强制检查，则返回上次状态
        if not force and (current_time - self.last_check_time < self.check_interval):
            return self.last_known_status

        self.last_check_time = current_time

        try:
            # 尝试多种方法获取对战状态

            # 方法1: 通过battle_manager获取（如果可访问）
            try:
                from utils.battle_manager_utils import get_battle_manager

                battle_manager = get_battle_manager()
                if battle_manager:
                    status = battle_manager.get_battle_status(self.battle_id)
                    if status:
                        self.last_known_status = status
                        logger.debug(
                            f"从battle_manager获取对战 {self.battle_id} 状态: {status}"
                        )
                        return status
            except Exception as e:
                logger.debug(f"无法从battle_manager获取状态: {str(e)}")

            # 方法2: 使用原始SQL查询
            import sqlite3
            from os import path

            # 尝试多个可能的数据库位置
            possible_paths = [
                "./database.sqlite",
                "./platform/database.sqlite",
                "../database.sqlite",
                "../../database.sqlite",
                os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), "../../database.sqlite"
                ),
            ]

            db_path = None
            for p in possible_paths:
                if path.exists(p):
                    db_path = p
                    break

            if not db_path:
                logger.warning(f"无法找到数据库文件进行状态检查")
                return self.last_known_status

            # 连接数据库
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 执行查询
            cursor.execute("SELECT status FROM battles WHERE id = ?", (self.battle_id,))
            result = cursor.fetchone()

            # 关闭连接
            conn.close()

            if result:
                self.last_known_status = result[0]
                logger.debug(f"从数据库获取对战 {self.battle_id} 状态: {result[0]}")
                return result[0]
            else:
                logger.warning(f"在数据库中找不到对战 {self.battle_id}")

        except Exception as e:
            logger.error(f"检查对战状态时出错: {str(e)}")

        return self.last_known_status

    def should_abort(self):
        """检查对战是否应该中止"""
        status = self.get_battle_status(force=True)  # 强制刷新状态
        should_stop = status not in ["playing", "waiting"]

        if should_stop:
            logger.warning(f"检测到对战 {self.battle_id} 状态为 '{status}'，将中止游戏")

        return should_stop


class AvalonReferee:
    def __init__(
        self,
        game_id: str,
        battle_observer: Observer,
        data_dir: str = "./data",
        player_code_paths: Dict[int, str] = None,
    ):
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
        # 为这个referee创建一个专用的GameHelper实例
        self.game_helper = GameHelper(data_dir=data_dir)
        self.game_helper.game_session_id = game_id  # 直接设置game_id

        # 创建数据目录
        os.makedirs(os.path.join(data_dir), exist_ok=True)

        # 初始化日志文件
        self.init_logs()

        # Observer实例
        self.battle_observer = battle_observer

        # 加载玩家代码
        if player_code_paths:
            player_modules = self._load_codes(player_code_paths)
            self.load_player_codes(player_modules)

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

        for player_id, code_path in player_codes.items():
            # 创建唯一模块名
            module_name = f"player_{player_id}_module_{int(time.time()*1000)}"
            logger.info(f"为玩家 {player_id} 创建模块: {module_name}")

            try:
                # 检查code_path是否是文件路径
                if isinstance(code_path, str) and os.path.exists(code_path):
                    # 如果是文件路径，读取文件内容
                    try:
                        with open(code_path, "r", encoding="utf-8") as f:
                            code_content = f.read()
                        logger.info(f"从文件 {code_path} 加载玩家 {player_id} 代码")
                    except Exception as e:
                        logger.error(f"读取玩家 {player_id} 代码文件时出错: {str(e)}")
                        continue
                else:
                    # 如果不是文件路径，假设是直接传递的代码内容
                    code_content = code_path

                # 创建模块规范
                spec = importlib.util.spec_from_loader(module_name, loader=None)
                if spec is None:
                    logger.error(f"为 {module_name} 创建规范失败")
                    continue

                # 从规范创建模块
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module  # 注册模块

                # 执行代码（限制 builtins）
                module.__dict__["__builtins__"] = RESTRICTED_BUILTINS
                exec(code_content, module.__dict__)

                # 检查Player类是否存在
                if not hasattr(module, "Player"):
                    logger.error(f"玩家 {player_id} 的代码已执行但未找到 'Player' 类")
                    self.suspend_game(
                        "critical_player_ERROR",
                        player_id,
                        "Player",
                        f"玩家 {player_id} 的代码已执行但未找到 'Player' 类",
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
                        exc_info=True,
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
        self.battle_observer.make_snapshot("RoleAssign", self.roles)
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
        self.battle_observer.make_snapshot("DefaultPositions", self.player_positions)

        # 通知所有玩家地图信息
        for player_id in range(1, PLAYER_COUNT + 1):
            logger.debug(f"Sending map data to player {player_id}")
            self.safe_execute(player_id, "pass_map", deepcopy(self.map_data))
        logger.info("Map initialized and sent to players.")

    def night_phase(self):
        """夜晚阶段：各角色按照视野规则获取信息"""
        logger.info("Starting Night Phase.")
        self.battle_observer.make_snapshot("NightStart", "Starting Night Phase.")
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
        self.battle_observer.make_snapshot("NightEnd", "--- Night phase complete ---")

    def run_mission_round(self):
        """执行一轮任务"""
        self.current_round += 1
        # 首先设置当前轮次
        self.game_helper.set_current_round(self.current_round)
        # 然后重置LLM限制
        self.game_helper.reset_llm_limit(self.current_round)

        member_count = MISSION_MEMBER_COUNT[self.current_round - 1]
        vote_round = 0
        mission_success = None

        logger.info(f"--- Starting Mission Round {self.current_round} ---")
        self.battle_observer.make_snapshot("RoundStart", self.current_round)
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

        # 检查对战状态
        def check_battle_status():
            """检查对战状态，如果不是playing或waiting则抛出异常"""
            if (
                hasattr(self, "battle_status_checker")
                and self.battle_status_checker is not None
            ):
                if self.battle_status_checker.should_abort():
                    battle_status = self.battle_status_checker.get_battle_status(
                        force=True
                    )
                    logger.warning(
                        f"Mission round aborted: Battle state changed to '{battle_status}'"
                    )
                    raise GameTerminationError(
                        f"Battle status changed to '{battle_status}'"
                    )

        # 初始状态检查
        try:
            check_battle_status()
        except GameTerminationError as e:
            raise e

        # 任务循环，直到有效执行或达到最大投票次数
        while mission_success is None and vote_round < MAX_VOTE_ROUNDS:
            vote_round += 1
            logger.info(
                f"Starting Vote Round {vote_round} for Mission {self.current_round}."
            )

            # 添加状态检查：队长选择前
            try:
                check_battle_status()
            except GameTerminationError as e:
                raise e

            # 1. 队长选择队员
            logger.info(f"Leader {self.leader_index} is proposing a team.")

            mission_members = self.safe_execute(
                self.leader_index, "decide_mission_member", member_count
            )
            logger.debug(f"Leader {self.leader_index} proposed: {mission_members}")

            # 验证队员数量和有效性
            if not isinstance(mission_members, list):
                logger.error(
                    f"Leader {self.leader_index} returned non-list: {type(mission_members)}.",
                    exc_info=True,  # Include traceback in log
                )
                self.suspend_game(
                    "player_ruturn_ERROR",
                    self.leader_index,
                    "decide_mission_member",
                    f"Leader {self.leader_index} returned non-list: {type(mission_members)}",
                )

            else:
                valid_members = []
                for member in mission_members:
                    if isinstance(member, int) and 1 <= member <= PLAYER_COUNT:
                        if member not in valid_members:  # 防止队员重复
                            valid_members.append(member)
                        else:
                            logger.error(
                                f"Leader {self.leader_index} proposed duplicate member {member}.",
                                exc_info=True,  # Include traceback in log
                            )
                            self.suspend_game(
                                "player_ruturn_ERROR",
                                self.leader_index,
                                "decide_mission_member",
                                f"Leader {self.leader_index} proposed duplicate member: {mission_members}",
                            )
                    else:
                        logger.error(
                            f"Leader {self.leader_index} proposed invalid member {member}.",
                            exc_info=True,  # Include traceback in log
                        )
                        self.suspend_game(
                            "player_ruturn_ERROR",
                            self.leader_index,
                            "decide_mission_member",
                            f"Leader {self.leader_index} proposed invalid member: {mission_members}",
                        )

                if len(valid_members) != member_count:
                    logger.error(
                        f"Leader {self.leader_index} proposed too many(few) members: {len(valid_members)}.",
                        exc_info=True,  # Include traceback in log
                    )
                    self.suspend_game(
                        "player_ruturn_ERROR",
                        self.leader_index,
                        "decide_mission_member",
                        f"Leader {self.leader_index} proposed too many(few) members: {mission_members}",
                    )

                else:
                    mission_members = valid_members  # Use the validated list
                    logger.info(
                        f"Leader {self.leader_index} proposed team: {mission_members}"
                    )

                self.battle_observer.make_snapshot(
                    "TeamPropose",
                    mission_members,
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
            self.battle_observer.make_snapshot("Leader", self.leader_index)
            self.log_public_event(
                {
                    "type": "team_proposed",
                    "round": self.current_round,
                    "vote_round": vote_round,
                    "leader": self.leader_index,
                    "members": mission_members,
                }
            )

            # 添加状态检查：第一轮发言前
            try:
                check_battle_status()
            except GameTerminationError as e:
                raise e

            # 2. 第一轮发言（全图广播）
            logger.info("Starting Global Speech phase.")
            try:
                self.conduct_global_speech()
            except GameTerminationError as e:
                raise e

            # 添加状态检查：玩家移动前
            try:
                check_battle_status()
            except GameTerminationError as e:
                raise e

            # 3. 玩家移动
            logger.info("Starting Movement phase.")
            try:
                self.conduct_movement()
            except GameTerminationError as e:
                raise e

            # 添加状态检查：第二轮发言前
            try:
                check_battle_status()
            except GameTerminationError as e:
                raise e

            # 4. 第二轮发言（有限听力范围）
            logger.info("Starting Limited Speech phase.")
            try:
                self.conduct_limited_speech()
            except GameTerminationError as e:
                raise e

            # 添加状态检查：公投表决前
            try:
                check_battle_status()
            except GameTerminationError as e:
                raise e

            # 5. 公投表决
            logger.info("Starting Public Vote phase.")
            approve_votes = self.conduct_public_vote(mission_members)
            logger.info(
                f"Public vote result: {approve_votes} Approve vs {PLAYER_COUNT - approve_votes} Reject."
            )
            self.battle_observer.make_snapshot(
                "PublicVoteResult", [approve_votes, PLAYER_COUNT - approve_votes]
            )

            if approve_votes >= (PLAYER_COUNT // 2 + 1):  # 过半数同意
                logger.info("Team Approved. Executing mission.")
                self.battle_observer.make_snapshot(
                    "MissionApproved", [self.current_round, mission_members]
                )

                # 添加状态检查：执行任务前
                try:
                    check_battle_status()
                except GameTerminationError as e:
                    raise e

                # 执行任务
                try:
                    mission_success = self.execute_mission(mission_members)
                except GameTerminationError as e:
                    raise e
                break  # 退出循环
            else:
                logger.info("Team Rejected.")
                self.battle_observer.make_snapshot("MissionRejected", "Team Rejected.")
                # 否决，更换队长
                self.game_helper.reset_llm_limit(self.current_round)

                old_leader = self.leader_index
                self.leader_index = self.leader_index % PLAYER_COUNT + 1
                logger.info(f"Leader changed from {old_leader} to {self.leader_index}.")
                self.battle_observer.make_snapshot("Leader", self.leader_index)

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

                # 添加状态检查：特殊情况前
                try:
                    check_battle_status()
                except GameTerminationError as e:
                    raise e

                # 特殊情况：连续5次否决
                if vote_round == MAX_VOTE_ROUNDS:
                    logger.warning(
                        "Maximum vote rounds reached. Forcing mission execution with last proposed team."
                    )
                    self.battle_observer.make_snapshot(
                        "MissionForceExecute",
                        "Maximum vote rounds reached. Forcing mission execution with last proposed team.",
                    )
                    self.log_public_event(
                        {"type": "consecutive_rejections", "round": self.current_round}
                    )

                    # 添加状态检查：强制执行前
                    try:
                        check_battle_status()
                    except GameTerminationError as e:
                        raise e

                    # 强制执行任务
                    try:
                        mission_success = self.execute_mission(mission_members)
                    except GameTerminationError as e:
                        raise e

        # 任务完成后最后检查状态
        try:
            check_battle_status()
        except GameTerminationError as e:
            raise e

        # 记录任务结果
        logger.info(
            f"Mission {self.current_round} Result: {'Success' if mission_success else 'Fail'}"
        )
        self.battle_observer.make_snapshot(
            "MissionResult",
            (self.current_round, ("Success" if mission_success else "Fail")),
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
        self.battle_observer.make_snapshot(
            "ScoreBoard", [self.blue_wins, self.red_wins]
        )

        # 更新队长 (Moved outside the loop, happens once per mission round end)
        old_leader_for_next_round = self.leader_index
        self.leader_index = self.leader_index % PLAYER_COUNT + 1
        logger.debug(
            f"Leader for next round will be {self.leader_index} (previous was {old_leader_for_next_round})"
        )
        self.battle_observer.make_snapshot("RoundEnd", self.current_round)
        logger.info(f"--- End of Mission Round {self.current_round} ---")

    def conduct_global_speech(self):
        """进行全局发言（所有玩家都能听到）"""
        # 添加状态检查
        if (
            hasattr(self, "battle_status_checker")
            and self.battle_status_checker is not None
        ):
            if self.battle_status_checker.should_abort():
                battle_status = self.battle_status_checker.get_battle_status(force=True)
                logger.warning(
                    f"Global speech aborted: Battle state changed to '{battle_status}'"
                )
                raise GameTerminationError(
                    f"Battle status changed to '{battle_status}'"
                )

        speeches = []

        # 从队长开始，按编号顺序发言
        ordered_players = [
            (i - 1) % PLAYER_COUNT + 1
            for i in range(self.leader_index, self.leader_index + PLAYER_COUNT)
        ]
        logger.debug(f"Global speech order: {ordered_players}")

        for player_id in ordered_players:
            # 每个玩家发言前检查状态
            if (
                hasattr(self, "battle_status_checker")
                and self.battle_status_checker is not None
            ):
                if self.battle_status_checker.should_abort():
                    battle_status = self.battle_status_checker.get_battle_status(
                        force=True
                    )
                    logger.warning(
                        f"Global speech interrupted: Battle state changed to '{battle_status}'"
                    )
                    raise GameTerminationError(
                        f"Battle status changed to '{battle_status}'"
                    )

            logger.debug(f"Requesting speech from Player {player_id}")
            speech = self.safe_execute(player_id, "say")

            if not isinstance(speech, str):  # 用户给的 speech 异常
                logger.error(
                    f"Player {player_id} returned non-string speech: {type(speech)}.",
                    exc_info=True,  # Include traceback in log
                )
                self.suspend_game(
                    "player_ruturn_ERROR",
                    player_id,
                    "say",
                    f"Returned non-string speech: {type(speech)} during global speech",
                )

            logger.info(
                f"Global Speech - Player {player_id}: {speech[:100]}{'...' if len(speech) > 100 else ''}"
            )
            self.battle_observer.make_snapshot(
                "PublicSpeech",
                (player_id, speech[:100] + ("..." if len(speech) > 100 else "")),
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
        # 添加状态检查
        if (
            hasattr(self, "battle_status_checker")
            and self.battle_status_checker is not None
        ):
            if self.battle_status_checker.should_abort():
                battle_status = self.battle_status_checker.get_battle_status(force=True)
                logger.warning(
                    f"Movement phase aborted: Battle state changed to '{battle_status}'"
                )
                raise GameTerminationError(
                    f"Battle status changed to '{battle_status}'"
                )

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
            # 每个玩家移动前检查状态
            if (
                hasattr(self, "battle_status_checker")
                and self.battle_status_checker is not None
            ):
                if self.battle_status_checker.should_abort():
                    battle_status = self.battle_status_checker.get_battle_status(
                        force=True
                    )
                    logger.warning(
                        f"Movement interrupted: Battle state changed to '{battle_status}'"
                    )
                    raise GameTerminationError(
                        f"Battle status changed to '{battle_status}'"
                    )

            # 告知玩家当前地图情况
            self.safe_execute(player_id, "pass_position_data", self.player_positions)
            logger.debug(f"Sending current map to player {player_id}.")

            # 获取当前位置
            current_pos = deepcopy(self.player_positions[player_id])
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
                    "player_ruturn_ERROR",
                    player_id,
                    "walk",
                    f"Returned invalid directions type: {type(directions)}",
                )

            # 最多移动3步
            steps = len(directions)
            if steps > 3:
                logger.error(
                    f"Player {player_id} returned invalid directions length: {len(directions)}. No movement."
                )
                self.suspend_game(
                    "player_ruturn_ERROR",
                    player_id,
                    "walk",
                    f"Returned invalid directions length: {len(directions)}",
                )

            new_pos = current_pos

            # 默认directions合法
            # 保留valid_moves，最后用于格式化显示
            valid_moves = []
            logger.debug(f"Player {player_id} requested moves: {directions}")
            for i in range(steps):
                # 处理每个方向
                if not isinstance(directions[i], str):
                    logger.error(
                        f"Player {player_id} returned invalid direction type: {type(directions[i])}. i_index: {i}"
                    )
                    self.suspend_game(
                        "player_ruturn_ERROR",
                        player_id,
                        "walk",
                        f"Returned invalid direction type: {type(directions[i])}. i_index: {i}",
                    )

                direction = directions[i].lower()

                x, y = deepcopy(new_pos)

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
                        "player_ruturn_ERROR",
                        player_id,
                        "walk",
                        f"Attempted invalid move: {direction}. i_index: {i}",
                    )

                # 检查是否与其他玩家重叠
                if new_pos in [
                    self.player_positions[pid]
                    for pid in range(1, PLAYER_COUNT + 1)
                    if pid != player_id
                ]:
                    # 回退到上一个位置
                    logger.error(
                        f"Player {player_id} attempted to move to occupied position: {deepcopy(new_pos)}. i_index: {i}"
                    )
                    self.suspend_game(
                        "player_ruturn_ERROR",
                        player_id,
                        "walk",
                        f"Attempted to move to occupied position: {deepcopy(new_pos)}. i_index: {i}",
                    )

                # 快照记录每一步移动与地图
                self.battle_observer.make_snapshot(
                    "Move",
                    (
                        player_id,
                        [list(valid_moves), deepcopy(new_pos)],
                    ),  # 或者 valid_moves.copy()
                )

            # 更新玩家位置
            logger.info(
                f"Movement - Player {player_id}: {current_pos} -> {deepcopy(new_pos)} via {valid_moves}"
            )

            self.player_positions[player_id] = deepcopy(new_pos)
            x, y = deepcopy(new_pos)
            self.map_data[x][y] = str(player_id)  # Place marker after all checks

            movements.append(
                {
                    "player_id": player_id,
                    "requested_moves": list(directions),  # Log requested moves
                    "executed_moves": valid_moves,  # Log executed moves
                    "final_position": deepcopy(new_pos),
                }
            )

        # 再次检查状态
        if (
            hasattr(self, "battle_status_checker")
            and self.battle_status_checker is not None
        ):
            if self.battle_status_checker.should_abort():
                battle_status = self.battle_status_checker.get_battle_status(force=True)
                logger.warning(
                    f"Movement completion aborted: Battle state changed to '{battle_status}'"
                )
                raise GameTerminationError(
                    f"Battle status changed to '{battle_status}'"
                )

        # 更新所有玩家的地图
        logger.debug(
            "Updating all players with the new map state and data of positions."
        )
        for player_id in range(1, PLAYER_COUNT + 1):
            # 传递给玩家两种数据
            self.safe_execute(player_id, "pass_position_data", self.player_positions)
            self.safe_execute(player_id, "pass_map", deepcopy(self.map_data))

        # 记录移动
        self.log_public_event(
            {"type": "movement", "round": self.current_round, "movements": movements}
        )

        self.battle_observer.make_snapshot("Positions", self.player_positions)

        logger.info("Movement phase complete.")

    def conduct_limited_speech(self):
        """进行有限范围发言（只有在听力范围内的玩家能听到）"""
        # 添加状态检查
        if (
            hasattr(self, "battle_status_checker")
            and self.battle_status_checker is not None
        ):
            if self.battle_status_checker.should_abort():
                battle_status = self.battle_status_checker.get_battle_status(force=True)
                logger.warning(
                    f"Limited speech aborted: Battle state changed to '{battle_status}'"
                )
                raise GameTerminationError(
                    f"Battle status changed to '{battle_status}'"
                )

        # 从队长开始，按编号顺序发言
        ordered_players = [
            (i - 1) % PLAYER_COUNT + 1
            for i in range(self.leader_index, self.leader_index + PLAYER_COUNT)
        ]
        logger.debug(f"Limited speech order: {ordered_players}")

        speeches = []
        for speaker_id in ordered_players:
            # 每个玩家发言前检查状态
            if (
                hasattr(self, "battle_status_checker")
                and self.battle_status_checker is not None
            ):
                if self.battle_status_checker.should_abort():
                    battle_status = self.battle_status_checker.get_battle_status(
                        force=True
                    )
                    logger.warning(
                        f"Limited speech interrupted: Battle state changed to '{battle_status}'"
                    )
                    raise GameTerminationError(
                        f"Battle status changed to '{battle_status}'"
                    )

            logger.debug(f"Requesting limited speech from Player {speaker_id}")
            speech = self.safe_execute(speaker_id, "say")

            if not isinstance(speech, str):
                logger.error(
                    f"Player {speaker_id} returned non-string speech: {type(speech)}.",
                    exc_info=True,  # Include traceback in log
                )
                self.suspend_game(
                    "player_ruturn_ERROR",
                    speaker_id,
                    "say",
                    f"Returned non-string speech: {type(speech)} during limited speech",
                )

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

            self.battle_observer.make_snapshot(
                "PrivateSpeech",
                (
                    speaker_id,
                    speech[:100] + ("..." if len(speech) > 100 else ""),
                    " ".join(map(str, hearers)),
                ),
            )

        # 记录有限范围发言
        self.log_public_event(
            {
                "type": "limited_speech",
                "round": self.current_round,
                # "speeches": speeches,  这里的speech不能人尽皆知
            }
        )
        logger.info("Limited Speech phase complete.")

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
        # 添加状态检查
        if (
            hasattr(self, "battle_status_checker")
            and self.battle_status_checker is not None
        ):
            if self.battle_status_checker.should_abort():
                battle_status = self.battle_status_checker.get_battle_status(force=True)
                logger.warning(
                    f"Public vote aborted: Battle state changed to '{battle_status}'"
                )
                raise GameTerminationError(
                    f"Battle status changed to '{battle_status}'"
                )

        votes = {}
        logger.debug(f"Requesting public votes for team: {mission_members}")
        for player_id in range(1, PLAYER_COUNT + 1):
            # 每个玩家投票前检查状态
            if (
                hasattr(self, "battle_status_checker")
                and self.battle_status_checker is not None
                and player_id % 3 == 0
            ):  # 每3个玩家检查一次状态
                if self.battle_status_checker.should_abort():
                    battle_status = self.battle_status_checker.get_battle_status(
                        force=True
                    )
                    logger.warning(
                        f"Public vote interrupted: Battle state changed to '{battle_status}'"
                    )
                    raise GameTerminationError(
                        f"Battle status changed to '{battle_status}'"
                    )

            vote = self.safe_execute(player_id, "mission_vote1")

            # 确保投票结果是布尔值
            if not isinstance(vote, bool):
                logger.error(
                    f"Player {player_id} returned non-bool public vote: {type(vote)}.",
                    exc_info=True,  # Include traceback in log
                )
                self.suspend_game(
                    "player_ruturn_ERROR",
                    player_id,
                    "mission_vote1",
                    f"Returned non-bool public vote: {type(vote)}",
                )

            votes[player_id] = vote
            logger.debug(
                f"Public Vote - Player {player_id}: {'Approve' if vote else 'Reject'}"
            )
            self.battle_observer.make_snapshot(
                "PublicVote", (player_id, ("Approve" if vote else "Reject"))
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

        # 增加的快照
        logger.info(f"--- Executing Mission  ---")

        logger.info(
            f"Executing Mission {self.current_round} with members: {mission_members}"
        )

        logger.debug("Requesting mission execution votes (vote2).")

        for player_id in mission_members:
            vote = self.safe_execute(player_id, "mission_vote2")

            # 确保投票结果是布尔值
            if not isinstance(vote, bool):
                logger.error(
                    f"Player {player_id} returned non-bool mission vote: {type(vote)}.",
                    exc_info=True,
                )
                self.suspend_game(
                    "player_ruturn_ERROR",
                    player_id,
                    "mission_vote2",
                    f"Returned non-bool mission vote: {type(vote)}",
                )

            # 检查蓝方投失败票
            if not vote and self.roles[player_id] in BLUE_ROLES:
                logger.error(
                    f"Blue player {player_id} voted against execution.", exc_info=True
                )
                self.suspend_game(
                    "player_ruturn_ERROR",
                    player_id,
                    "mission_vote2",
                    f"Blue player {player_id} voted against execution.",
                )

            votes[player_id] = vote
            logger.debug(
                f"Mission Vote - Player {player_id} ({self.roles.get(player_id)}): {'Success' if vote else 'Fail'}"
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
        self.battle_observer.make_snapshot("MissionVote", votes)

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
            logger.error(
                f"No Assassin found!",
                exc_info=True,  # Include traceback in log
            )
            self.suspend_game(
                "critical_referee_ERROR", 0, "assassinate_phase", "no assassin found"
            )

        logger.info(f"Assassin (Player {assassin_id}) is choosing a target.")
        self.battle_observer.make_snapshot(
            "Event", f"player{assassin_id} choosing a target."
        )
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
                "player_ruturn_ERROR",
                assassin_id,
                "assass",
                f"Assassin returned invalid target: {target_id}",
            )
        # 不考虑刺客刺杀自己，因为无法改变游戏结果
        # 我倒是觉得可以做个彩蛋，刺杀自己就是蠢蛋，而且刺杀自己属于代码问题，就是用户的bug
        if target_id == assassin_id:
            logger.error(
                f"Assassin {assassin_id} targeted himself.",
                exc_info=True,  # Include traceback in log
            )
            self.suspend_game(
                "player_ruturn_ERROR",
                assassin_id,
                "assass",
                f"""Assassin {assassin_id} targeted himself.  
                    FOOL Assassin! FOOL Assassin! FOOL Assassin! FOOL Assassin!""",
            )

        # 判断是否刺中梅林
        target_role = self.roles[target_id]
        success = target_role == "Merlin"
        logger.info(
            f"Assassination: Player {assassin_id} targeted Player {target_id} ({target_role}). Result: {'Success' if success else 'Fail'}"
        )
        self.battle_observer.make_snapshot(
            "Assass",
            [assassin_id, target_id, target_role, ("Success" if success else "Fail")],
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
        # 刺杀结束快照
        return success

    """
    以下是完整的 referee.py 中 run_game 方法修改实现。
    这个实现专注于确保游戏结果的格式一致性，正确包含角色信息，并增强日志记录。
    """

    def run_game(self) -> Dict[str, Any]:
        """
        运行游戏，返回游戏结果
        """
        logger.info(f"===== Starting Game {self.game_id} =====")
        self.battle_observer.make_snapshot("GameStart", self.game_id)

        # 从数据库获取对战记录，用于状态检查
        try:
            # 直接使用传入的battle_service而不是直接查询数据库
            # 避免"Working outside of application context"错误
            self.battle_status_checker = BattleStatusChecker(self.game_id)
        except Exception as e:
            logger.error(f"Error initializing battle status checker: {str(e)}")
            # 继续游戏流程，但没有状态检查
            self.battle_status_checker = None

        def check_abort():
            """检查是否需要中止游戏，若需要则返回中止结果"""
            # 如果无法获取battle状态检查器，跳过检查
            if (
                not hasattr(self, "battle_status_checker")
                or self.battle_status_checker is None
            ):
                return None

            # 检查对战状态
            if self.battle_status_checker.should_abort():
                battle_status = self.battle_status_checker.get_battle_status()

                # 创建标准格式的角色信息字典
                roles_dict = {}
                if hasattr(self, "roles") and self.roles:
                    # 保持整数键 - 这样在 process_battle_results_and_update_stats 中更容易处理
                    for player_id, role in self.roles.items():
                        roles_dict[player_id] = role

                    # 记录详细的角色分配信息，便于调试
                    logger.info(f"Game {self.game_id} aborted with roles: {roles_dict}")

                game_result = {
                    "blue_wins": self.blue_wins,
                    "red_wins": self.red_wins,
                    "rounds_played": self.current_round,
                    "roles": roles_dict,  # 使用标准格式的角色字典
                    "public_log_file": os.path.join(
                        self.data_dir, f"game_{self.game_id}_public.json"
                    ),
                    "winner": None,
                    "win_reason": f"aborted_due_to_battle_state_{battle_status}",
                }
                logger.info(f"Game aborted: Battle state is '{battle_status}'")
                self.log_public_event({"type": "game_aborted", "result": game_result})
                self.battle_observer.make_snapshot("GameAborted", self.game_id)
                return game_result
            return None

        try:
            # 初始化游戏
            self.init_game()
            abort_result = check_abort()
            if abort_result:
                return abort_result

            # 夜晚阶段
            self.night_phase()
            abort_result = check_abort()
            if abort_result:
                return abort_result

            # 任务阶段
            while (
                self.blue_wins < 3
                and self.red_wins < 3
                and self.current_round < MAX_MISSION_ROUNDS
            ):
                try:
                    self.run_mission_round()
                except GameTerminationError as e:
                    logger.warning(f"Mission round terminated: {str(e)}")
                    # 将状态检查的结果包装成返回值
                    abort_result = check_abort()
                    if abort_result:
                        return abort_result
                    else:
                        # 如果check_abort没有返回结果，我们仍然需要处理终止
                        # 创建标准格式的角色信息字典
                        roles_dict = {}
                        if hasattr(self, "roles") and self.roles:
                            # 保持整数键，与正常流程保持一致
                            for player_id, role in self.roles.items():
                                roles_dict[player_id] = role

                            # 记录详细的角色分配信息，便于调试
                            logger.info(
                                f"Game {self.game_id} terminated with roles: {roles_dict}"
                            )

                        return {
                            "blue_wins": self.blue_wins,
                            "red_wins": self.red_wins,
                            "rounds_played": self.current_round,
                            "roles": roles_dict,
                            "public_log_file": os.path.join(
                                self.data_dir, f"game_{self.game_id}_public.json"
                            ),
                            "winner": None,
                            "win_reason": "terminated_due_to_status_change",
                        }

                # 每轮结束后检查状态
                abort_result = check_abort()
                if abort_result:
                    return abort_result

            # 游戏结束判定
            logger.info("===== Game Over =====")
            self.battle_observer.make_snapshot("GameEnd", self.game_id)
            logger.info(
                f"Final Score: Blue {self.blue_wins} - Red {self.red_wins} after {self.current_round} rounds."
            )
            self.battle_observer.make_snapshot(
                "FinalScore", [self.blue_wins, self.red_wins]
            )

            # 创建标准格式的角色信息字典
            roles_dict = {}
            if hasattr(self, "roles") and self.roles:
                # 保持整数键 - 这样在 process_battle_results_and_update_stats 中更容易处理
                for player_id, role in self.roles.items():
                    roles_dict[player_id] = role

                # 记录详细的角色分配信息，便于调试
                logger.info(f"Game {self.game_id} final role assignments: {roles_dict}")

            game_result = {
                "blue_wins": self.blue_wins,
                "red_wins": self.red_wins,
                "rounds_played": self.current_round,
                "roles": roles_dict,  # 使用标准格式的角色字典
                "public_log_file": os.path.join(
                    self.data_dir, f"game_{self.game_id}_public.json"
                ),
            }

            # 蓝方需要刺杀阶段
            if self.blue_wins >= 3:
                logger.info(
                    "Blue team completed 3 missions. Proceeding to assassination."
                )
                abort_result = check_abort()
                if abort_result:
                    return abort_result  # 进入刺杀阶段前检查

                assassination_success = self.assassinate_phase()
                if assassination_success:
                    game_result.update(
                        {"winner": "red", "win_reason": "assassination_success"}
                    )
                    self.battle_observer.make_snapshot(
                        "GameResult", ["Red", "Assassination Success"]
                    )
                    logger.info(
                        f"Game {self.game_id} result: RED wins by assassination"
                    )
                else:
                    game_result.update(
                        {
                            "winner": "blue",
                            "win_reason": "missions_complete_and_assassination_failed",
                        }
                    )
                    self.battle_observer.make_snapshot(
                        "GameResult", ["Blue", "Assassination Failed"]
                    )
                    logger.info(
                        f"Game {self.game_id} result: BLUE wins (assassination failed)"
                    )
            elif self.red_wins >= 3:
                game_result.update({"winner": "red", "win_reason": "missions_failed"})
                self.battle_observer.make_snapshot(
                    "GameResult", ["Red", "3 Failed Missions"]
                )
                logger.info(
                    f"Game {self.game_id} result: RED wins by completing 3 failed missions"
                )

            # 验证结果数据的完整性
            if "roles" not in game_result or not game_result["roles"]:
                logger.warning(f"Game {self.game_id} missing roles data in result")
                # 确保有一个默认的roles字典
                game_result["roles"] = {}

            if "winner" not in game_result:
                logger.warning(f"Game {self.game_id} missing winner in result")
                # 根据得分确定获胜方
                if self.blue_wins > self.red_wins:
                    game_result["winner"] = "blue"
                elif self.red_wins > self.blue_wins:
                    game_result["winner"] = "red"
                else:
                    # 平局情况
                    game_result["winner"] = None

            # 记录最终完整的游戏结果
            logger.info(
                f"Final game result for {self.game_id}: {json.dumps(game_result, default=str)}"
            )

            # 记录最终结果
            self.log_public_event(
                {"type": "tokens", "result": self.game_helper.get_tokens()}
            )
            self.log_public_event({"type": "game_end", "result": game_result})
            logger.info(f"===== Game {self.game_id} Finished =====")
            self.battle_observer.make_snapshot("GameEnd", self.game_id)
            return game_result

        except GameTerminationError as e:
            logger.error(f"Game terminated due to battle status change: {str(e)}")

            # 创建标准格式的角色信息字典
            roles_dict = {}
            if hasattr(self, "roles") and self.roles:
                # 保持整数键，与正常流程保持一致
                for player_id, role in self.roles.items():
                    roles_dict[player_id] = role

                # 记录详细的角色分配信息，便于调试
                logger.info(f"Game {self.game_id} terminated with roles: {roles_dict}")

            terminate_result = {
                "blue_wins": self.blue_wins,
                "red_wins": self.red_wins,
                "rounds_played": self.current_round,
                "roles": roles_dict,  # 使用标准格式的角色字典
                "public_log_file": os.path.join(
                    self.data_dir, f"game_{self.game_id}_public.json"
                ),
                "winner": None,
                "win_reason": "terminated_due_to_status_change",
            }

            # 记录终止事件
            self.log_public_event(
                {"type": "game_terminated", "result": terminate_result}
            )
            return terminate_result

        except Exception as e:
            logger.error(
                f"Critical error during game {self.game_id}: {str(e)}", exc_info=True
            )

            # 创建标准格式的角色信息字典
            roles_dict = {}
            if hasattr(self, "roles") and self.roles:
                # 保持整数键，与正常流程保持一致
                for player_id, role in self.roles.items():
                    roles_dict[player_id] = role

                # 记录详细的角色分配信息，便于调试
                logger.info(f"Game {self.game_id} crashed with roles: {roles_dict}")

            error_result = {
                "error": f"Critical Error: {str(e)}",
                "blue_wins": self.blue_wins,
                "red_wins": self.red_wins,
                "rounds_played": self.current_round,
                "roles": roles_dict,  # 使用标准格式的角色字典
                "public_log_file": os.path.join(
                    self.data_dir, f"game_{self.game_id}_public.json"
                ),
            }

            # 记录错误事件
            self.log_public_event({"type": "game_error", "result": error_result})
            return error_result

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
                f"Player {player_id} has no callable method '{method_name}'. Using default behavior."
            )
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
            # 1. 设置referee实例的上下文
            self.game_helper.set_current_context(player_id, self.game_id)

            # 2. 同时设置全局默认实例的上下文 - 确保线程安全
            from .avalon_game_helper import (
                set_thread_helper,
                set_current_context,
                set_current_round,
            )

            # 将当前线程的helper设为referee的专属实例
            set_thread_helper(self.game_helper)

            # 3. 设置当前轮次信息
            if self.current_round is not None:
                set_current_round(self.current_round)

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
            if execution_time > MAX_EXECUTION_TIME:  # Lowered threshold for warning
                logger.error(
                    f"Player {player_id} ({self.roles.get(player_id)}) method {method_name} took {execution_time:.2f} seconds (timeout)"
                )
                self.suspend_game(
                    "critical_player_ERROR", player_id, method_name, str(e)
                )
            return result

        except Exception as e:  # 玩家代码运行过程中报错
            logger.error(
                f"Error executing Player {player_id} ({self.roles.get(player_id)}) method '{method_name}': {str(e)}",
                exc_info=True,  # Include traceback in log
            )
            self.suspend_game("critical_player_ERROR", player_id, method_name, str(e))

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
        error_msg: str,
    ):
        "一键中止游戏。代替前文反反复复出现的堆积如山的 raise RuntimeError。"

        SUSPEND_BROADCAST_MSG = (
            (
                f"Error executing Player {error_code_pid} method {error_code_method_name}: "
                + error_msg
                + ". Game suspended."
            )
            if error_code_pid > 0
            else (
                f"Referee error during {error_code_method_name}: {error_msg}. Game suspended."
            )
        )

        # 1. 给公有库添加报错信息
        self.log_public_event(
            {"type": "tokens", "result": self.game_helper.get_tokens()}
        )
        self.log_public_event(
            {
                "type": game_error_type,
                "error_code_pid": error_code_pid,
                "error_code_method": error_code_method_name,
                "error_msg": error_msg,
            }
        )

        # 2. 给observer添加报错信息
        self.battle_observer.make_snapshot("Bug", SUSPEND_BROADCAST_MSG)

        # 3. 抛出错误，终止游戏
        raise RuntimeError(SUSPEND_BROADCAST_MSG)

    def random_select_members(self, member_count: int) -> List[int]:
        """
        随机选择指定数量的队员
        作为 decide_mission_member 方法的默认实现
        """
        # 随机选择玩家组成队伍
        all_players = list(range(1, PLAYER_COUNT + 1))
        # 确保不超过可用玩家数量
        member_count = min(member_count, PLAYER_COUNT)
        # 随机抽样不放回
        return random.sample(all_players, member_count)
