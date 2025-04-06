import gradio as gr
import random
import time
from data_storage import (
    get_user_codes,
    get_code_content,
    get_baseline_codes,
    save_duel_record,
    get_all_duels,
    update_user_points,
)

# 对战队列
duel_queue = []


# 简化的对战规则（石头剪刀布）
def determine_winner(user_move, opponent_move):
    moves = {
        "rock": {"rock": "draw", "paper": "lose", "scissors": "win"},
        "paper": {"rock": "win", "paper": "draw", "scissors": "lose"},
        "scissors": {"rock": "lose", "paper": "win", "scissors": "draw"},
    }

    if user_move not in moves or opponent_move not in moves[user_move]:
        return "invalid"

    return moves[user_move][opponent_move]


def execute_code(code_content):
    try:
        # 准备执行环境
        exec_globals = {"__builtins__": __builtins__}

        # 执行代码
        exec(code_content, exec_globals)

        # 如果代码中有play_game函数，调用它
        if "play_game" in exec_globals:
            return exec_globals["play_game"]()
        else:
            return "代码中未找到play_game函数"
    except Exception as e:
        return f"执行错误: {str(e)}"


def start_test_duel(user_state, user_code_name, opponent_code_name):
    if not user_state["username"] or not user_code_name or not opponent_code_name:
        return "请先登录并选择代码"

    # 获取用户代码和对手代码
    user_code = get_code_content(user_state["username"], user_code_name)
    baseline_codes = get_baseline_codes()
    opponent_code = baseline_codes.get(opponent_code_name, "")

    if not user_code or not opponent_code:
        return "获取代码内容失败"

    # 执行代码
    user_move = execute_code(user_code)
    opponent_move = execute_code(opponent_code)

    # 记录对战过程
    duel_process = [
        f"您的代码 ({user_code_name}) 出招: {user_move}",
        f"对手代码 ({opponent_code_name}) 出招: {opponent_move}",
    ]

    # 判断胜负
    result = determine_winner(user_move, opponent_move)

    if result == "win":
        duel_process.append(f"结果: 您的代码获胜！")
        final_result = "胜利"
    elif result == "lose":
        duel_process.append(f"结果: 对手代码获胜！")
        final_result = "失败"
    elif result == "draw":
        duel_process.append(f"结果: 平局！")
        final_result = "平局"
    else:
        duel_process.append(
            f"结果: 无效对战，请确保代码返回'rock'、'paper'或'scissors'"
        )
        final_result = "无效"

    # 保存对战记录
    duel_data = {
        "type": "test",
        "user1": user_state["username"],
        "code1": user_code_name,
        "move1": user_move,
        "user2": "Baseline",
        "code2": opponent_code_name,
        "move2": opponent_move,
        "result": final_result,
        "process": duel_process,
    }
    save_duel_record(duel_data)

    return "\n".join(duel_process)


def join_ladder_duel(user_state, user_code_name):
    if not user_state["username"] or not user_code_name:
        return "正在匹配...", "请先登录并选择代码"

    # 创建对战请求
    duel_request = {
        "username": user_state["username"],
        "code_name": user_code_name,
        "timestamp": time.time(),
    }

    # 加入对战队列
    duel_queue.append(duel_request)

    # 检查是否有足够的请求进行匹配
    if len(duel_queue) >= 2:
        # 取出两个请求
        opponent_request = None

        # 找一个不是当前用户的对手
        for i, request in enumerate(duel_queue):
            if request["username"] != user_state["username"]:
                opponent_request = request
                duel_queue.pop(i)
                break

        # 如果找到对手，进行对战
        if opponent_request:
            # 从队列中移除当前用户的请求
            for i, request in enumerate(duel_queue):
                if request["username"] == user_state["username"]:
                    duel_queue.pop(i)
                    break

            # 进行对战
            return conduct_ladder_duel(duel_request, opponent_request)

    # 如果没有足够的请求或没有合适的对手，继续等待
    return "正在匹配对手...", "您已加入对战队列，正在等待匹配..."


