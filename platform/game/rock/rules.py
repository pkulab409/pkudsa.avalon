"""
定义游戏规则。
"""


def determine_winner(move1, move2):
    """
    根据双方在一回合中的出招判断胜负 (石头剪刀布示例)。
    Args:
        move1 (str): 玩家1的出招。
        move2 (str): 玩家2的出招。
    Returns:
        str: 'player1_win', 'player2_win', 'draw', 'invalid'
    """
    # 将输入标准化为小写，如果它们是字符串的话
    m1_lower = str(move1).lower() if move1 else None
    m2_lower = str(move2).lower() if move2 else None

    # 示例：石头剪刀布规则
    rules = {
        "rock": {"rock": "draw", "paper": "player2_win", "scissors": "player1_win"},
        "paper": {"rock": "player1_win", "paper": "draw", "scissors": "player2_win"},
        "scissors": {"rock": "player2_win", "paper": "player1_win", "scissors": "draw"},
    }

    if m1_lower not in rules or m2_lower not in rules.get(m1_lower, {}):
        # 处理无效输入或非预期输入
        print(f"Invalid moves detected: Player 1: {move1}, Player 2: {move2}")
        return "invalid"

    # 使用标准化后的输入进行判断
    return rules[m1_lower][m2_lower]


# 可以添加更多游戏规则相关的函数
