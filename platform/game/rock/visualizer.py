"""
负责生成对战相关的可视化图表。
"""

import matplotlib.pyplot as plt
import matplotlib

matplotlib.use("Agg")  # 确保设置后端


def create_moves_visualization(move1, move2, result=None):
    """
    根据双方的出招和结果生成对战可视化图表 (仅使用 ASCII 字符)。

    Args:
        move1 (str): 玩家1的出招。
        move2 (str): 玩家2的出招。
        result (str, optional): 对战结果 ('player1_win', 'player2_win', 'draw'). Defaults to None.

    Returns:
        matplotlib.figure.Figure or None: Matplotlib 图表对象，如果无法生成则返回 None。
    """
    # 使用纯文本代替 Emoji
    moves_text = {"rock": "ROCK", "paper": "PAPER", "scissors": "SCISSORS"}
    # 处理无效或非预期的出招显示
    text1 = moves_text.get(str(move1).lower(), "?") if move1 else "?"
    text2 = moves_text.get(str(move2).lower(), "?") if move2 else "?"

    # 根据 result 确定显示文本 (保持英文)
    result_text = ""
    if result == "player1_win":
        result_text = "Player 1 Wins!"
    elif result == "player2_win":
        result_text = "Player 2 Wins!"
    elif result == "draw":
        result_text = "Draw!"
    # 可以添加对其他 result 值的处理，例如错误情况

    fig = None
    try:
        fig, ax = plt.subplots(figsize=(6, 3))
        fig.patch.set_facecolor("#f0f2f6")
        ax.set_facecolor("#f0f2f6")
        # 使用英文标题
        ax.set_title("Duel Moves", fontsize=14, fontweight="bold")
        ax.axis("off")

        # 使用文本代替 Emoji
        ax.text(0.25, 0.5, text1, fontsize=20, ha="center", va="center")  # 调整字体大小
        ax.text(
            0.5,
            0.5,
            "VS",
            fontsize=20,
            ha="center",
            va="center",
            bbox=dict(facecolor="#e6e6e6", edgecolor="gray", boxstyle="round,pad=0.3"),
        )
        ax.text(0.75, 0.5, text2, fontsize=20, ha="center", va="center")  # 调整字体大小

        # 使用英文标签
        ax.text(0.25, 0.1, "Player 1", fontsize=10, ha="center", va="center")
        ax.text(0.75, 0.1, "Player 2", fontsize=10, ha="center", va="center")

        # 在图表顶部添加结果文本 (保持英文)
        if result_text:
            ax.text(
                0.5,
                0.85,
                result_text,
                fontsize=12,
                ha="center",
                va="center",
                color="blue",
                fontweight="bold",
            )

        return fig
    except Exception as e:
        print(f"Error creating visualization: {e}")
        if fig is not None and plt.fignum_exists(fig.number):
            plt.close(fig)
        return None


# ... 其他可视化函数 ...
