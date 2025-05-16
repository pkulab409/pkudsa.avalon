# 裁判系统 - 负责执行游戏规则和管理游戏状态


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

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("Referee")

# 导入辅助模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
        game_id: str,  # 游戏唯一标识符
        battle_observer: Observer,  # 观察者对象，用于记录游戏状态变化
        data_dir: str = "./data",  # 数据存储目录，默认为当前目录下的data文件夹
        player_code_paths: Dict[
            int, str
        ] = None,  # 玩家代码路径字典，格式为{玩家ID: 代码路径}
    ):
        # 初始化基本游戏属性
        self.game_id = game_id
        self.data_dir = data_dir
        self.players = {}  # 玩家对象字典 {1: player1, 2: player2, ...}
        self.roles = {}  # 角色分配字典 {1: "Merlin", 2: "Assassin", ...}
        self.map_data = []  # 地图数据，二维数组表示
        self.player_positions = {}  # 玩家在地图上的位置 {1: (x, y), 2: (x, y), ...}
        self.mission_results = []  # 任务结果列表 [True, False, ...]，True表示任务成功
        self.current_round = 0  # 当前任务轮次，从0开始，每轮任务+1
        self.blue_wins = 0  # 蓝方（好人方）胜利次数
        self.red_wins = 0  # 红方（坏人方）胜利次数
        self.public_log = []  # 公共日志，记录游戏过程中的公开信息
        self.leader_index = random.randint(1, PLAYER_COUNT)  # 随机选择初始队长

        # 记录初始化信息
        logger.info(
            f"Game {game_id} initialized. Data dir: {data_dir}. Initial leader: {self.leader_index}"
        )

        # 为这个referee创建一个专用的GameHelper实例，用于管理游戏辅助功能
        self.game_helper = GameHelper(data_dir=data_dir)
        self.game_helper.game_session_id = game_id  # 设置GameHelper的游戏ID

        # 创建数据目录，确保目录存在
        os.makedirs(os.path.join(data_dir), exist_ok=True)

        # 初始化日志文件
        self.init_logs()

        # 保存Observer实例
        self.battle_observer = battle_observer

        # 加载玩家代码（如果提供了代码路径）
        if player_code_paths:
            player_modules = self._load_codes(player_code_paths)  # 加载代码为模块
            self.load_player_codes(player_modules)  # 实例化玩家对象

    def init_logs(self):
        """初始化游戏日志文件"""
        logger.info(f"Initializing logs for game {self.game_id}")

        # 初始化公共日志文件（所有玩家可见的信息）
        public_log_file = os.path.join(
            self.data_dir, f"game_{self.game_id}_public.json"
        )
        with open(public_log_file, "w", encoding="utf-8") as f:
            json.dump([], f)  # 初始化为空列表

        # 为每个玩家初始化私有日志文件（只有玩家自己可见的信息）
        for player_id in range(1, PLAYER_COUNT + 1):
            private_log_file = os.path.join(
                self.data_dir, f"game_{self.game_id}_player_{player_id}_private.json"
            )
            with open(private_log_file, "w", encoding="utf-8") as f:
                json.dump(INIT_PRIVA_LOG_DICT, f)  # 使用预定义的私有日志初始结构

        logger.info(f"Public and private log files initialized in {self.data_dir}")

    def _load_codes(self, player_codes):
        """
        加载玩家代码
        player_codes: {玩家ID: 代码路径或代码内容}
        返回: {玩家ID: 代码模块}
        """
        player_modules = {}  # 用于存储加载的模块

        for player_id, code_path in player_codes.items():
            # 创建唯一模块名，避免模块名冲突
            module_name = f"player_{player_id}_module_{int(time.time()*1000)}"
            logger.info(f"为玩家 {player_id} 创建模块: {module_name}")

            try:
                # 判断code_path是文件路径还是代码内容
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

                # 创建模块规范（spec）
                spec = importlib.util.spec_from_loader(module_name, loader=None)
                if spec is None:
                    logger.error(f"为 {module_name} 创建规范失败")
                    continue

                # 从规范创建模块
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module  # 注册模块到sys.modules

                # 执行代码（限制内置函数以增加安全性）
                module.__dict__["__builtins__"] = RESTRICTED_BUILTINS
                exec(code_content, module.__dict__)  # 将代码执行到模块环境中

                # 检查Player类是否存在
                if not hasattr(module, "Player"):
                    logger.error(f"玩家 {player_id} 的代码已执行但未找到 'Player' 类")
                    self.suspend_game(
                        "critical_player_ERROR",
                        player_id,
                        "Player",
                        f"玩家 {player_id} 的代码已执行但未找到 'Player' 类",
                    )  # 中止游戏

                # 存储模块
                player_modules[player_id] = module
                logger.info(f"玩家 {player_id} 代码加载成功")

            except Exception as e:
                # 加载过程中出现异常
                logger.error(f"加载玩家 {player_id} 代码时出错: {str(e)}")
                traceback.print_exc()  # 打印详细的异常追踪

        return player_modules  # 返回加载的模块字典

    def load_player_codes(self, player_modules: Dict[int, Any]):
        """
        实例化玩家对象并设置玩家编号
        player_modules: {玩家ID: 代码模块}
        """
        logger.info(f"Loading player code for {len(player_modules)} players.")

        for player_id, module in player_modules.items():
            try:
                # 实例化Player类，创建玩家对象
                player_instance = module.Player()
                self.players[player_id] = player_instance

            except Exception as e:  # 玩家代码 __init__ 方法执行出错
                logger.error(
                    f"Error executing Player {player_id} method '__init__': {str(e)}",
                    exc_info=True,  # 包含完整异常追踪
                )
                try:
                    # 统一通过suspend_game方法处理错误
                    self.suspend_game(
                        "critical_player_ERROR", player_id, "__init__", str(e)
                    )  # 中止游戏
                except Exception as e_:  # suspend_game抛出的错误
                    logger.error(
                        f"Critical error during game {self.game_id}: {str(e)}",
                        exc_info=True,
                    )
                    raise RuntimeError(e_)  # 重新抛出错误

            # 为玩家设置编号
            self.safe_execute(player_id, "set_player_index", player_id)
            logger.info(f"Player {player_id} code loaded and instance created.")

    def init_game(self):
        """初始化游戏：分配角色、初始化地图"""
        logger.info("Initializing game: Assigning roles and map.")
        # 创建角色列表并随机打乱
        all_roles = BLUE_ROLES.copy()  # 复制蓝方角色列表(Merlin, Percival, Knight)
        # 添加额外的骑士，因为需要2个骑士角色
        all_roles.append("Knight")
        all_roles.extend(RED_ROLES)  # 添加红方角色(Morgana, Assassin, Oberon)
        random.shuffle(all_roles)  # 随机打乱角色顺序

        # 将角色分配给玩家
        for player_id in range(1, PLAYER_COUNT + 1):
            self.roles[player_id] = all_roles[player_id - 1]  # 保存玩家ID对应的角色
            # 调用玩家代码中的set_role_type方法通知玩家自己的角色
            self.safe_execute(player_id, "set_role_type", all_roles[player_id - 1])
            logger.info(f"Player {player_id} assigned role: {all_roles[player_id - 1]}")
        logger.info(f"Roles assigned: {self.roles}")
        # 创建角色分配的游戏状态快照，用于可视化
        self.battle_observer.make_snapshot("RoleAssign", self.roles)

        # 初始化游戏地图
        self.init_map()

        # 向公共日志添加游戏开始记录
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
        # 创建空地图，初始化为9x9的空格矩阵
        self.map_data = [[" " for _ in range(MAP_SIZE)] for _ in range(MAP_SIZE)]

        # 随机为每个玩家分配不重叠的位置
        positions = []
        for player_id in range(1, PLAYER_COUNT + 1):
            while True:
                # 随机生成坐标
                x = random.randint(0, MAP_SIZE - 1)
                y = random.randint(0, MAP_SIZE - 1)
                # 确保位置未被占用
                if (x, y) not in positions:
                    positions.append((x, y))
                    self.player_positions[player_id] = (x, y)  # 记录玩家位置
                    self.map_data[x][y] = str(player_id)  # 在地图上标记玩家位置
                    break
        logger.info(f"Player positions: {self.player_positions}")
        # 记录玩家位置快照
        self.battle_observer.make_snapshot("DefaultPositions", self.player_positions)

        # 将地图信息发送给所有玩家
        for player_id in range(1, PLAYER_COUNT + 1):
            logger.debug(f"Sending map data to player {player_id}")
            # 使用深拷贝确保每个玩家获得独立的地图副本
            self.safe_execute(player_id, "pass_map", deepcopy(self.map_data))
        logger.info("Map initialized and sent to players.")

    def night_phase(self):
        """夜晚阶段：各角色按照视野规则获取信息"""
        logger.info("Starting Night Phase.")
        self.battle_observer.make_snapshot("NightStart", "Starting Night Phase.")

        # 1. 红方互认（除奥伯伦外的红方角色互相了解）
        # 获取所有互相了解的红方角色ID
        evil_team_ids = [pid for pid, r in self.roles.items() if r in EVIL_AWARE_ROLES]
        logger.info(f"Evil team (aware): {evil_team_ids}")

        for player_id, role in self.roles.items():
            if role in EVIL_AWARE_ROLES:  # 如果是互相了解的红方角色
                # 构建包含其他互认红方玩家的字典
                evil_sight = {}
                for other_id, other_role in self.roles.items():
                    # 添加其他互认红方角色（不包括自己）
                    if other_id != player_id and other_role in EVIL_AWARE_ROLES:
                        evil_sight[other_role] = other_id

                logger.debug(
                    f"Sending evil sight info to Player {player_id} ({role}): {evil_sight}"
                )
                # 调用玩家代码的pass_role_sight方法传递红方玩家信息
                self.safe_execute(player_id, "pass_role_sight", evil_sight)

        # 2. 梅林看到所有红方
        # 找到梅林玩家ID
        merlin_id = [pid for pid, r in self.roles.items() if r == "Merlin"]
        if merlin_id:  # 如果找到了梅林
            merlin_id = merlin_id[0]
            # 构建包含所有红方角色的字典
            red_team_ids = {r: pid for pid, r in self.roles.items() if r in RED_ROLES}
            logger.debug(
                f"Sending red team info to Merlin (Player {merlin_id}): {red_team_ids}"
            )
            # 调用梅林玩家的pass_role_sight方法传递红方信息
            self.safe_execute(merlin_id, "pass_role_sight", red_team_ids)

        # 3. 派西维尔看到梅林和莫甘娜（但无法区分）
        percival_id = [pid for pid, r in self.roles.items() if r == "Percival"]
        morgana_id = [pid for pid, r in self.roles.items() if r == "Morgana"]
        if percival_id and morgana_id:  # 如果找到了派西维尔和莫甘娜
            percival_id = percival_id[0]
            morgana_id = morgana_id[0]
            # 按顺序排列梅林和莫甘娜的ID
            merlin_morgana_id = sorted([merlin_id, morgana_id])
            # 构建特殊角色字典，派西维尔无法区分梅林和莫甘娜
            targets = {f"Special{i+1}": merlin_morgana_id[i] for i in range(2)}
            logger.debug(
                f"Sending Merlin/Morgana info to Percival (Player {percival_id}): {targets}"
            )
            # 调用派西维尔玩家的pass_role_sight方法传递特殊角色信息
            self.safe_execute(percival_id, "pass_role_sight", targets)

        # 记录夜晚阶段完成到公共日志
        self.log_public_event({"type": "night_phase_complete"})
        logger.info("Night Phase complete.")
        self.battle_observer.make_snapshot("NightEnd", "--- Night phase complete ---")

    def run_mission_round(self):
        """执行一轮任务：包括队长选人、发言、移动、投票和任务执行"""
        # 递增当前轮次计数
        self.current_round += 1

        # 在GameHelper中设置当前轮次，以便玩家代码访问
        self.game_helper.set_current_round(self.current_round)

        # 重置当前轮次的大语言模型(LLM)使用限制
        self.game_helper.reset_llm_limit(self.current_round)

        # 获取当前轮次需要的队员数量
        member_count = MISSION_MEMBER_COUNT[self.current_round - 1]

        # 初始化投票轮次计数和任务结果
        vote_round = 0
        mission_success = None  # 任务结果初始为None

        # 记录轮次开始的日志信息
        logger.info(f"--- Starting Mission Round {self.current_round} ---")

        # 创建轮次开始的可视化快照
        self.battle_observer.make_snapshot("RoundStart", self.current_round)

        # 记录当前队长和所需队员数量
        logger.info(
            f"Leader: Player {self.leader_index}, Members needed: {member_count}"
        )

        # 向公共日志中添加任务开始事件
        self.log_public_event(
            {
                "type": "mission_start",  # 事件类型：任务开始
                "round": self.current_round,  # 当前轮次
                "leader": self.leader_index,  # 当前队长
                "member_count": member_count,  # 需要的队员数量
            }
        )

        # 定义内部函数，用于检查游戏对战状态
        def check_battle_status():
            """检查对战状态，如果不是playing或waiting则抛出异常"""
            if (
                hasattr(self, "battle_status_checker")  # 如果有状态检查器
                and self.battle_status_checker is not None
            ):
                if self.battle_status_checker.should_abort():  # 如果应该中止
                    # 获取当前状态（强制更新）
                    battle_status = self.battle_status_checker.get_battle_status(
                        force=True
                    )
                    # 记录警告日志
                    logger.warning(
                        f"Mission round aborted: Battle state changed to '{battle_status}'"
                    )
                    # 抛出游戏终止异常
                    raise GameTerminationError(
                        f"Battle status changed to '{battle_status}'"
                    )

        # 任务开始前进行初始状态检查
        try:
            check_battle_status()
        except GameTerminationError as e:
            raise e  # 重新抛出异常，交由上层处理

        # 任务循环：直到有效执行任务或达到最大投票次数(5次)
        while mission_success is None and vote_round < MAX_VOTE_ROUNDS:
            # 递增投票轮次计数
            vote_round += 1

            # 记录当前投票轮次和任务轮次的日志
            logger.info(
                f"Starting Vote Round {vote_round} for Mission {self.current_round}."
            )

            # 队长选择队员前检查状态
            try:
                check_battle_status()
            except GameTerminationError as e:
                raise e

            # 1. 队长选择队员阶段
            logger.info(f"Leader {self.leader_index} is proposing a team.")

            # 调用队长的decide_mission_member方法选择队员
            mission_members = self.safe_execute(
                self.leader_index, "decide_mission_member", member_count
            )
            logger.debug(f"Leader {self.leader_index} proposed: {mission_members}")

            # 验证队员选择的有效性
            if not isinstance(mission_members, list):  # 必须返回列表类型
                # 记录错误日志
                logger.error(
                    f"Leader {self.leader_index} returned non-list: {type(mission_members)}.",
                    exc_info=True,  # 包含完整异常追踪
                )
                # 中止游戏
                self.suspend_game(
                    "player_ruturn_ERROR",  # 错误类型：玩家返回值错误
                    self.leader_index,  # 出错的玩家ID
                    "decide_mission_member",  # 出错的方法名
                    f"Leader {self.leader_index} returned non-list: {type(mission_members)}",  # 错误信息
                )
            else:
                # 验证队员ID的有效性
                valid_members = []
                for member in mission_members:
                    # 检查队员ID是否为有效的玩家ID（1-7）
                    if isinstance(member, int) and 1 <= member <= PLAYER_COUNT:
                        if member not in valid_members:  # 防止队员重复
                            valid_members.append(member)
                        else:  # 检测到重复队员
                            logger.error(
                                f"Leader {self.leader_index} proposed duplicate member {member}.",
                                exc_info=True,
                            )
                            self.suspend_game(
                                "player_ruturn_ERROR",
                                self.leader_index,
                                "decide_mission_member",
                                f"Leader {self.leader_index} proposed duplicate member: {mission_members}",
                            )
                    else:  # 检测到无效队员ID
                        logger.error(
                            f"Leader {self.leader_index} proposed invalid member {member}.",
                            exc_info=True,
                        )
                        self.suspend_game(
                            "player_ruturn_ERROR",
                            self.leader_index,
                            "decide_mission_member",
                            f"Leader {self.leader_index} proposed invalid member: {mission_members}",
                        )

                # 验证队员数量是否符合要求
                if len(valid_members) != member_count:
                    logger.error(
                        f"Leader {self.leader_index} proposed too many(few) members: {len(valid_members)}.",
                        exc_info=True,
                    )
                    self.suspend_game(
                        "player_ruturn_ERROR",
                        self.leader_index,
                        "decide_mission_member",
                        f"Leader {self.leader_index} proposed too many(few) members: {mission_members}",
                    )
                else:
                    # 使用经过验证的队员列表
                    mission_members = valid_members
                    logger.info(
                        f"Leader {self.leader_index} proposed team: {mission_members}"
                    )

                # 创建队伍提议的可视化快照
                self.battle_observer.make_snapshot(
                    "TeamPropose",
                    mission_members,
                )

            # 通知所有玩家队伍组成
            logger.debug("Notifying all players of the proposed team.")
            for player_id in range(1, PLAYER_COUNT + 1):
                # 调用每个玩家的pass_mission_members方法传递队伍信息
                self.safe_execute(
                    player_id,
                    "pass_mission_members",
                    self.leader_index,  # 传递队长ID
                    mission_members,  # 传递队员列表
                )

            # 创建队长和队伍提议的可视化快照
            self.battle_observer.make_snapshot("Leader", self.leader_index)

            # 向公共日志添加队伍提议事件
            self.log_public_event(
                {
                    "type": "team_proposed",
                    "round": self.current_round,
                    "vote_round": vote_round,
                    "leader": self.leader_index,
                    "members": mission_members,
                }
            )

            # 第一轮发言前检查状态
            try:
                check_battle_status()
            except GameTerminationError as e:
                raise e

            # 2. 第一轮发言（全图广播）
            logger.info("Starting Global Speech phase.")
            try:
                self.conduct_global_speech()  # 执行全局发言
            except GameTerminationError as e:
                raise e

            # 玩家移动前检查状态
            try:
                check_battle_status()
            except GameTerminationError as e:
                raise e

            # 3. 玩家移动
            logger.info("Starting Movement phase.")
            try:
                self.conduct_movement()  # 执行玩家移动
            except GameTerminationError as e:
                raise e

            # 第二轮发言前检查状态
            try:
                check_battle_status()
            except GameTerminationError as e:
                raise e

            # 4. 第二轮发言（有限听力范围）
            logger.info("Starting Limited Speech phase.")
            try:
                self.conduct_limited_speech()  # 执行有限范围发言
            except GameTerminationError as e:
                raise e

            # 公投表决前检查状态
            try:
                check_battle_status()
            except GameTerminationError as e:
                raise e

            # 5. 公投表决
            logger.info("Starting Public Vote phase.")
            # 执行公投，并获取支持票数
            approve_votes = self.conduct_public_vote(mission_members)

            # 记录投票结果日志
            logger.info(
                f"Public vote result: {approve_votes} Approve vs {PLAYER_COUNT - approve_votes} Reject."
            )

            # 创建投票结果的可视化快照
            self.battle_observer.make_snapshot(
                "PublicVoteResult", [approve_votes, PLAYER_COUNT - approve_votes]
            )

            # 判断投票结果，过半数同意则执行任务
            if approve_votes >= (PLAYER_COUNT // 2 + 1):  # 过半数同意
                logger.info("Team Approved. Executing mission.")

                # 创建任务通过的可视化快照
                self.battle_observer.make_snapshot(
                    "MissionApproved", [self.current_round, mission_members]
                )

                # 执行任务前检查状态
                try:
                    check_battle_status()
                except GameTerminationError as e:
                    raise e

                # 执行任务
                try:
                    mission_success = self.execute_mission(mission_members)
                except GameTerminationError as e:
                    raise e

                break  # 任务执行完毕，退出循环
            else:  # 未获得过半数支持，任务被否决
                logger.info("Team Rejected.")

                # 创建任务否决的可视化快照
                self.battle_observer.make_snapshot("MissionRejected", "Team Rejected.")

                # 否决后重置当前轮次的LLM限制
                self.game_helper.reset_llm_limit(self.current_round)

                # 更换队长（当前队长索引+1，如果超出玩家数量则回到1）
                old_leader = self.leader_index
                self.leader_index = self.leader_index % PLAYER_COUNT + 1
                logger.info(f"Leader changed from {old_leader} to {self.leader_index}.")

                # 创建新队长的可视化快照
                self.battle_observer.make_snapshot("Leader", self.leader_index)

                # 向公共日志添加任务否决事件
                self.log_public_event(
                    {
                        "type": "team_rejected",
                        "round": self.current_round,
                        "vote_round": vote_round,
                        "approve_count": approve_votes,
                        "next_leader": self.leader_index,
                    }
                )

                # 特殊情况检查前检查状态
                try:
                    check_battle_status()
                except GameTerminationError as e:
                    raise e

                # 特殊情况：连续5次否决
                if vote_round == MAX_VOTE_ROUNDS:
                    logger.warning(
                        "Maximum vote rounds reached. Forcing mission execution with last proposed team."
                    )

                    # 创建强制执行任务的可视化快照
                    self.battle_observer.make_snapshot(
                        "MissionForceExecute",
                        "Maximum vote rounds reached. Forcing mission execution with last proposed team.",
                    )

                    # 向公共日志添加连续否决事件
                    self.log_public_event(
                        {"type": "consecutive_rejections", "round": self.current_round}
                    )

                    # 强制执行前检查状态
                    try:
                        check_battle_status()
                    except GameTerminationError as e:
                        raise e

                    # 强制执行任务（即使未获得过半数支持）
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

        # 创建任务结果的可视化快照
        self.battle_observer.make_snapshot(
            "MissionResult",
            (self.current_round, ("Success" if mission_success else "Fail")),
        )

        # 将任务结果添加到结果列表中
        self.mission_results.append(mission_success)

        # 根据任务结果更新蓝方/红方胜利计数
        if mission_success:  # 任务成功，蓝方胜利
            self.blue_wins += 1

            # 向公共日志添加任务结果事件
            self.log_public_event(
                {
                    "type": "mission_result",
                    "round": self.current_round,
                    "result": "success",
                    "blue_wins": self.blue_wins,
                    "red_wins": self.red_wins,
                }
            )
        else:  # 任务失败，红方胜利
            self.red_wins += 1

            # 向公共日志添加任务结果事件
            self.log_public_event(
                {
                    "type": "mission_result",
                    "round": self.current_round,
                    "result": "fail",
                    "blue_wins": self.blue_wins,
                    "red_wins": self.red_wins,
                }
            )

        # 记录当前比分
        logger.info(f"Score: Blue {self.blue_wins} - Red {self.red_wins}")

        # 创建比分的可视化快照
        self.battle_observer.make_snapshot(
            "ScoreBoard", [self.blue_wins, self.red_wins]
        )

        # 更新下一轮的队长（在一轮任务结束时更新）
        old_leader_for_next_round = self.leader_index
        self.leader_index = self.leader_index % PLAYER_COUNT + 1

        # 记录下一轮队长
        logger.debug(
            f"Leader for next round will be {self.leader_index} (previous was {old_leader_for_next_round})"
        )

        # 创建轮次结束的可视化快照
        self.battle_observer.make_snapshot("RoundEnd", self.current_round)

        # 记录轮次结束日志
        logger.info(f"--- End of Mission Round {self.current_round} ---")

    def conduct_global_speech(self):
        """进行全局发言（所有玩家都能听到）"""
        # 检查游戏对战状态，如果需要终止则提前结束
        if (
            hasattr(self, "battle_status_checker")
            and self.battle_status_checker is not None
        ):
            if self.battle_status_checker.should_abort():
                battle_status = self.battle_status_checker.get_battle_status(force=True)
                logger.warning(
                    f"Global speech aborted: Battle state changed to '{battle_status}'"
                )
                # 抛出游戏终止异常，将被上层函数捕获处理
                raise GameTerminationError(
                    f"Battle status changed to '{battle_status}'"
                )

        # 用于存储所有玩家的发言记录
        speeches = []

        # 确定发言顺序：从当前队长开始，按照玩家编号顺序安排
        ordered_players = [
            (i - 1) % PLAYER_COUNT + 1
            for i in range(self.leader_index, self.leader_index + PLAYER_COUNT)
        ]
        logger.debug(f"Global speech order: {ordered_players}")

        # 按顺序让每个玩家发言
        for player_id in ordered_players:
            # 每位玩家发言前再次检查游戏状态
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

            # 请求当前玩家发言
            logger.debug(f"Requesting speech from Player {player_id}")
            speech = self.safe_execute(player_id, "say")

            # 验证发言格式是否为字符串
            if not isinstance(speech, str):  # 发言内容必须是字符串
                logger.error(
                    f"Player {player_id} returned non-string speech: {type(speech)}.",
                    exc_info=True,  # 输出完整错误堆栈
                )
                # 终止游戏，标记返回值错误
                self.suspend_game(
                    "player_ruturn_ERROR",
                    player_id,
                    "say",
                    f"Returned non-string speech: {type(speech)} during global speech",
                )

            # 记录发言并可能截断过长的内容用于日志
            logger.info(
                f"Global Speech - Player {player_id}: {speech[:100]}{'...' if len(speech) > 100 else ''}"
            )
            # 创建发言事件的快照，用于游戏回放和可视化
            self.battle_observer.make_snapshot(
                "PublicSpeech",
                (player_id, speech[:100] + ("..." if len(speech) > 100 else "")),
            )
            # 保存完整发言内容
            speeches.append((player_id, speech))

            # 通知其他所有玩家当前玩家的发言内容
            logger.debug(f"Broadcasting Player {player_id}'s speech to others.")
            for listener_id in range(1, PLAYER_COUNT + 1):
                if listener_id != player_id:  # 不需要通知发言者自己
                    self.safe_execute(listener_id, "pass_message", (player_id, speech))

        # 将全局发言记录添加到公共日志，便于后续查询
        self.log_public_event(
            {"type": "global_speech", "round": self.current_round, "speeches": speeches}
        )
        logger.info("Global Speech phase complete.")

    def conduct_movement(self):
        """执行玩家移动阶段，允许玩家在游戏地图上移动"""
        # 检查对战状态，如果需要中止游戏则提前退出
        if (
            hasattr(self, "battle_status_checker")  # 检查是否有状态检查器
            and self.battle_status_checker is not None  # 确保状态检查器已初始化
        ):
            if (
                self.battle_status_checker.should_abort()
            ):  # 调用检查方法判断是否应该中止
                # 如果需要中止，获取当前对战状态
                battle_status = self.battle_status_checker.get_battle_status(
                    force=True
                )  # 强制刷新状态
                logger.warning(
                    f"Movement phase aborted: Battle state changed to '{battle_status}'"  # 记录中止原因
                )
                # 抛出游戏终止异常，会被上层函数捕获处理
                raise GameTerminationError(
                    f"Battle status changed to '{battle_status}'"  # 异常信息包含状态
                )

        # 确定移动顺序：从当前队长开始，按照玩家编号顺序安排
        ordered_players = [
            (i - 1) % PLAYER_COUNT + 1  # 计算玩家ID，确保在1-7范围内循环
            for i in range(
                self.leader_index, self.leader_index + PLAYER_COUNT
            )  # 从队长开始遍历所有玩家
        ]
        logger.debug(f"Movement order: {ordered_players}")  # 记录移动顺序

        movements = []  # 存储所有玩家的移动信息

        # 清空地图上的玩家标记，为新的移动做准备
        logger.debug("Clearing player markers from map before movement.")
        for x in range(MAP_SIZE):  # 遍历地图的x坐标
            for y in range(MAP_SIZE):  # 遍历地图的y坐标
                # 检查当前位置是否有玩家标记(1-7数字)
                if self.map_data[x][y] in [str(i) for i in range(1, PLAYER_COUNT + 1)]:
                    self.map_data[x][y] = " "  # 将玩家标记清除为空格

        # 按照确定的顺序依次处理每个玩家的移动
        for player_id in ordered_players:
            # 每个玩家移动前再次检查游戏状态，确保游戏可以继续
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

            # 向玩家传递当前地图上所有玩家的位置信息
            self.safe_execute(player_id, "pass_position_data", self.player_positions)
            logger.debug(f"Sending current map to player {player_id}.")

            # 记录玩家当前位置（深拷贝避免引用问题）
            current_pos = deepcopy(self.player_positions[player_id])
            logger.debug(
                f"Requesting movement from Player {player_id} at {current_pos}"
            )

            # 调用玩家的walk方法获取移动方向
            directions = self.safe_execute(player_id, "walk")

            # 验证返回值类型是否为元组
            if not isinstance(directions, tuple):
                logger.error(
                    f"Player {player_id} returned invalid directions type: {type(directions)}. No movement."
                )
                # 终止游戏，报告返回值错误
                self.suspend_game(
                    "player_ruturn_ERROR",  # 错误类型：玩家返回值错误
                    player_id,  # 错误的玩家ID
                    "walk",  # 错误的方法名
                    f"Returned invalid directions type: {type(directions)}",  # 错误详情
                )

            # 验证移动步数不超过最大限制(3步)
            steps = len(directions)
            if steps > 3:  # 超过3步则报错
                logger.error(
                    f"Player {player_id} returned invalid directions length: {len(directions)}. No movement."
                )
                self.suspend_game(
                    "player_ruturn_ERROR",
                    player_id,
                    "walk",
                    f"Returned invalid directions length: {len(directions)}",
                )

            # 初始化新位置为当前位置
            new_pos = current_pos

            # 用于记录有效的移动方向
            valid_moves = []
            logger.debug(f"Player {player_id} requested moves: {directions}")

            # 处理每一步移动
            for i in range(steps):
                # 验证每个方向是否为字符串类型
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

                # 将方向转为小写进行标准化处理
                direction = directions[i].lower()

                # 记录当前位置坐标
                x, y = deepcopy(new_pos)

                # 根据方向计算新位置坐标，并检查是否超出地图边界
                if direction == "up" and x > 0:  # 向上移动且不超出上边界
                    new_pos = (x - 1, y)  # 更新位置
                    valid_moves.append("up")  # 记录有效移动
                elif direction == "down" and x < MAP_SIZE - 1:  # 向下移动且不超出下边界
                    new_pos = (x + 1, y)
                    valid_moves.append("down")
                elif direction == "left" and y > 0:  # 向左移动且不超出左边界
                    new_pos = (x, y - 1)
                    valid_moves.append("left")
                elif (
                    direction == "right" and y < MAP_SIZE - 1
                ):  # 向右移动且不超出右边界
                    new_pos = (x, y + 1)
                    valid_moves.append("right")
                else:
                    # 无效移动（超出边界或无效方向），抛出错误
                    logger.error(
                        f"Player {player_id} attempted invalid move: {direction}. i_index: {i}"
                    )
                    self.suspend_game(
                        "player_ruturn_ERROR",
                        player_id,
                        "walk",
                        f"Attempted invalid move: {direction}. i_index: {i}",
                    )

                # 检查新位置是否与其他玩家重叠
                if new_pos in [
                    self.player_positions[pid]  # 获取所有其他玩家的位置
                    for pid in range(1, PLAYER_COUNT + 1)
                    if pid != player_id  # 排除当前玩家自己
                ]:
                    # 发现重叠，报告错误
                    logger.error(
                        f"Player {player_id} attempted to move to occupied position: {deepcopy(new_pos)}. i_index: {i}"
                    )
                    self.suspend_game(
                        "player_ruturn_ERROR",
                        player_id,
                        "walk",
                        f"Attempted to move to occupied position: {deepcopy(new_pos)}. i_index: {i}",
                    )

                # 为每一步移动创建快照，用于游戏回放
                self.battle_observer.make_snapshot(
                    "Move",  # 快照类型
                    (
                        player_id,  # 玩家ID
                        [
                            list(valid_moves),
                            deepcopy(new_pos),
                        ],  # 移动详情：已执行的有效移动和新位置
                    ),
                )

            # 记录完整的移动过程
            logger.info(
                f"Movement - Player {player_id}: {current_pos} -> {deepcopy(new_pos)} via {valid_moves}"
            )

            # 更新玩家在游戏状态中的位置
            self.player_positions[player_id] = deepcopy(new_pos)
            x, y = deepcopy(new_pos)
            self.map_data[x][y] = str(player_id)  # 在地图上标记玩家的新位置

            # 记录本次移动的完整信息
            movements.append(
                {
                    "player_id": player_id,  # 玩家ID
                    "requested_moves": list(directions),  # 请求的移动方向
                    "executed_moves": valid_moves,  # 实际执行的移动
                    "final_position": deepcopy(new_pos),  # 最终位置
                }
            )

        # 所有玩家移动完成后再次检查游戏状态
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

        # 向所有玩家更新地图信息
        logger.debug(
            "Updating all players with the new map state and data of positions."
        )
        for player_id in range(1, PLAYER_COUNT + 1):
            # 传递两种数据：位置信息和地图数据
            self.safe_execute(
                player_id, "pass_position_data", self.player_positions
            )  # 所有玩家的位置
            self.safe_execute(
                player_id, "pass_map", deepcopy(self.map_data)
            )  # 整个地图的状态

        # 向公共日志记录本轮所有玩家的移动信息
        self.log_public_event(
            {"type": "movement", "round": self.current_round, "movements": movements}
        )

        # 创建包含所有玩家最终位置的快照
        self.battle_observer.make_snapshot("Positions", self.player_positions)

        # 记录移动阶段完成
        logger.info("Movement phase complete.")

    def conduct_limited_speech(self):
        """进行有限范围发言（只有在听力范围内的玩家能听到）"""
        # 检查游戏对战状态，如果需要终止则提前结束
        if (
            hasattr(self, "battle_status_checker")  # 检查是否有状态检查器
            and self.battle_status_checker is not None  # 确保状态检查器已初始化
        ):
            if (
                self.battle_status_checker.should_abort()
            ):  # 调用检查方法判断是否应该中止
                # 如果需要中止，获取当前对战状态
                battle_status = self.battle_status_checker.get_battle_status(
                    force=True
                )  # 强制刷新状态
                logger.warning(
                    f"Limited speech aborted: Battle state changed to '{battle_status}'"  # 记录中止原因
                )
                # 抛出游戏终止异常，会被上层函数捕获处理
                raise GameTerminationError(
                    f"Battle status changed to '{battle_status}'"  # 异常信息包含状态
                )

        # 确定发言顺序：从当前队长开始，按照玩家编号顺序安排
        ordered_players = [
            (i - 1) % PLAYER_COUNT + 1  # 计算玩家ID，确保在1-7范围内循环
            for i in range(
                self.leader_index, self.leader_index + PLAYER_COUNT
            )  # 从队长开始遍历所有玩家
        ]
        logger.debug(f"Limited speech order: {ordered_players}")  # 记录发言顺序

        speeches = []  # 用于临时存储所有玩家的发言记录
        for speaker_id in ordered_players:  # 按顺序让每个玩家发言
            # 每位玩家发言前再次检查游戏状态
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

            # 请求当前玩家发言
            logger.debug(f"Requesting limited speech from Player {speaker_id}")
            speech = self.safe_execute(
                speaker_id, "say"
            )  # 调用玩家代码的say方法获取发言内容

            # 验证发言格式是否为字符串
            if not isinstance(speech, str):  # 发言内容必须是字符串
                logger.error(
                    f"Player {speaker_id} returned non-string speech: {type(speech)}.",
                    exc_info=True,  # 输出完整错误堆栈
                )
                # 终止游戏，标记返回值错误
                self.suspend_game(
                    "player_ruturn_ERROR",  # 错误类型：玩家返回值错误
                    speaker_id,  # 错误的玩家ID
                    "say",  # 错误的方法名
                    f"Returned non-string speech: {type(speech)} during limited speech",  # 错误详情
                )

            # 记录发言并可能截断过长的内容用于日志
            logger.info(
                f"Limited Speech - Player {speaker_id}: {speech[:100]}{'...' if len(speech) > 100 else ''}"
            )

            speeches.append((speaker_id, speech))  # 将发言记录添加到列表中

            # 确定能听到发言的玩家列表（根据地图位置和角色听力范围）
            hearers = self.get_players_in_hearing_range(
                speaker_id
            )  # 获取在听力范围内的玩家ID列表
            logger.debug(
                f"Player {speaker_id}'s speech heard by: {hearers}"
            )  # 记录能听到的玩家

            # 通知能听到发言的玩家
            for hearer_id in hearers:
                if hearer_id != speaker_id:  # 不需要通知发言者自己
                    # 调用每个听者的pass_message方法，传递发言者ID和发言内容
                    self.safe_execute(hearer_id, "pass_message", (speaker_id, speech))

            # 创建发言事件的快照，用于游戏回放和可视化
            self.battle_observer.make_snapshot(
                "PrivateSpeech",  # 快照类型
                (
                    speaker_id,  # 发言者ID
                    speech[:100]
                    + ("..." if len(speech) > 100 else ""),  # 发言内容（可能截断）
                    " ".join(map(str, hearers)),  # 听者列表，转为空格分隔的字符串
                ),
            )

        # 向公共日志添加有限范围发言记录，但不包含具体发言内容，保持私密性
        self.log_public_event(
            {
                "type": "limited_speech",
                "round": self.current_round,
                # "speeches": speeches,  这里的speech不能人尽皆知，所以不添加到公共日志
            }
        )
        logger.info("Limited Speech phase complete.")  # 记录发言阶段完成

    def get_players_in_hearing_range(self, speaker_id: int) -> List[int]:
        """
        获取能听到指定玩家发言的所有玩家ID列表

        参数:
            speaker_id (int): 发言玩家的ID

        返回:
            List[int]: 能听到发言的玩家ID列表
        """
        # 初始化一个空列表用于存储能听到发言的玩家ID
        hearers = []

        # 获取发言者在地图上的坐标位置
        speaker_x, speaker_y = self.player_positions[speaker_id]

        # 遍历所有玩家，检查每个玩家是否在听力范围内
        for player_id in range(1, PLAYER_COUNT + 1):
            # 获取当前检查的玩家在地图上的坐标位置
            player_x, player_y = self.player_positions[player_id]

            # 计算切比雪夫距离(Chebyshev distance)
            # 这是水平和垂直距离的最大值，相当于国际象棋中国王移动的距离度量
            # 例如：在坐标(3,4)和(1,5)之间的切比雪夫距离是max(|3-1|, |4-5|) = max(2, 1) = 2
            distance = max(abs(player_x - speaker_x), abs(player_y - speaker_y))

            # 获取当前玩家的角色，以确定其听力范围
            role = self.roles[player_id]

            # 从预设的听力范围字典中获取该角色的听力范围，如果没有预设则默认为1
            # 根据游戏规则，Knight和Oberon有更大的听力范围(2)，其他角色为标准范围(1)
            hearing_range = HEARING_RANGE.get(role, 1)

            # 判断玩家是否在听力范围内
            # 如果距离小于等于听力范围，则该玩家可以听到发言
            if distance <= hearing_range:
                hearers.append(player_id)

        # 返回所有能听到发言的玩家ID列表
        return hearers

    def conduct_public_vote(self, mission_members: List[int]) -> int:
        """
        进行公开投票，决定是否执行任务

        这个函数负责收集所有玩家对当前任务队伍的投票，计算支持票数，
        并将投票结果记录到游戏日志中。

        参数:
            mission_members: List[int] - 当前被提名执行任务的队员ID列表

        返回:
            int - 支持该任务队伍的票数
        """
        # 游戏状态检查：如果游戏需要中断（例如由于外部原因），提前结束投票过程
        if (
            hasattr(self, "battle_status_checker")  # 检查是否存在状态检查器属性
            and self.battle_status_checker is not None  # 确保状态检查器已被初始化
        ):
            if (
                self.battle_status_checker.should_abort()
            ):  # 调用检查方法判断是否应该中止
                # 获取当前对战状态（强制刷新）
                battle_status = self.battle_status_checker.get_battle_status(force=True)
                # 记录警告日志
                logger.warning(
                    f"Public vote aborted: Battle state changed to '{battle_status}'"
                )
                # 抛出游戏终止异常，会被上层函数捕获处理
                raise GameTerminationError(
                    f"Battle status changed to '{battle_status}'"
                )

        # 用于存储每个玩家的投票结果，格式为 {玩家ID: 是否支持(布尔值)}
        votes = {}

        # 记录调试日志，显示将要对哪些队员进行投票
        logger.debug(f"Requesting public votes for team: {mission_members}")

        # 依次收集每个玩家的投票
        for player_id in range(1, PLAYER_COUNT + 1):
            # 优化的状态检查：为降低开销，每3个玩家检查一次游戏状态
            if (
                hasattr(self, "battle_status_checker")
                and self.battle_status_checker is not None
                and player_id % 3 == 0  # 只有玩家ID是3的倍数时才检查
            ):
                if self.battle_status_checker.should_abort():  # 检查是否应该中止
                    # 获取最新的对战状态
                    battle_status = self.battle_status_checker.get_battle_status(
                        force=True
                    )
                    # 记录警告日志
                    logger.warning(
                        f"Public vote interrupted: Battle state changed to '{battle_status}'"
                    )
                    # 抛出游戏终止异常
                    raise GameTerminationError(
                        f"Battle status changed to '{battle_status}'"
                    )

            # 调用当前玩家的mission_vote1方法获取投票决定
            # safe_execute确保即使玩家代码出错也不会导致裁判崩溃
            vote = self.safe_execute(player_id, "mission_vote1")

            # 验证投票结果是否为布尔值（True表示同意，False表示拒绝）
            if not isinstance(vote, bool):
                # 记录错误日志，包含完整的异常追踪信息
                logger.error(
                    f"Player {player_id} returned non-bool public vote: {type(vote)}.",
                    exc_info=True,  # 包含完整异常追踪
                )
                # 中止游戏，提供明确的错误原因
                self.suspend_game(
                    "player_ruturn_ERROR",  # 错误类型：玩家返回值错误
                    player_id,  # 出错的玩家ID
                    "mission_vote1",  # 出错的方法名
                    f"Returned non-bool public vote: {type(vote)}",  # 详细错误信息
                )

            # 记录当前玩家的投票结果
            votes[player_id] = vote

            # 记录调试日志，显示每个玩家的投票决定
            logger.debug(
                f"Public Vote - Player {player_id}: {'Approve' if vote else 'Reject'}"
            )

            # 创建投票事件的可视化快照，用于游戏回放
            self.battle_observer.make_snapshot(
                "PublicVote",  # 快照类型
                (
                    player_id,
                    ("Approve" if vote else "Reject"),
                ),  # 快照数据：玩家ID和投票结果
            )

        # 统计支持票数 - 计算投票为True的数量
        approve_count = sum(1 for v in votes.values() if v)

        # 将投票结果添加到公共日志中
        self.log_public_event(
            {
                "type": "public_vote",  # 事件类型
                "round": self.current_round,  # 当前游戏轮次
                "votes": votes,  # 所有玩家的投票记录
                "approve_count": approve_count,  # 支持票总数
                "result": (  # 投票结果（通过/拒绝）
                    "approved"  # 如果支持票数超过半数，则通过
                    if approve_count >= (PLAYER_COUNT // 2 + 1)
                    else "rejected"  # 否则拒绝
                ),
            }
        )

        # 记录投票阶段完成的信息日志
        logger.info("Public Vote phase complete.")

        # 返回支持票数，供上层函数判断任务是否可以继续
        return approve_count

    def execute_mission(self, mission_members: List[int]) -> bool:
        """
        执行任务阶段，获取队员投票并确定任务成功或失败

        参数:
            mission_members: List[int] - 执行当前任务的队员ID列表

        返回:
            bool - 任务是否成功 (True表示成功，False表示失败)
        """
        # 初始化变量：记录每个队员的投票和失败票数量
        votes = {}  # 存储投票结果的字典 {玩家ID: 投票结果(布尔值)}
        fail_votes = 0  # 计数器，记录反对票(失败票)的数量

        # 创建事件快照，用于游戏回放和可视化
        logger.info(f"--- Executing Mission  ---")
        logger.info(
            f"Executing Mission {self.current_round} with members: {mission_members}"
        )
        logger.debug("Requesting mission execution votes (vote2).")

        # 遍历所有参与任务的队员，收集他们的投票
        for player_id in mission_members:
            # 安全调用玩家的mission_vote2方法获取投票决定
            # safe_execute确保即使玩家代码出错也不会导致裁判系统崩溃
            vote = self.safe_execute(player_id, "mission_vote2")

            # 验证投票结果是否为布尔值（True表示支持任务成功，False表示投失败票）
            if not isinstance(vote, bool):
                # 记录错误日志，包含完整的异常追踪信息
                logger.error(
                    f"Player {player_id} returned non-bool mission vote: {type(vote)}.",
                    exc_info=True,  # 包含完整异常堆栈
                )
                # 中止游戏，提供明确的错误原因
                self.suspend_game(
                    "player_ruturn_ERROR",  # 错误类型：玩家返回值错误
                    player_id,  # 出错的玩家ID
                    "mission_vote2",  # 出错的方法名
                    f"Returned non-bool mission vote: {type(vote)}",  # 详细错误信息
                )

            # 规则检查：蓝方角色（好人阵营）不能投失败票
            # 这是阿瓦隆游戏的核心规则之一：好人必须支持任务成功
            if not vote and self.roles[player_id] in BLUE_ROLES:
                # 记录违规行为
                logger.error(
                    f"Blue player {player_id} voted against execution.", exc_info=True
                )
                # 中止游戏，标记违规行为
                self.suspend_game(
                    "player_ruturn_ERROR",  # 错误类型：玩家返回值错误
                    player_id,  # 违规的玩家ID
                    "mission_vote2",  # 违规的方法
                    f"Blue player {player_id} voted against execution.",  # 违规详情
                )

            # 记录当前玩家的投票结果
            votes[player_id] = vote
            # 记录调试信息，包括玩家ID、角色和投票结果
            logger.debug(
                f"Mission Vote - Player {player_id} ({self.roles.get(player_id)}): {'Success' if vote else 'Fail'}"
            )

            # 统计投失败票的数量
            if not vote:  # False表示投失败票
                fail_votes += 1

        # 根据游戏规则判断任务结果
        # 阿瓦隆规则：第3轮和第4轮为"保护轮"，需要至少2票失败才算任务失败
        # 其他轮次只需1票失败即算任务失败
        is_protect_round = self.current_round in [3, 4]  # 检查是否为保护轮
        # 确定导致任务失败所需的最小失败票数
        # 7人及以上游戏中，第3、4轮需要至少2票失败；其他情况只需1票失败
        required_fails = 2 if is_protect_round and PLAYER_COUNT >= 7 else 1
        # 判定任务结果：失败票数少于阈值则任务成功
        mission_success = fail_votes < required_fails

        # 记录任务执行结果及相关信息
        logger.info(
            f"Mission Execution: {fail_votes} Fail votes submitted. Required fails for failure: {required_fails}. Result: {'Success' if mission_success else 'Fail'}"
        )
        # 创建投票结果的可视化快照
        self.battle_observer.make_snapshot("MissionVote", votes)

        # 向公共日志添加任务执行事件（匿名记录，不显示具体谁投了失败票）
        # 这也符合阿瓦隆的规则：玩家只知道有多少失败票，但不知道是谁投的
        self.log_public_event(
            {
                "type": "mission_execution",  # 事件类型
                "round": self.current_round,  # 当前轮次
                "fail_votes": fail_votes,  # 失败票数量
                "success": mission_success,  # 任务是否成功
            }
        )

        # 返回任务执行结果
        return mission_success

    def assassinate_phase(self) -> bool:
        """
        刺杀阶段，由刺客选择一名目标进行刺杀，返回刺杀是否成功（刺中梅林）

        返回:
            bool - 刺杀是否成功，True表示刺中梅林，蓝方失败；False表示未刺中梅林，蓝方胜利
        """
        # 记录刺杀阶段开始的日志
        logger.info("--- Starting Assassination Phase ---")

        # 通过遍历所有玩家的角色，找到担任刺客的玩家ID
        assassin_id = None
        for player_id, role in self.roles.items():
            if role == "Assassin":
                assassin_id = player_id
                break

        # 如果没有找到刺客角色，记录错误并终止游戏
        # 这种情况不应该发生，属于裁判系统内部错误
        if not assassin_id:
            logger.error(
                f"No Assassin found!",
                exc_info=True,  # 在日志中包含完整的异常堆栈
            )
            # 调用中止游戏方法，指明是裁判系统错误
            self.suspend_game(
                "critical_referee_ERROR", 0, "assassinate_phase", "no assassin found"
            )

        # 记录刺客选择目标的信息
        logger.info(f"Assassin (Player {assassin_id}) is choosing a target.")
        # 为刺客选择目标的事件创建一个游戏快照，用于可视化回放
        self.battle_observer.make_snapshot(
            "Event", f"player{assassin_id} choosing a target."
        )

        # 调用刺客玩家的assass方法，获取其选择的目标玩家ID
        # safe_execute确保即使玩家代码出错也不会导致裁判系统崩溃
        target_id = self.safe_execute(assassin_id, "assass")
        logger.debug(f"Assassin {assassin_id} chose target: {target_id}")

        # 验证目标ID是否有效（必须是1-7之间的整数）
        if not isinstance(target_id, int) or target_id < 1 or target_id > PLAYER_COUNT:
            logger.error(
                f"Assassin returned invalid target: {target_id}.",
                exc_info=True,  # 在日志中包含完整的异常堆栈
            )
            # 中止游戏，指明是玩家返回值错误
            self.suspend_game(
                "player_ruturn_ERROR",
                assassin_id,
                "assass",
                f"Assassin returned invalid target: {target_id}",
            )

        # 检查刺客是否选择了自己作为刺杀目标（这是一种错误情况）
        if target_id == assassin_id:
            logger.error(
                f"Assassin {assassin_id} targeted himself.",
                exc_info=True,  # 在日志中包含完整的异常堆栈
            )
            # 中止游戏，并显示一个幽默的错误信息
            self.suspend_game(
                "player_ruturn_ERROR",
                assassin_id,
                "assass",
                f"""Assassin {assassin_id} targeted himself.  
                    FOOL Assassin! FOOL Assassin! FOOL Assassin! FOOL Assassin!""",
            )

        # 确定目标玩家的角色，判断刺杀是否成功
        target_role = self.roles[target_id]
        success = target_role == "Merlin"  # 如果目标是梅林，则刺杀成功

        # 记录刺杀结果的详细信息
        logger.info(
            f"Assassination: Player {assassin_id} targeted Player {target_id} ({target_role}). Result: {'Success' if success else 'Fail'}"
        )

        # 为刺杀事件创建一个详细的游戏快照
        self.battle_observer.make_snapshot(
            "Assass",
            [assassin_id, target_id, target_role, ("Success" if success else "Fail")],
        )

        # 将刺杀事件及结果添加到公共日志中
        self.log_public_event(
            {
                "type": "assassination",  # 事件类型
                "assassin": assassin_id,  # 刺客ID
                "target": target_id,  # 目标ID
                "target_role": self.roles[target_id],  # 目标角色
                "success": success,  # 刺杀是否成功
            }
        )

        # 记录刺杀阶段完成的日志
        logger.info("--- Assassination Phase Complete ---")

        # 返回刺杀结果：成功(True)表示刺中梅林，游戏由红方胜利；失败(False)表示未刺中梅林，蓝方胜利
        return success

    def run_game(self) -> Dict[str, Any]:
        """
        运行游戏的主控制函数，管理整个游戏流程并返回最终结果

        返回:
            Dict[str, Any]: 包含游戏结果的字典，包括胜负情况、角色分配等信息
        """
        # 记录游戏开始的日志信息并创建游戏开始的快照
        logger.info(f"===== Starting Game {self.game_id} =====")
        self.battle_observer.make_snapshot("GameStart", self.game_id)

        # 初始化对战状态检查器，用于监控游戏是否需要中断
        try:
            # 创建状态检查器，不依赖Flask上下文，避免"Working outside of application context"错误
            self.battle_status_checker = BattleStatusChecker(self.game_id)
        except Exception as e:
            # 如果无法初始化状态检查器，记录错误但继续游戏流程
            logger.error(f"Error initializing battle status checker: {str(e)}")
            self.battle_status_checker = None

        # 内部函数：检查是否需要中止游戏
        def check_abort():
            """
            检查当前对战状态，如果需要中止游戏则返回标准格式的游戏结果

            返回:
                Dict或None: 如果需要中止，返回包含游戏结果的字典；否则返回None
            """
            # 如果状态检查器不存在或未初始化，则跳过检查
            if (
                not hasattr(self, "battle_status_checker")
                or self.battle_status_checker is None
            ):
                return None

            # 调用状态检查器判断是否需要中断游戏
            if self.battle_status_checker.should_abort():
                # 获取当前的对战状态
                battle_status = self.battle_status_checker.get_battle_status()

                # 构建标准格式的角色信息字典，用于结果记录
                roles_dict = {}
                if hasattr(self, "roles") and self.roles:
                    # 保留整数键格式，方便后续处理
                    for player_id, role in self.roles.items():
                        roles_dict[player_id] = role

                    # 记录角色分配信息，便于调试
                    logger.info(f"Game {self.game_id} aborted with roles: {roles_dict}")

                # 准备游戏中止结果
                game_result = {
                    "blue_wins": self.blue_wins,  # 蓝方（好人方）胜利轮数
                    "red_wins": self.red_wins,  # 红方（坏人方）胜利轮数
                    "rounds_played": self.current_round,  # 已完成的轮数
                    "roles": roles_dict,  # 角色分配情况
                    "public_log_file": os.path.join(  # 公共日志文件路径
                        self.data_dir, f"game_{self.game_id}_public.json"
                    ),
                    "winner": None,  # 由于中止，无胜利方
                    "win_reason": f"aborted_due_to_battle_state_{battle_status}",  # 中止原因
                }

                # 记录中止信息
                logger.info(f"Game aborted: Battle state is '{battle_status}'")

                # 向公共日志添加游戏中止事件
                self.log_public_event({"type": "game_aborted", "result": game_result})

                # 创建游戏中止的观察者快照
                self.battle_observer.make_snapshot("GameAborted", self.game_id)

                # 返回中止结果
                return game_result

            # 如果不需要中止，返回None
            return None

        # 主游戏流程的try-except结构，用于捕获和处理各种异常
        try:
            # === 游戏初始化阶段 ===

            # 初始化游戏（分配角色、初始化地图等）
            self.init_game()

            # 初始化后检查是否需要中止
            abort_result = check_abort()
            if abort_result:
                return abort_result

            # === 夜晚阶段 ===

            # 执行夜晚阶段（各角色获取视野信息）
            self.night_phase()

            # 夜晚阶段后检查是否需要中止
            abort_result = check_abort()
            if abort_result:
                return abort_result

            # === 任务循环阶段 ===

            # 循环执行任务，直到某方获得3次胜利或达到最大轮数限制
            while (
                self.blue_wins < 3  # 蓝方未获得3次胜利
                and self.red_wins < 3  # 红方未获得3次胜利
                and self.current_round < MAX_MISSION_ROUNDS  # 未达到最大轮数限制
            ):
                try:
                    # 执行一轮任务（包括队长选人、发言、移动、投票等）
                    self.run_mission_round()
                except GameTerminationError as e:
                    # 如果任务中途需要终止
                    logger.warning(f"Mission round terminated: {str(e)}")

                    # 检查是否由于对战状态变化需要中止
                    abort_result = check_abort()
                    if abort_result:
                        return abort_result
                    else:
                        # 如果check_abort没有返回结果但游戏需要终止
                        # 构建标准的终止结果
                        roles_dict = {}
                        if hasattr(self, "roles") and self.roles:
                            for player_id, role in self.roles.items():
                                roles_dict[player_id] = role

                            logger.info(
                                f"Game {self.game_id} terminated with roles: {roles_dict}"
                            )

                        # 返回终止结果
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

                # 每轮任务结束后检查是否需要中止
                abort_result = check_abort()
                if abort_result:
                    return abort_result

            # === 游戏结束阶段 ===

            # 记录游戏结束信息
            logger.info("===== Game Over =====")
            self.battle_observer.make_snapshot("GameEnd", self.game_id)
            logger.info(
                f"Final Score: Blue {self.blue_wins} - Red {self.red_wins} after {self.current_round} rounds."
            )
            self.battle_observer.make_snapshot(
                "FinalScore", [self.blue_wins, self.red_wins]
            )

            # 构建标准格式的角色信息字典
            roles_dict = {}
            if hasattr(self, "roles") and self.roles:
                for player_id, role in self.roles.items():
                    roles_dict[player_id] = role

                logger.info(f"Game {self.game_id} final role assignments: {roles_dict}")

            # 准备游戏结果
            game_result = {
                "blue_wins": self.blue_wins,
                "red_wins": self.red_wins,
                "rounds_played": self.current_round,
                "roles": roles_dict,
                "public_log_file": os.path.join(
                    self.data_dir, f"game_{self.game_id}_public.json"
                ),
            }

            # === 蓝方达成三次任务后的刺杀阶段 ===
            if self.blue_wins >= 3:
                logger.info(
                    "Blue team completed 3 missions. Proceeding to assassination."
                )

                # 进入刺杀阶段前检查是否需要中止
                abort_result = check_abort()
                if abort_result:
                    return abort_result

                # 执行刺杀阶段
                assassination_success = self.assassinate_phase()

                # 根据刺杀结果确定最终胜利方
                if assassination_success:  # 刺杀成功（刺客找到了梅林）
                    game_result.update(
                        {"winner": "red", "win_reason": "assassination_success"}
                    )
                    self.battle_observer.make_snapshot(
                        "GameResult", ["Red", "Assassination Success"]
                    )
                    logger.info(
                        f"Game {self.game_id} result: RED wins by assassination"
                    )
                else:  # 刺杀失败（刺客未找到梅林）
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
            elif self.red_wins >= 3:  # 红方达成三次任务，直接胜利
                game_result.update({"winner": "red", "win_reason": "missions_failed"})
                self.battle_observer.make_snapshot(
                    "GameResult", ["Red", "3 Failed Missions"]
                )
                logger.info(
                    f"Game {self.game_id} result: RED wins by completing 3 failed missions"
                )

            # === 结果验证与完善 ===

            # 确保roles字段存在
            if "roles" not in game_result or not game_result["roles"]:
                logger.warning(f"Game {self.game_id} missing roles data in result")
                game_result["roles"] = {}

            # 确保winner字段存在
            if "winner" not in game_result:
                logger.warning(f"Game {self.game_id} missing winner in result")
                # 根据胜利次数判断胜方
                if self.blue_wins > self.red_wins:
                    game_result["winner"] = "blue"
                elif self.red_wins > self.blue_wins:
                    game_result["winner"] = "red"
                else:
                    # 平局情况
                    game_result["winner"] = None

            # 记录最终游戏结果
            logger.info(
                f"Final game result for {self.game_id}: {json.dumps(game_result, default=str)}"
            )

            # 向公共日志记录token使用情况和游戏结束事件
            self.log_public_event(
                {"type": "tokens", "result": self.game_helper.get_tokens()}
            )
            self.log_public_event({"type": "game_end", "result": game_result})

            # 记录游戏完成
            logger.info(f"===== Game {self.game_id} Finished =====")
            self.battle_observer.make_snapshot("GameEnd", self.game_id)

            # 返回最终结果
            return game_result

        # === 异常处理部分 ===

        except GameTerminationError as e:
            # 处理游戏终止异常（由对战状态改变触发）
            logger.error(f"Game terminated due to battle status change: {str(e)}")

            # 构建角色信息字典
            roles_dict = {}
            if hasattr(self, "roles") and self.roles:
                for player_id, role in self.roles.items():
                    roles_dict[player_id] = role

                logger.info(f"Game {self.game_id} terminated with roles: {roles_dict}")

            # 准备终止结果
            terminate_result = {
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

            # 记录终止事件
            self.log_public_event(
                {"type": "game_terminated", "result": terminate_result}
            )
            return terminate_result

        except Exception as e:
            # 处理其他未预期的异常
            logger.error(
                f"Critical error during game {self.game_id}: {str(e)}", exc_info=True
            )

            # 构建角色信息字典
            roles_dict = {}
            if hasattr(self, "roles") and self.roles:
                for player_id, role in self.roles.items():
                    roles_dict[player_id] = role

                logger.info(f"Game {self.game_id} crashed with roles: {roles_dict}")

            # 准备错误结果
            error_result = {
                "error": f"Critical Error: {str(e)}",
                "blue_wins": self.blue_wins,
                "red_wins": self.red_wins,
                "rounds_played": self.current_round,
                "roles": roles_dict,
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

        参数:
            player_id: int - 要执行代码的玩家ID
            method_name: str - 要调用的玩家类方法名
            *args - 传递给方法的位置参数
            **kwargs - 传递给方法的关键字参数

        返回:
            方法执行的结果，如果出错则由错误处理逻辑决定
        """
        # 获取玩家对象，检查玩家是否存在
        player = self.players.get(player_id)
        if not player:
            # 如果指定ID的玩家不存在，记录错误日志
            logger.error(
                f"Attempted to execute method '{method_name}' for non-existent player {player_id}"
            )

        # 尝试获取玩家对象中指定的方法
        method = getattr(player, method_name, None)
        if not method or not callable(method):
            # 如果方法不存在或不可调用，记录错误并使用默认行为
            logger.error(
                f"Player {player_id} has no callable method '{method_name}'. Using default behavior."
            )
            # 针对不同方法提供默认实现
            if method_name == "decide_mission_member":
                # 随机选择队员（args[0]应该是需要的队员数量）
                return self.random_select_members(args[0])
            if method_name == "assass":
                # 随机选择一个非自己的玩家作为刺杀目标
                return random.choice(
                    [i for i in range(1, PLAYER_COUNT + 1) if i != player_id]
                )
            if method_name == "say":
                # 默认发言为省略号
                return "..."
            if method_name == "walk":
                # 默认不移动
                return ()
            # 其他方法默认返回None
            if method_name in ["pass_message", "pass_map", "pass_position_data"]:
                return None
            return None

        try:
            # 设置当前上下文环境
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

            # 记录执行信息
            logger.debug(
                f"Executing Player {player_id}.{method_name} with args: {args}, kwargs: {kwargs}"
            )

            # 记录开始时间以检测执行时长
            start_time = time.time()

            # 以下被注释的代码是用于捕获玩家代码输出的，目前未启用
            # stdout_capture = StringIO()
            # stderr_capture = StringIO()
            # with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):

            # 执行玩家方法
            result = method(*args, **kwargs)

            # 计算执行时间
            execution_time = time.time() - start_time

            # 记录方法返回值和执行时间
            logger.debug(
                f"Player {player_id}.{method_name} returned: {result} (took {execution_time:.4f}s)"
            )

            # 检查执行时间是否超过阈值
            if execution_time > MAX_EXECUTION_TIME:  # 执行时间过长视为超时
                logger.error(
                    f"Player {player_id} ({self.roles.get(player_id)}) method {method_name} took {execution_time:.2f} seconds (timeout)"
                )
                # 中止游戏，报告超时错误
                self.suspend_game(
                    "critical_player_ERROR",
                    player_id,
                    method_name,
                    f"执行超时，超过{MAX_EXECUTION_TIME}秒",
                )

            # 返回方法执行结果
            return result

        except Exception as e:  # 捕获玩家代码执行过程中的所有异常
            # 记录详细的错误信息，包括完整堆栈跟踪
            logger.error(
                f"Error executing Player {player_id} ({self.roles.get(player_id)}) method '{method_name}': {str(e)}",
                exc_info=True,  # 包含异常堆栈信息
            )
            # 中止游戏，报告关键错误
            self.suspend_game("critical_player_ERROR", player_id, method_name, str(e))

    def log_public_event(self, event: Dict[str, Any]):
        """
        记录公共事件到日志

        该函数负责将游戏事件记录到公共日志中，方便后续查询和游戏回放。

        参数:
            event (Dict[str, Any]): 要记录的事件数据，是一个字典，包含事件类型和相关信息

        工作流程:
            1. 向事件添加时间戳和当前轮次信息
            2. 将事件添加到内存中的日志列表
            3. 将更新后的日志列表写入JSON文件
        """
        # 添加时间戳，格式为"年-月-日 时:分:秒.毫秒"，去掉最后3位（截断到毫秒）
        event["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # 添加当前轮次编号，确保每个事件都有轮次信息，便于分析和回放
        event["round"] = self.current_round

        # 记录调试日志，显示正在记录的事件内容
        logger.debug(f"Logging public event: {event}")

        # 将事件添加到内存中的日志列表，用于后续查询和记录
        self.public_log.append(event)

        # 构建公共日志文件的完整路径
        public_log_file = os.path.join(
            self.data_dir, f"game_{self.game_id}_public.json"
        )

        try:
            # 打开日志文件并以写入模式覆盖之前的内容
            # 使用utf-8编码确保支持多语言字符
            with open(public_log_file, "w", encoding="utf-8") as f:
                # 将整个日志列表序列化为JSON格式并写入文件
                # ensure_ascii=False 允许写入非ASCII字符而不进行转义
                # indent=2 使得输出的JSON格式美观易读
                json.dump(self.public_log, f, ensure_ascii=False, indent=2)

        except Exception as e:
            # 如果写入过程中发生错误（如文件权限问题或磁盘空间不足），记录错误信息
            logger.error(f"Error writing public log: {str(e)}")

    def suspend_game(
        self,
        game_error_type: str,  # 错误类型，有三种可能:
        # - "critical_referee_ERROR": 来自裁判系统(referee)的严重错误
        # - "critical_player_ERROR": 来自用户代码的严重错误（如未捕获的异常）
        # - "player_return_ERROR": 用户代码的返回值不符合规范（格式错误）
        error_code_pid: int,  # 出错的玩家ID，如果是裁判系统错误则为0
        error_code_method_name: str,  # 出错的方法名
        error_msg: str,  # 详细的错误信息
    ):
        """
        一键中止游戏函数

        当游戏出现不可恢复的错误时调用此函数，统一处理游戏中止逻辑。
        该函数取代了代码中多处重复的错误处理和游戏中止逻辑。

        参数:
            game_error_type: 错误类型（"critical_referee_ERROR"/"critical_player_ERROR"/"player_return_ERROR"）
            error_code_pid: 出错的玩家ID（裁判系统错误则为0）
            error_code_method_name: 出错的方法名
            error_msg: 详细的错误信息

        行为:
            1. 记录错误信息到公共日志
            2. 向观察者发送错误快照
            3. 抛出RuntimeError终止游戏
        """
        # 根据错误来源（玩家代码或裁判系统）构建不同的错误信息
        SUSPEND_BROADCAST_MSG = (
            # 如果是玩家代码错误
            (
                f"Error executing Player {error_code_pid} method {error_code_method_name}: "
                + error_msg
                + ". Game suspended."
            )
            if error_code_pid > 0
            # 如果是裁判系统错误
            else (
                f"Referee error during {error_code_method_name}: {error_msg}. Game suspended."
            )
        )

        # 1. 记录token使用情况到公共日志
        self.log_public_event(
            {"type": "tokens", "result": self.game_helper.get_tokens()}
        )

        # 2. 记录详细错误信息到公共日志
        self.log_public_event(
            {
                "type": game_error_type,  # 错误类型
                "error_code_pid": error_code_pid,  # 出错的玩家ID
                "error_code_method": error_code_method_name,  # 出错的方法名
                "error_msg": error_msg,  # 详细错误信息
            }
        )

        # 3. 向观察者发送错误快照，用于游戏回放和可视化
        self.battle_observer.make_snapshot("Bug", SUSPEND_BROADCAST_MSG)

        # 4. 抛出运行时错误，中止游戏执行
        # 该异常会被run_game方法捕获并转化为游戏结果
        raise RuntimeError(SUSPEND_BROADCAST_MSG)

    def random_select_members(self, member_count: int) -> List[int]:
        """
        随机选择指定数量的队员

        作为decide_mission_member方法的默认实现，当队长未提供有效的队伍选择时使用。

        参数:
            member_count (int): 需要选择的队员数量

        返回:
            List[int]: 随机选择的队员ID列表

        行为:
            - 从所有玩家中随机选择指定数量的玩家
            - 确保选择的队员数量不超过总玩家数
            - 采用不放回抽样，确保每个玩家最多被选择一次
        """
        # 获取所有玩家ID列表(1到7)
        all_players = list(range(1, PLAYER_COUNT + 1))

        # 确保请求的队员数量不会超过可用的玩家总数
        # 如果超过，则取可用的最大值
        member_count = min(member_count, PLAYER_COUNT)

        # 使用random.sample进行随机抽样不放回
        # 从all_players中随机选择member_count个元素
        # 这确保了选出的队员列表中没有重复
        return random.sample(all_players, member_count)
