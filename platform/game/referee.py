"""
裁判系统 - 负责执行游戏规则和管理游戏状态
"""
import os
import sys
import time
import json
import logging
import importlib.util
import traceback
import threading
import random
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from typing import Dict, List, Any, Optional, Tuple, Set

# 游戏常量
PLAYER_COUNT = 7
MISSION_MEMBER_COUNT = [2, 3, 3, 4, 4]  # 每轮任务需要的成员数
ROLES = {
    "Merlin": "blue",
    "Percival": "blue",
    "Knight1": "blue",
    "Knight2": "blue", 
    "Assassin": "red",
    "Morgana": "red",
    "Oberon": "red"
}

logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Referee")

class AvalonReferee:
    """阿瓦隆游戏裁判"""
    
    def __init__(self, game_id: str, data_dir: str):
        """
        初始化裁判
        
        参数:
            game_id: 游戏唯一标识符
            data_dir: 数据存储目录
        """
        self.game_id = game_id
        self.data_dir = data_dir
        
        # 游戏状态
        self.players = {}  # 玩家实例 {player_id: player_instance}
        self.roles = {}  # 玩家角色 {player_id: role_name}
        self.leader_index = 1  # 队长索引，从1开始
        self.current_round = 0  # 当前轮数
        self.failed_votes = 0  # 连续失败的提议投票
        self.blue_wins = 0  # 蓝队获胜次数
        self.red_wins = 0  # 红队获胜次数
        
        # 初始化日志文件
        self._init_log_files()
        
        logger.info(f"裁判初始化完成，游戏ID: {game_id}")
    
    def _init_log_files(self):
        """初始化游戏日志文件"""
        # 确保目录存在
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 初始化公共日志文件
        public_log_file = os.path.join(self.data_dir, f"game_{self.game_id}_public.json")
        with open(public_log_file, "w", encoding="utf-8") as f:
            json.dump({"events": []}, f)
        
        # 为每个玩家初始化私有日志文件
        for player_id in range(1, PLAYER_COUNT + 1):
            private_log_file = os.path.join(
                self.data_dir, f"game_{self.game_id}_player_{player_id}_private.json"
            )
            with open(private_log_file, "w", encoding="utf-8") as f:
                json.dump({"logs": []}, f)
                
        logger.info(f"日志文件已初始化，位于 {self.data_dir}")
    
    def load_player_codes(self, player_codes: Dict[int, str]) -> Dict[int, Any]:
        """
        加载玩家代码，动态创建模块并执行
        
        参数:
            player_codes: 玩家代码字典 {player_id: code_content}
            
        返回:
            玩家模块字典 {player_id: module}
        """
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
                
                # 执行代码
                exec(code_content, module.__dict__)
                
                # 检查Player类是否存在
                if not hasattr(module, "Player"):
                    logger.error(f"玩家 {player_id} 的代码已执行但未找到 'Player' 类")
                    continue
                
                # 存储模块
                player_modules[player_id] = module
                logger.info(f"玩家 {player_id} 代码加载成功")
                
            except Exception as e:
                logger.error(f"加载玩家 {player_id} 代码时出错: {str(e)}")
                traceback.print_exc()
        
        return player_modules
    
    def _initialize_players(self, player_modules: Dict[int, Any]):
        """
        初始化玩家实例
        
        参数:
            player_modules: 玩家模块字典 {player_id: module}
        """
        logger.info(f"为 {len(player_modules)} 个玩家初始化实例")
        self.players = {} # 确保每次初始化时清空旧的玩家实例
        
        for player_id, module in player_modules.items():
            try:
                # 实例化Player类
                player_instance = module.Player()
                self.players[player_id] = player_instance
                
                # 设置玩家编号
                self.safe_execute(player_id, "set_player_index", player_id)
                # 确认玩家实例已添加
                if player_id in self.players:
                     logger.info(f"玩家 {player_id} 实例创建并存储成功")
                else:
                     logger.error(f"玩家 {player_id} 实例创建后未能存储")

            except Exception as e:
                logger.error(f"初始化玩家 {player_id} 实例时出错: {str(e)}")
                traceback.print_exc()
                # 即使出错，也尝试继续初始化其他玩家
    
    def _assign_roles(self):
        """分配玩家角色"""
        role_names = list(ROLES.keys())
        random.shuffle(role_names)
        
        for player_id in range(1, PLAYER_COUNT + 1):
            if player_id <= len(role_names):
                self.roles[player_id] = role_names[player_id - 1]
        
        logger.info(f"角色分配完成: {self.roles}")
        self.log_public_event({"type": "roles_assigned"})
    
    def safe_execute(self, player_id: int, method_name: str, *args, **kwargs):
        """
        安全执行玩家代码方法，处理可能的异常
        
        参数:
            player_id: 玩家ID
            method_name: 要执行的方法名
            *args, **kwargs: 传递给方法的参数
            
        返回:
            方法执行结果或None(如果出错)
        """
        player = self.players.get(player_id)
        if not player:
            logger.error(f"尝试为不存在的玩家 {player_id} 执行方法 '{method_name}'")
            return None
            
        method = getattr(player, method_name, None)
        if not method:
            logger.error(f"玩家 {player_id} 没有方法 '{method_name}'")
            return None
            
        # 设置游戏辅助模块的上下文
        from game_helper import set_current_context
        set_current_context(player_id, self.game_id)
        
        try:
            # 创建超时线程
            result = [None]
            exception = [None]
            completed = [False]
            
            def execute_method():
                try:
                    result[0] = method(*args, **kwargs)
                    completed[0] = True
                except Exception as e:
                    exception[0] = e
                    logger.error(f"玩家 {player_id} 执行方法 '{method_name}' 时出错: {str(e)}")
                    traceback.print_exc()
            
            # 启动执行线程
            thread = threading.Thread(target=execute_method)
            thread.start()
            thread.join(timeout=3.0)  # 3秒超时
            
            if thread.is_alive():
                logger.warning(f"玩家 {player_id} 方法 '{method_name}' 执行超时")
                return None
                
            if exception[0]:
                return None
                
            return result[0]
            
        except Exception as e:
            logger.error(f"安全执行方法时出错: {str(e)}")
            return None
    
    def log_public_event(self, event_data: Dict[str, Any]):
        """
        记录公共事件到日志
        
        参数:
            event_data: 事件数据
        """
        try:
            event_data["timestamp"] = time.time()
            
            log_file = os.path.join(self.data_dir, f"game_{self.game_id}_public.json")
            with open(log_file, "r", encoding="utf-8") as f:
                log_data = json.load(f)
                
            log_data["events"].append(event_data)
            
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2)
                
        except Exception as e:
            logger.error(f"记录公共事件时出错: {str(e)}")
    
    def run_night_phase(self):
        """执行夜晚阶段，向特殊角色传递信息"""
        logger.info("开始夜晚阶段")
        self.log_public_event({"type": "night_phase_start"})
        
        # 向梅林传递邪恶方信息
        merlin_id = [pid for pid, role in self.roles.items() if role == "Merlin"]
        if merlin_id:
            merlin_id = merlin_id[0]
            evil_players = {pid for pid, role in self.roles.items() 
                           if ROLES[role] == "red"}
            logger.debug(f"向梅林(玩家 {merlin_id})发送邪恶方信息: {evil_players}")
            self.safe_execute(merlin_id, "receive_evil_knowledge", evil_players)
        
        # 向刺客和莫甘娜传递彼此信息
        evil_ids = [pid for pid, role in self.roles.items() if ROLES[role] == "red"]
        for evil_id in evil_ids:
            other_evils = {pid for pid in evil_ids if pid != evil_id}
            logger.debug(f"向邪恶玩家 {evil_id} 发送其他邪恶玩家信息: {other_evils}")
            self.safe_execute(evil_id, "receive_evil_allies", other_evils)
        
        self.log_public_event({"type": "night_phase_complete"})
        logger.info("夜晚阶段完成")
    
    def run_mission_round(self) -> Optional[bool]:
        """执行一轮任务. 返回任务成功 (True/False) 或 None (如果游戏因投票失败结束)"""
        self.current_round += 1
        # 检查轮数是否超出限制
        if self.current_round > len(MISSION_MEMBER_COUNT):
            logger.error(f"尝试开始第 {self.current_round} 轮任务，但最多只有 {len(MISSION_MEMBER_COUNT)} 轮。")
            return None # 表示游戏应结束

        member_count = MISSION_MEMBER_COUNT[self.current_round - 1]
        mission_success = None
        
        logger.info(f"--- 开始任务轮 {self.current_round} ---")
        logger.info(f"队长: 玩家 {self.leader_index}, 需要成员数: {member_count}")
        
        self.log_public_event({
            "type": "mission_start",
            "round": self.current_round,
            "leader": self.leader_index,
            "member_count": member_count
        })
        
        # 队长选择任务成员逻辑
        team_proposal = self.safe_execute(self.leader_index, "propose_team", member_count)
        # 验证队伍提议
        valid_proposal = isinstance(team_proposal, set) and \
                         len(team_proposal) == member_count and \
                         all(isinstance(p, int) and 1 <= p <= PLAYER_COUNT for p in team_proposal)

        if not valid_proposal:
            logger.error(f"队长 {self.leader_index} 提供了无效的队伍提议: {team_proposal}. 需要 {member_count} 个成员.")
            # 如果提议无效，使用默认随机队伍
            available_players = list(range(1, PLAYER_COUNT + 1))
            if self.leader_index in available_players: # 队长通常应在队伍中？（规则不强制，但常见）
                 default_team = {self.leader_index}
                 available_players.remove(self.leader_index)
                 default_team.update(random.sample(available_players, member_count - 1))
                 team_proposal = default_team
            else: # 如果队长ID无效或不在1-5范围内
                 team_proposal = set(random.sample(available_players, member_count))
            logger.warning(f"使用默认随机队伍: {team_proposal}")

        # 全体投票决定是否接受队伍
        votes = {}
        for player_id in range(1, PLAYER_COUNT + 1):
            vote = self.safe_execute(player_id, "vote_for_team", team_proposal)
            votes[player_id] = bool(vote) # 转换为布尔值
        
        # 计票
        approve_count = sum(1 for v in votes.values() if v)
        team_approved = approve_count > PLAYER_COUNT / 2
        
        self.log_public_event({
            "type": "team_vote",
            "team": sorted(list(team_proposal)), # 排序以保证一致性
            "votes": {str(k): v for k, v in votes.items()}, # 确保键是字符串
            "approved": team_approved
        })
        
        if team_approved:
            self.failed_votes = 0 # 重置连续失败次数
            logger.info(f"队伍 {team_proposal} 被批准 ({approve_count} 票赞成)")
            # 任务成员进行任务投票
            mission_votes = {}
            for player_id in team_proposal:
                action = self.safe_execute(player_id, "mission_action")
                mission_votes[player_id] = bool(action) # 转换为布尔值
            
            # 计算任务结果
            fail_count = sum(1 for v in mission_votes.values() if not v)
            mission_success = fail_count == 0
            
            self.log_public_event({
                "type": "mission_result",
                "success": mission_success,
                "fail_count": fail_count,
                "team": sorted(list(team_proposal)) # 添加队伍信息
            })
            
            # 更新任务结果
            if mission_success:
                self.blue_wins += 1
                logger.info(f"任务成功! 蓝队得分: {self.blue_wins}, 红队得分: {self.red_wins}")
            else:
                self.red_wins += 1
                logger.info(f"任务失败! ({fail_count} 票失败) 蓝队得分: {self.blue_wins}, 红队得分: {self.red_wins}")
        else:
            self.failed_votes += 1
            logger.info(f"队伍 {team_proposal} 被否决 ({approve_count} 票赞成). 连续否决次数: {self.failed_votes}")
            # 检查是否连续5次失败
            if self.failed_votes >= 5:
                logger.warning("连续5次投票失败，红队获胜!")
                self.log_public_event({
                    "type": "game_end_failed_votes",
                    "reason": "5 consecutive failed team votes"
                })
                return None # 返回 None 表示游戏应结束

            # 更新队长
            self.leader_index = (self.leader_index % PLAYER_COUNT) + 1
            
            # 修复：返回特殊值表示"继续游戏"而不是返回未初始化的mission_success
            return "continue_game"  # 返回特殊标记，表示投票失败但游戏应继续

        return mission_success

    
    def run_assassination_phase(self):
        """执行刺杀阶段"""
        logger.info("开始刺杀阶段")
        self.log_public_event({"type": "assassination_phase_start"})
        
        # 找到刺客
        assassin_id = None
        for player_id, role in self.roles.items():
            if role == "Assassin":
                assassin_id = player_id
                break
        
        if not assassin_id:
            logger.error("找不到刺客角色")
            return False
        
        # 刺客选择目标
        target = self.safe_execute(assassin_id, "choose_assassination_target")
        if not isinstance(target, int) or target < 1 or target > PLAYER_COUNT:
            logger.error(f"刺客 {assassin_id} 提供了无效的刺杀目标")
            # 随机选择一个非刺客的玩家
            valid_targets = [pid for pid in range(1, PLAYER_COUNT + 1) if pid != assassin_id]
            target = random.choice(valid_targets)
        
        # 检查是否刺杀梅林
        merlin_killed = self.roles.get(target) == "Merlin"
        
        self.log_public_event({
            "type": "assassination_result",
            "assassin": assassin_id,
            "target": target,
            "merlin_killed": merlin_killed
        })
        
        logger.info(f"刺杀阶段结束, 目标: 玩家 {target}, 梅林被杀: {merlin_killed}")
        return merlin_killed
    
    def run_game(self) -> Dict[str, Any]:
        """
        运行完整游戏
        
        返回:
            游戏结果字典
        """
        try:
            # 确保玩家已初始化
            if not self.players:
                 logger.error("玩家未初始化，无法开始游戏。")
                 return {"error": "Players not initialized"}

            logger.info(f"开始游戏 {self.game_id}")
            self.log_public_event({"type": "game_start", "game_id": self.game_id})
            
            # 分配角色
            self._assign_roles()
            
            # 夜晚阶段
            self.run_night_phase()
            
            # 任务阶段
            game_end = False
            final_winner = None # 初始化获胜者

            while not game_end:
                # 在开始新一轮前检查是否已达到最大轮数但无胜者
                if self.current_round >= len(MISSION_MEMBER_COUNT) and self.blue_wins < 3 and self.red_wins < 3:
                     logger.warning(f"已完成 {len(MISSION_MEMBER_COUNT)} 轮任务但无胜者或5次投票失败，判定红队获胜。")
                     final_winner = "red"
                     game_end = True
                     break

                mission_result = self.run_mission_round()
                
                if mission_result is None:
                    # 游戏因5次投票失败而结束
                    final_winner = "red"
                    game_end = True
                elif mission_result == "continue_game":
                    # 新增：投票失败但未达到5次，继续游戏
                    continue
                elif self.blue_wins >= 3:
                    # 蓝队通过三次任务，进入刺杀阶段
                    logger.info("蓝队已通过三次任务，进入刺杀阶段")
                    merlin_killed = self.run_assassination_phase()
                    
                    if merlin_killed:
                        logger.info("梅林被成功刺杀，红队获胜!")
                        final_winner = "red"
                    else:
                        logger.info("梅林存活，蓝队获胜!")
                        final_winner = "blue"
                    
                    game_end = True
                    
                elif self.red_wins >= 3:
                    # 红队通过三次任务直接获胜
                    logger.info("红队已通过三次任务，红队获胜!")
                    final_winner = "red"
                    game_end = True

            # 记录游戏结束
            if final_winner is None:
                logger.error("游戏循环意外结束，未确定获胜者。默认为红队获胜。")
                final_winner = "red" # 设置默认值以防万一

            end_event_data = {
                "type": "game_end",
                "winner": final_winner,
                "blue_wins": self.blue_wins,
                "red_wins": self.red_wins,
                "roles": {str(k): v for k, v in self.roles.items()} # 确保键是字符串
            }
            self.log_public_event(end_event_data)
            
            # 返回游戏结果
            return {
                "winner": final_winner,
                "blue_wins": self.blue_wins,
                "red_wins": self.red_wins,
                "roles": {str(k): v for k, v in self.roles.items()},
                "rounds_played": self.current_round
            }
            
        except Exception as e:
            logger.error(f"游戏执行过程中出错: {str(e)}")
            traceback.print_exc()
            # 尝试记录包含错误的游戏结束事件
            error_end_event = {
                "type": "game_end",
                "winner": "error",
                "error_message": str(e),
                "blue_wins": getattr(self, 'blue_wins', 0),
                "red_wins": getattr(self, 'red_wins', 0),
                "roles": {str(k): v for k, v in getattr(self, 'roles', {}).items()}
            }
            try:
                self.log_public_event(error_end_event)
            except Exception as log_e:
                logger.error(f"记录错误结束事件时也发生错误: {log_e}")
            return {"error": str(e)}