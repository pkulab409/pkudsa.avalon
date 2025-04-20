"""
负责执行玩家代码和单回合对战逻辑。
"""

import traceback
import builtins  # <--- 导入 builtins 模块
import random  # <--- 移到这里，确保 random 在 try 块外导入一次即可
from .rules import determine_winner  # 使用相对导入


def execute_player_code(code_content):
    """
    执行玩家代码并获取其回合决策。
    警告：当前的 exec 实现存在安全风险，生产环境应使用沙箱。
    Returns: move (str) or error identifier (str)
    """
    try:
        # 准备执行环境 (可以考虑进一步限制)
        # 使用导入的 builtins 模块构建安全的内建函数字典
        safe_builtins_dict = {}
        allowed_builtins_names = [
            "print",
            "int",
            "float",
            "str",
            "list",
            "dict",
            "tuple",
            "len",
            "range",
            "abs",
            "max",
            "min",
            "sum",
            "True",
            "False",
            "None",
            "round",
            # 可以根据需要添加其他安全的内建函数/类型
        ]
        for name in allowed_builtins_names:
            try:
                # 从导入的 builtins 模块获取属性
                safe_builtins_dict[name] = getattr(builtins, name)
            except AttributeError:
                # 处理可能不存在的属性（虽然列表中的应该都存在）
                print(
                    f"Warning: Builtin '{name}' not found in standard builtins module."
                )

        # 将构建好的安全内建字典传递给 exec
        exec_globals = {"__builtins__": safe_builtins_dict, "random": random}

        # 执行代码
        exec(code_content, exec_globals)

        # 调用 play_game 函数
        if "play_game" in exec_globals and callable(exec_globals["play_game"]):
            move = exec_globals["play_game"]()
            allowed_moves = ["rock", "paper", "scissors"]  # 示例允许的出招
            if isinstance(move, str) and move.lower() in allowed_moves:
                return move.lower()
            else:
                print(f"Player code returned invalid move: {move}")
                return "invalid_move_type_or_value"
        else:
            return "play_game_not_found_or_not_callable"
    except Exception as e:
        print(f"Error executing player code: {e}")
        traceback.print_exc()  # <--- 这行会打印详细错误信息
        return "execution_error"


def run_single_round(code_content1, code_content2):
    """
    执行单回合对战。

    Args:
        code_content1 (str): 玩家1的代码内容。
        code_content2 (str): 玩家2的代码内容。

    Returns:
        tuple: (move1: str, move2: str, result: str)
               result 是 'player1_win', 'player2_win', 'draw', 'invalid'
    """
    move1 = execute_player_code(code_content1)
    move2 = execute_player_code(code_content2)

    # 检查代码执行结果
    error_flags = ["error", "not_found", "invalid_move"]
    p1_failed = any(flag in str(move1) for flag in error_flags)
    p2_failed = any(flag in str(move2) for flag in error_flags)

    if p1_failed and p2_failed:
        result = "draw"  # 双方都失败，判平局
    elif p1_failed:
        result = "player2_win"
    elif p2_failed:
        result = "player1_win"
    else:
        # 双方代码都成功执行，根据游戏规则判断
        result = determine_winner(move1, move2)  # 调用 game.rules 中的函数

    return move1, move2, result
