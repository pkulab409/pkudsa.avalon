# 对战管理模块

import gradio as gr
import random
import time

# data_storage 导入保持不变
from data_storage import (
    get_user_codes,
    get_code_content,
    get_baseline_codes,
    save_duel_record,
    get_all_duels,
    update_user_points,
)

# 从新的 game 包导入所需函数
from game.referee import run_single_round
from game.visualizer import create_moves_visualization

# 对战队列 (保持不变)
duel_queue = []


def start_test_duel(user_state, user_code_name, opponent_code_name):
    username = user_state.get("username")
    if not username or not user_code_name or not opponent_code_name:
        # 返回两个值以匹配期望的输出 (文本, 图表)
        return "请先登录并选择代码", None

    user_code = get_code_content(username, user_code_name)
    baseline_codes = get_baseline_codes()
    opponent_code = baseline_codes.get(opponent_code_name, "")

    if not user_code or not opponent_code:
        return "获取代码内容失败", None

    gr.Info("正在进行对战...")

    # 调用裁判执行单回合对战
    user_move, opponent_move, result_code = run_single_round(
        user_code, opponent_code
    )  # result is now result_code

    # 记录对战过程
    duel_process = [
        f"您的代码 ({user_code_name}) 出招: {user_move}",
        f"对手代码 ({opponent_code_name}) 出招: {opponent_move}",
    ]

    # 根据裁判结果添加最终日志
    final_result_desc = ""  # 用于保存到 duel_data
    if result_code == "player1_win":
        duel_process.append(f"结果: 您的代码获胜！")
        final_result_desc = "胜利"
    elif result_code == "player2_win":
        duel_process.append(f"结果: 对手代码获胜！")
        final_result_desc = "失败"
    elif result_code == "draw":
        duel_process.append(f"结果: 平局！")
        final_result_desc = "平局"
    else:  # 'invalid' or other error cases from referee
        duel_process.append(f"结果: 无效对战 (裁判判定: {result_code})")
        # 可以根据 move1, move2 的错误标识添加更具体信息
        if (
            "error" in str(user_move)
            or "not_found" in str(user_move)
            or "invalid_move" in str(user_move)
        ):
            duel_process.append(f"原因: 您的代码执行出错或返回无效 ({user_move})")
        if (
            "error" in str(opponent_move)
            or "not_found" in str(opponent_move)
            or "invalid_move" in str(opponent_move)
        ):
            duel_process.append(f"原因: 对手代码执行出错或返回无效 ({opponent_move})")
        final_result_desc = "无效"

    # 保存对战记录
    duel_data = {
        "type": "test",
        "user1": username,
        "code1": user_code_name,
        "move1": user_move,
        "user2": "Baseline",
        "code2": opponent_code_name,
        "move2": opponent_move,
        "result": final_result_desc,  # 保存用户友好的结果
        "result_code": result_code,  # 保存内部结果代码
        "process": duel_process,
    }
    save_duel_record(duel_data)

    # 生成可视化图表
    plot_data = create_moves_visualization(user_move, opponent_move, result_code)

    # 返回对战过程文本和图表对象
    return "\n".join(duel_process), plot_data


def join_ladder_duel(user_state, user_code_name):
    username = user_state.get("username")
    if not username or not user_code_name:
        # 返回三个值以匹配期望的输出 (状态, 结果文本, 图表)
        return "错误", "错误：未登录或未选择代码", None

    if any(req["username"] == username for req in duel_queue):
        gr.Info("您已在队列中，请耐心等待...")
        return "正在匹配对手...", "您已在队列中", None

    duel_request = {
        "username": username,
        "code_name": user_code_name,
        "timestamp": time.time(),
    }
    duel_queue.append(duel_request)
    gr.Info("已加入队列，正在寻找对手...")

    if len(duel_queue) >= 2:
        player1_req = None
        player2_req = None
        for i in range(len(duel_queue)):
            for j in range(i + 1, len(duel_queue)):
                if duel_queue[i]["username"] != duel_queue[j]["username"]:
                    player2_req = duel_queue.pop(j)
                    player1_req = duel_queue.pop(i)
                    break
            if player1_req:
                break

        if player1_req and player2_req:
            gr.Info(f"匹配成功: {player1_req['username']} vs {player2_req['username']}")
            # conduct_ladder_duel 现在返回三个值
            return conduct_ladder_duel(player1_req, player2_req)

    # 如果没有立即匹配，返回等待状态和 None 图表
    return "正在匹配对手...", f"队列中 {len(duel_queue)} 人，等待匹配...", None