def conduct_ladder_duel(request1, request2):
    user1 = request1["username"]
    code1 = request1["code_name"]
    user2 = request2["username"]
    code2 = request2["code_name"]

    # 获取用户代码
    user1_code = get_code_content(user1, code1)
    user2_code = get_code_content(user2, code2)

    if not user1_code or not user2_code:
        return "对战取消", "获取代码内容失败"

    # 执行代码
    user1_move = execute_code(user1_code)
    user2_move = execute_code(user2_code)

    # 记录对战过程
    duel_process = [
        f"{user1} ({code1}) 出招: {user1_move}",
        f"{user2} ({code2}) 出招: {user2_move}",
    ]

    # 判断胜负
    result = determine_winner(user1_move, user2_move)

    # 设置积分变化
    points_change = 20  # 基础积分变化

    if result == "win":
        duel_process.append(f"结果: {user1} 获胜！")
        update_user_points(user1, points_change)
        update_user_points(user2, -points_change)
        final_result = (
            f"{user1} 胜利 (+{points_change}分), {user2} 失败 (-{points_change}分)"
        )
    elif result == "lose":
        duel_process.append(f"结果: {user2} 获胜！")
        update_user_points(user1, -points_change)
        update_user_points(user2, points_change)
        final_result = (
            f"{user2} 胜利 (+{points_change}分), {user1} 失败 (-{points_change}分)"
        )
    elif result == "draw":
        duel_process.append(f"结果: 平局！")
        final_result = "平局 (积分不变)"
    else:
        duel_process.append(
            f"结果: 无效对战，请确保代码返回'rock'、'paper'或'scissors'"
        )
        final_result = "无效对战 (积分不变)"

    # 保存对战记录
    duel_data = {
        "type": "ladder",
        "user1": user1,
        "code1": code1,
        "move1": user1_move,
        "user2": user2,
        "code2": code2,
        "move2": user2_move,
        "result": final_result,
        "process": duel_process,
    }
    save_duel_record(duel_data)

    return "对战结束", "\n".join(duel_process)


def get_duel_records():
    all_duels = get_all_duels()
    return [
        f"对战 {i+1}: {duel['user1']} vs {duel['user2']} ({duel['result']})"
        for i, duel in enumerate(all_duels)
    ]


def get_duel_details(duel_index_str):
    try:
        duel_index = int(duel_index_str.split(":")[0].split(" ")[1]) - 1
        all_duels = get_all_duels()
        if 0 <= duel_index < len(all_duels):
            duel = all_duels[duel_index]
            return "\n".join(duel["process"])
        return "未找到对战记录"
    except:
        return "获取对战详情失败"


def create_duel_management_tab(user_state):
    with gr.Tab("对战管理"):
        with gr.Row():
            with gr.Column():
                gr.Markdown("### 发起测试")

                # 用于更新代码列表的函数
                def update_code_list(user_state):
                    return gr.update(choices=load_user_codes(user_state))

                test_user_code = gr.Dropdown(
                    choices=[], label="选择您的代码 (测试对战)"
                )
                refresh_test_code_btn = gr.Button("刷新代码列表")
                test_opponent_code = gr.Dropdown(
                    choices=list(get_baseline_codes().keys()),
                    label="选择对手代码 (测试对战)",
                )
                test_duel_btn = gr.Button("发起测试对战")
                test_duel_result = gr.Textbox(label="测试对战结果", lines=5)

                # 刷新代码列表
                refresh_test_code_btn.click(
                    fn=update_code_list, inputs=[user_state], outputs=test_user_code
                )

                test_duel_btn.click(
                    fn=start_test_duel,
                    inputs=[user_state, test_user_code, test_opponent_code],
                    outputs=test_duel_result,
                )

        with gr.Row():
            with gr.Column():
                gr.Markdown("### 发起对战")
                ladder_user_code = gr.Dropdown(
                    choices=[], label="选择您的代码 (天梯对战)"
                )
                refresh_ladder_code_btn = gr.Button("刷新代码列表")
                join_ladder_btn = gr.Button("加入天梯对战队列")
                ladder_status = gr.Label(label="对战状态", value="未开始")
                ladder_duel_result = gr.Textbox(label="天梯对战结果", lines=5)

                # 刷新代码列表
                refresh_ladder_code_btn.click(
                    fn=update_code_list, inputs=[user_state], outputs=ladder_user_code
                )

                join_ladder_btn.click(
                    fn=join_ladder_duel,
                    inputs=[user_state, ladder_user_code],
                    outputs=[ladder_status, ladder_duel_result],
                )

        with gr.Row():
            with gr.Column():
                gr.Markdown("### 对战可视化")
                duel_records = gr.Dropdown(
                    choices=get_duel_records(), label="选择要查看的对战记录"
                )
                refresh_records_btn = gr.Button("刷新对战记录")
                refresh_records_btn.click(
                    fn=get_duel_records, inputs=[], outputs=duel_records
                )
                duel_details = gr.Textbox(label="对战过程 (文本模拟)", lines=10)

                duel_records.change(
                    fn=get_duel_details, inputs=duel_records, outputs=duel_details
                )


# 用于代码管理模块调用
def load_user_codes(user_state):
    if not user_state["username"]:
        return []

    user_codes = get_user_codes(user_state["username"])
    return list(user_codes.keys())
