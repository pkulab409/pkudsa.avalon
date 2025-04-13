import gradio as gr
import logging
from game.visualizer import create_moves_visualization


def create_duel_tab():
    """创建对战中心Tab界面"""
    from services.duel_service import (
        start_test_duel,
        join_ladder_duel,
        get_duel_details,
        get_duel_records,
        get_baseline_codes,
    )
    from services.code_service import get_user_codes

    def update_code_list(request: gr.Request):
        """更新用户代码列表"""
        username = request.session.get("username")
        if not username:
            return gr.update(choices=[])
        user_codes_dict = get_user_codes(username)
        return gr.update(choices=list(user_codes_dict.keys()))

    def handle_test_duel(user_code, opponent_code, request: gr.Request):
        """处理测试对战请求"""
        username = request.session.get("username")
        if not username:
            gr.Warning("请先登录")
            return "请先登录", None

        # 执行对战
        duel_process, result_code = start_test_duel(username, user_code, opponent_code)

        # 生成可视化图表
        if result_code and result_code != "invalid":
            from services.code_service import get_code_content

            user_code_content = get_code_content(username, user_code)
            baseline_codes = get_baseline_codes()
            opponent_code_content = baseline_codes.get(opponent_code, "")

            # 裁判执行对战，获取招式
            from game.referee import run_single_round

            move1, move2, _ = run_single_round(user_code_content, opponent_code_content)

            # 生成图表
            plot_data = create_moves_visualization(move1, move2, result_code)
            return duel_process, plot_data

        return duel_process, None

    def handle_ladder_duel(user_code, request: gr.Request):
        """处理天梯对战请求"""
        username = request.session.get("username")
        if not username:
            gr.Warning("请先登录")
            return "错误", "请先登录", None

        # 加入对战队列
        status, message, result_code = join_ladder_duel(username, user_code)

        # 如果有对战结果，生成可视化图表
        plot_data = None
        if result_code and result_code != "invalid":
            # 假设 message 包含双方的出招信息，从中提取
            import re

            move1_match = re.search(r"出招: ([a-zA-Z]+)", message.split("\n")[0])
            move2_match = re.search(r"出招: ([a-zA-Z]+)", message.split("\n")[1])

            if move1_match and move2_match:
                move1 = move1_match.group(1)
                move2 = move2_match.group(1)
                plot_data = create_moves_visualization(move1, move2, result_code)

        return status, message, plot_data

    def update_details_and_visualization(duel_index_str):
        """更新对战详情和可视化"""
        details_text, move1, move2, result_code = get_duel_details(duel_index_str)

        # 只有在成功获取到移动时才尝试创建可视化
        plot_data = None
        if move1 is not None and move2 is not None:
            plot_data = create_moves_visualization(move1, move2, result_code)

        return details_text, plot_data

    with gr.Tab("⚔️ 对战中心"):
        with gr.Row():
            # 左侧：发起对战
            with gr.Column(scale=1):
                gr.Markdown("### 🚀 发起对战")

                # 测试对战
                with gr.Group():
                    gr.Markdown("#### 🧪 测试对战")

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
                    test_duel_plot = gr.Plot(label="测试对战可视化")

                # 天梯对战
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
                    ladder_duel_plot = gr.Plot(label="天梯对战可视化")

            # 右侧：查看对战记录
            with gr.Column(scale=1):
                gr.Markdown("### 📊 对战记录与可视化")

                with gr.Group():
                    duel_records = gr.Dropdown(
                        choices=[], label="选择要查看的对战记录", interactive=True
                    )
                    refresh_records_btn = gr.Button("🔄 刷新对战记录列表")

                    duel_details = gr.Textbox(
                        label="对战过程详情", lines=8, interactive=False
                    )
                    duel_visualization = gr.Plot(label="对战可视化图")

        # 事件处理
        refresh_test_code_btn.click(
            fn=update_code_list, inputs=[], outputs=[test_user_code]
        )

        refresh_ladder_code_btn.click(
            fn=update_code_list, inputs=[], outputs=[ladder_user_code]
        )

        test_duel_btn.click(
            fn=handle_test_duel,
            inputs=[test_user_code, test_opponent_code],
            outputs=[test_duel_result, test_duel_plot],
        )

        join_ladder_btn.click(
            fn=handle_ladder_duel,
            inputs=[ladder_user_code],
            outputs=[ladder_status, ladder_duel_result, ladder_duel_plot],
        )

        refresh_records_btn.click(
            fn=lambda: gr.update(choices=get_duel_records()),
            inputs=[],
            outputs=[duel_records],
        )

        duel_records.change(
            fn=update_details_and_visualization,
            inputs=[duel_records],
            outputs=[duel_details, duel_visualization],
        )

    return {
        "refresh_test_code_btn": refresh_test_code_btn,
        "test_user_code": test_user_code,
        "refresh_ladder_code_btn": refresh_ladder_code_btn,
        "ladder_user_code": ladder_user_code,
    }
