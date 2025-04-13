# filepath: /home/eric/qhw/platform/game/baselines.py
"""
定义游戏的基础 AI (Baseline) 策略。
"""

BASELINE_CODE_A = """
def play_game():
    # 简单的策略：总是出布
    return 'paper'
"""

BASELINE_CODE_B = """
def play_game():
    # 随机策略
    choices = ['rock', 'paper', 'scissors']
    # 直接使用由裁判注入的 random 模块
    return random.choice(choices)
"""

# 如果需要，可以在这里添加更多的 Baseline 策略
# BASELINE_CODE_C = """..."""


def get_all_baseline_codes():
    """
    返回一个包含所有已定义 Baseline 代码的字典。
    键是描述性名称，值是代码内容的字符串。
    """
    return {
        "Baseline A (总是出布)": BASELINE_CODE_A,
        "Baseline B (随机)": BASELINE_CODE_B,
        # 在此添加其他 Baseline
        # "Baseline C": BASELINE_CODE_C,
    }