def conduct_ladder_duel(request1, request2):
    user1 = request1["username"]
    code1_name = request1["code_name"]
    user2 = request2["username"]
    code2_name = request2["code_name"]

    user1_code = get_code_content(user1, code1_name)
    user2_code = get_code_content(user2, code2_name)

    if not user1_code or not user2_code:
        # 返回三个值
        return "对战取消", "错误：获取一方或双方代码内容失败", None

    gr.Info(f"开始对战: {user1} vs {user2}")

    # 调用裁判执行单回合对战
    move1, move2, result_code = run_single_round(
        user1_code, user2_code
    )  # result is now result_code

    # 记录对战过程
    duel_process = [
        f"{user1} ({code1_name}) 出招: {move1}",
        f"{user2} ({code2_name}) 出招: {move2}",
    ]

    # 更新积分和最终结果描述
    points_change = 20
    final_result_desc = ""

    if result_code == "player1_win":
        duel_process.append(f"结果: {user1} 获胜！")
        update_user_points(user1, points_change)
        update_user_points(user2, -points_change)
        final_result_desc = (
            f"{user1} 胜利 (+{points_change}分), {user2} 失败 (-{points_change}分)"
        )
    elif result_code == "player2_win":
        duel_process.append(f"结果: {user2} 获胜！")
        update_user_points(user1, -points_change)
        update_user_points(user2, points_change)
        final_result_desc = (
            f"{user2} 胜利 (+{points_change}分), {user1} 失败 (-{points_change}分)"
        )
    elif result_code == "draw":
        duel_process.append(f"结果: 平局！")
        final_result_desc = "平局 (积分不变)"
    else:  # 'invalid' or other error cases
        duel_process.append(f"结果: 无效对战 (裁判判定: {result_code})")
        # 可以根据 move1, move2 的错误标识添加更具体信息
        if (
            "error" in str(move1)
            or "not_found" in str(move1)
            or "invalid_move" in str(move1)
        ):
            duel_process.append(f"原因: {user1} 代码执行出错或返回无效 ({move1})")
        if (
            "error" in str(move2)
            or "not_found" in str(move2)
            or "invalid_move" in str(move2)
        ):
            duel_process.append(f"原因: {user2} 代码执行出错或返回无效 ({move2})")
        final_result_desc = "无效对战 (积分不变)"

    # 保存对战记录
    duel_data = {
        "type": "ladder",
        "user1": user1,
        "code1": code1_name,
        "move1": move1,
        "user2": user2,
        "code2": code2_name,
        "move2": move2,
        "result": final_result_desc,  # 保存详细结果描述
        "result_code": result_code,  # 保存内部结果代码
        "process": duel_process,
    }
    save_duel_record(duel_data)

    # 生成可视化图表
    plot_data = create_moves_visualization(move1, move2, result_code)

    # 返回状态、详细结果文本和图表对象
    return "对战结束", "\n".join(duel_process), plot_data


def get_duel_records():
    all_duels = get_all_duels()
    # 确保排序，以便索引稳定
    all_duels.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return [
        f"对战 {i+1}: {duel.get('user1','?')} vs {duel.get('user2','?')} ({duel.get('result','?')})"
        for i, duel in enumerate(all_duels)
    ]


def get_duel_details(duel_index_str):
    # 添加对输入字符串格式的基础检查
    if (
        not duel_index_str
        or ":" not in duel_index_str
        or not duel_index_str.startswith("对战 ")
    ):
        # 返回两个值以匹配 update_details_and_visualization 的期望
        return "请选择一个有效的对战记录", None, None, None
    try:
        parts = duel_index_str.split(":")
        duel_header = parts[0]
        index_part = duel_header.replace("对战 ", "").strip()
        duel_index = int(index_part) - 1

        all_duels = get_all_duels()
        # 确保排序与 get_duel_records 一致
        all_duels.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        if 0 <= duel_index < len(all_duels):
            duel = all_duels[duel_index]
            details = [
                f"对战类型: {duel.get('type', '未知')}",
                f"玩家1: {duel.get('user1', '?')} ({duel.get('code1', '?')})",
                f"玩家2: {duel.get('user2', '?')} ({duel.get('code2', '?')})",
                f"玩家1出招: {duel.get('move1', '未记录')}",
                f"玩家2出招: {duel.get('move2', '未记录')}",
                f"结果: {duel.get('result', '未记录')}",
                f"时间戳: {duel.get('timestamp', '未知')}",
                "\n对战过程:",
            ]
            details.extend(duel.get("process", ["无详细过程"]))
            # 提取 move1, move2 和 result 用于可视化
            move1 = duel.get("move1")
            move2 = duel.get("move2")
            # 需要从原始结果（如 '玩家1胜利'）映射回内部标识符 ('player1_win')
            # 或者，更好的方式是在保存 duel 时就保存内部标识符
            # 假设 duel['result_code'] 保存了 'player1_win', 'player2_win', 'draw'
            # 如果没有，需要根据 duel['result'] 进行转换
            result_desc = duel.get("result", "")
            result_code = None
            if "玩家1胜利" in result_desc:
                result_code = "player1_win"
            elif "玩家2胜利" in result_desc:
                result_code = "player2_win"
            elif "平局" in result_desc:
                result_code = "draw"
            # 返回详细文本、出招1、出招2、结果代码
            return "\n".join(details), move1, move2, result_code
        else:
            return "选择的对战索引无效", None, None, None
    except ValueError:
        return "无效的对战索引格式", None, None, None
    except Exception as e:
        print(f"获取对战详情时出错: {e}")
        return f"获取对战详情时出错: {e}", None, None, None


