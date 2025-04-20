"""
负责生成阿瓦隆游戏相关的可视化图表。
"""

import matplotlib.pyplot as plt
import matplotlib
import matplotlib.patches as mpatches
import textwrap
import numpy as np
from matplotlib.gridspec import GridSpec

matplotlib.use("Agg")  # 确保无GUI环境可用


def create_game_visualization(game_data, result=None):
    """
    原始函数保持不变，用于兼容性
    """
    return create_moves_visualization(game_data)


def create_moves_visualization(game_data):
    """
    创建阿瓦隆游戏对战可视化图表，模仿聊天对话和游戏进程

    Args:
        game_data (dict): 包含游戏数据的字典

    Returns:
        matplotlib.figure.Figure: Matplotlib图表对象
    """
    # 创建一个大尺寸的图像
    fig = plt.figure(figsize=(12, 10), dpi=100)

    # 使用GridSpec创建更灵活的布局
    gs = GridSpec(3, 2, height_ratios=[1, 3, 2], width_ratios=[3, 1])

    # 设置整体背景颜色
    fig.patch.set_facecolor("#f5f5f7")

    # =====顶部区域：游戏标题和基本信息=====
    ax_header = fig.add_subplot(gs[0, :])
    ax_header.set_facecolor("#f5f5f7")
    ax_header.axis("off")
    ax_header.text(
        0.5,
        0.5,
        "图灵阿瓦隆对战记录",
        fontsize=24,
        fontweight="bold",
        ha="center",
        va="center",
    )

    # 如果有最终结果，显示胜利方
    if "final_result" in game_data:
        result_text = (
            "蓝方胜利!" if game_data["final_result"] == "blue_win" else "红方胜利!"
        )
        result_color = "blue" if game_data["final_result"] == "blue_win" else "red"
        ax_header.text(
            0.5,
            0.1,
            result_text,
            fontsize=18,
            color=result_color,
            ha="center",
            va="center",
            bbox=dict(facecolor="white", alpha=0.8, boxstyle="round,pad=0.5"),
        )

    # =====中间区域：任务轮次和对话记录=====
    ax_main = fig.add_subplot(gs[1, 0])
    ax_main.set_facecolor("#f5f5f7")
    ax_main.axis("off")

    # 显示任务轮次
    if "mission_rounds" in game_data:
        rounds = game_data["mission_rounds"]
        max_rounds = len(rounds)

        # 绘制任务记录
        for i, round_data in enumerate(rounds):
            y_pos = 0.9 - i * 0.15  # 从上到下排列

            # 轮次标题
            ax_main.text(
                0.05,
                y_pos,
                f"任务 {round_data['round']}",
                fontsize=14,
                fontweight="bold",
            )

            # 队长信息
            ax_main.text(
                0.05,
                y_pos - 0.03,
                f"队长: 玩家{round_data['leader']} | 提议: {round_data['proposed_team']}",
                fontsize=11,
            )

            # 投票结果
            vote_result = round_data.get("vote_results", {})
            vote_text = f"投票: {vote_result.get('approve', 0)}赞成 vs {vote_result.get('reject', 0)}反对"
            ax_main.text(0.05, y_pos - 0.06, vote_text, fontsize=11)

            # 任务结果
            result = round_data.get("mission_result", "unknown")
            result_text = "成功" if result == "success" else "失败"
            result_color = "green" if result == "success" else "red"

            # 创建圆形指示器
            circle = plt.Circle((0.9, y_pos - 0.03), 0.02, color=result_color)
            ax_main.add_patch(circle)
            ax_main.text(
                0.9,
                y_pos - 0.06,
                result_text,
                fontsize=11,
                ha="center",
                color=result_color,
            )

            # 如果有发言记录，添加一个样例
            if "speeches" in round_data and round_data["speeches"]:
                sample_speech = round_data["speeches"][0]
                speaker = sample_speech["player"]
                content = sample_speech["content"]

                # 截断长消息
                if len(content) > 50:
                    content = content[:47] + "..."

                ax_main.text(
                    0.05,
                    y_pos - 0.09,
                    f'玩家{speaker}: "{content}"',
                    fontsize=10,
                    style="italic",
                    color="#555",
                )

    # =====右侧区域：角色分配=====
    ax_roles = fig.add_subplot(gs[1, 1])
    ax_roles.set_facecolor("#f5f5f7")
    ax_roles.axis("off")

    if "roles" in game_data:
        ax_roles.text(
            0.5, 0.95, "角色分配", fontsize=14, fontweight="bold", ha="center"
        )

        roles = game_data["roles"]

        # 定义角色颜色
        role_colors = {
            "Merlin": "#4169E1",  # 皇家蓝
            "Percival": "#6495ED",  # 矢车菊蓝
            "Knight": "#87CEEB",  # 天蓝色
            "Assassin": "#B22222",  # 深红色
            "Morgana": "#DC143C",  # 猩红色
            "Oberon": "#CD5C5C",  # 印度红
        }

        y_spacing = 0.85
        for player_id, role in roles.items():
            color = role_colors.get(role, "grey")
            ax_roles.text(0.5, y_spacing, f"玩家 {player_id}", fontsize=12, ha="center")
            ax_roles.text(
                0.5,
                y_spacing - 0.05,
                role,
                fontsize=12,
                color=color,
                fontweight="bold",
                ha="center",
            )

            # 添加简单的背景
            rect = plt.Rectangle(
                (0.1, y_spacing - 0.08),
                0.8,
                0.1,
                fill=True,
                alpha=0.1,
                color=color,
                transform=ax_roles.transAxes,
            )
            ax_roles.add_patch(rect)

            y_spacing -= 0.13

    # =====底部区域：对话记录=====
    ax_chat = fig.add_subplot(gs[2, :])
    ax_chat.set_facecolor("#f0f2f6")
    ax_chat.axis("off")

    # 找到包含发言的回合
    speech_samples = []
    if "mission_rounds" in game_data:
        for round_data in game_data["mission_rounds"]:
            if "speeches" in round_data and round_data["speeches"]:
                # 提取前3个发言作为样本
                for speech in round_data["speeches"][:3]:
                    speech_samples.append((speech["player"], speech["content"]))
                break

    # 如果没有找到发言，使用默认样本
    if not speech_samples:
        speech_samples = [
            (1, "我认为2号和7号可能是邪恶方，他们的行为很可疑"),
            (2, "我是骑士，我可以保证我是好人，请信任我"),
            (3, "我们应该注意观察每个人的投票模式"),
        ]

    # 显示对话记录
    ax_chat.text(0.5, 0.97, "对话记录示例", fontsize=14, fontweight="bold", ha="center")

    # 绘制类似聊天气泡的对话
    max_width_chars = 40
    y_pos = 0.85
    alternating_x = [0.1, 0.9]  # 左右交替，使对话看起来更自然
    bubble_colors = ["#DCF8C6", "#FFFFFF"]  # 绿色和白色交替

    for i, (speaker, message) in enumerate(speech_samples):
        x_pos = alternating_x[i % 2]
        ha = "left" if i % 2 == 0 else "right"
        bubble_color = bubble_colors[i % 2]

        # 清理消息格式
        message = message.strip()

        # 自动换行处理
        wrapped_message = textwrap.fill(
            f"玩家{speaker}: {message}", width=max_width_chars
        )
        lines = wrapped_message.count("\n") + 1

        # 创建气泡背景并添加文本
        text_box = ax_chat.text(
            x_pos,
            y_pos,
            wrapped_message,
            ha=ha,
            va="top",
            wrap=True,
            fontsize=11,
            bbox=dict(
                boxstyle="round,pad=0.6",
                facecolor=bubble_color,
                alpha=0.9,
                edgecolor="#DDDDDD",
            ),
        )

        # 根据文本内容移动Y位置
        y_pos -= 0.05 + (lines * 0.03)

    # 调整布局
    plt.tight_layout(pad=2.0)
    return fig


def _get_result_description(result_code):
    """
    根据结果代码获取描述文本
    """
    if result_code == "player1_win":
        return "玩家1获胜"
    elif result_code == "player2_win":
        return "玩家2获胜"
    elif result_code == "draw":
        return "平局"
    elif result_code == "blue_win":
        return "蓝方胜利"
    elif result_code == "red_win":
        return "红方胜利"
    else:
        return f"未知结果 ({result_code})"