# 修改辅助函数：处理新的返回值并传递 result_code
def update_details_and_visualization(duel_index_str):
    # get_duel_details 现在返回四个值
    details_text, move1, move2, result_code = get_duel_details(duel_index_str)
    plot_data = None

    # 只有在成功获取到 move1 和 move2 时才尝试可视化
    if move1 is not None and move2 is not None:
        # 调用 game.visualizer 中的函数，传递 result_code
        plot_data = create_moves_visualization(
            move1, move2, result_code
        )  # <--- 传递 result_code
    elif "错误" in details_text or "未找到" in details_text or "无法" in details_text:
        pass
    else:
        print(
            f"Could not get moves/result for visualization from duel record: {duel_index_str}"
        )

    return details_text, plot_data


# UI 创建函数 (create_duel_management_tab) 保持不变
# 它内部的 update_code_list 也不变
def create_duel_management_tab(user_state):
    with gr.Tab("⚔️ 对战中心"):
        with gr.Row():
            # --- 左侧：发起对战 ---
            with gr.Column(scale=1):
                gr.Markdown("### 🚀 发起对战")
                # --- 测试对战 ---
                with gr.Group():
                    gr.Markdown("#### 🧪 测试对战")

                    def update_code_list(current_user_state):
                        username = current_user_state.get("username")
                        if not username:
                            return gr.update(choices=[])
                        user_codes_dict = get_user_codes(username)
                        return gr.update(choices=list(user_codes_dict.keys()))

                    test_user_code = gr.Dropdown(
                        choices=[], label="选择您的代码", interactive=True
                    )
                    refresh_test_code_btn = gr.Button("🔄 刷新我的代码 (测试)")
                    test_opponent_code = gr.Dropdown(
                        choices=list(get_baseline_codes().keys()),
                        label="选择 Baseline 对手",
                        interactive=True,
                    )
                    test_duel_btn = gr.Button("⚡ 发起测试对战")
                    test_duel_result = gr.Textbox(
                        label="测试对战结果", lines=5, interactive=False
                    )
                    # 添加测试对战的可视化组件
                    test_duel_plot = gr.Plot(label="测试对战可视化")

                    refresh_test_code_btn.click(
                        fn=update_code_list, inputs=[user_state], outputs=test_user_code
                    )
                    # 更新 test_duel_btn 的 outputs
                    test_duel_btn.click(
                        fn=start_test_duel,
                        inputs=[user_state, test_user_code, test_opponent_code],
                        outputs=[
                            test_duel_result,
                            test_duel_plot,
                        ],  # 输出到文本框和图表
                    )
                # --- 天梯对战 ---
                with gr.Group():
                    gr.Markdown("#### 🏆 天梯对战")
                    ladder_user_code = gr.Dropdown(
                        choices=[], label="选择您的代码", interactive=True
                    )
                    refresh_ladder_code_btn = gr.Button("🔄 刷新我的代码 (天梯)")
                    join_ladder_btn = gr.Button("⏳ 加入天梯对战队列")
                    ladder_status = gr.Textbox(
                        label="匹配状态", value="未加入队列", interactive=False
                    )
                    ladder_duel_result = gr.Textbox(
                        label="天梯对战结果", lines=5, interactive=False
                    )
                    # 添加天梯对战的可视化组件
                    ladder_duel_plot = gr.Plot(label="天梯对战可视化")

                    refresh_ladder_code_btn.click(
                        fn=update_code_list,
                        inputs=[user_state],
                        outputs=ladder_user_code,
                    )
                    # 更新 join_ladder_btn 的 outputs
                    join_ladder_btn.click(
                        fn=join_ladder_duel,
                        inputs=[user_state, ladder_user_code],
                        outputs=[
                            ladder_status,
                            ladder_duel_result,
                            ladder_duel_plot,
                        ],  # 输出到状态、结果文本和图表
                    )
            # --- 右侧：查看对战记录与可视化 ---
            with gr.Column(scale=1):
                gr.Markdown("### 📊 对战记录与可视化")
                with gr.Group():
                    duel_records = gr.Dropdown(
                        choices=get_duel_records(),
                        label="选择要查看的对战记录",
                        interactive=True,
                    )
                    refresh_records_btn = gr.Button("🔄 刷新对战记录列表")
                    duel_details = gr.Textbox(
                        label="对战过程详情", lines=8, interactive=False
                    )
                    duel_visualization = gr.Plot(label="对战可视化图")
                    refresh_records_btn.click(
                        fn=lambda: gr.update(choices=get_duel_records()),
                        inputs=[],
                        outputs=duel_records,
                    )
                    duel_records.change(
                        fn=update_details_and_visualization,
                        inputs=duel_records,
                        outputs=[duel_details, duel_visualization],
                    )
