import gradio as gr
import logging


def create_code_tab():
    """创建代码管理Tab界面"""
    from services.code_service import (
        get_user_codes,
        save_code,
        get_code_content,
        execute_code_safely,
        get_code_templates,
    )

    def load_user_codes(request: gr.Request):
        """加载当前登录用户的代码列表"""
        username = request.session.get("username")
        if not username:
            return []
        user_codes = get_user_codes(username)
        return list(user_codes.keys())

    def save_new_code(code_name, code_content, request: gr.Request):
        """保存新代码，并返回更新给UI组件"""
        username = request.session.get("username")
        if not username:
            gr.Warning("请先登录")
            return gr.update(), gr.update(), gr.update(choices=[])

        if not code_name or not code_content:
            gr.Warning("代码名称和内容不能为空")
            return gr.update(), gr.update(), gr.update(choices=load_user_codes(request))

        user_codes = get_user_codes(username)
        if code_name in user_codes:
            gr.Warning("代码名称已存在，请选择该代码进行编辑")
            return gr.update(), gr.update(), gr.update(choices=load_user_codes(request))

        success, message = save_code(username, code_name, code_content)
        if success:
            gr.Info(message)
            # 清空输入框，更新列表
            return (
                gr.update(value=""),
                gr.update(value=""),
                gr.update(choices=load_user_codes(request)),
            )
        else:
            gr.Error(message)
            return gr.update(), gr.update(), gr.update(choices=load_user_codes(request))

    def load_code_content(code_name, request: gr.Request):
        """加载代码内容到编辑器"""
        username = request.session.get("username")
        if not username or not code_name:
            return ""
        return get_code_content(username, code_name)

    def save_edited_code(code_name, code_content, request: gr.Request):
        """保存编辑后的代码"""
        username = request.session.get("username")
        if not username:
            gr.Warning("请先登录")
            return

        if not code_name:
            gr.Warning("请先从下拉列表中选择要编辑的代码")
            return

        if not code_content:
            gr.Warning("代码内容不能为空")
            return

        success, message = save_code(username, code_name, code_content)
        if success:
            gr.Info(message)
        else:
            gr.Error(message)

    def debug_code(code_name, input_params, request: gr.Request):
        """执行代码调试"""
        username = request.session.get("username")
        if not username:
            gr.Warning("请先登录")
            return "请先登录。"

        if not code_name:
            gr.Warning("请先从下拉列表中选择要调试的代码")
            return "请选择代码。"

        code_content = get_code_content(username, code_name)
        if not code_content:
            gr.Error("获取代码内容失败")
            return "无法加载所选代码。"

        stdout, stderr, result = execute_code_safely(code_content, input_params)
        result_output = f"--- 标准输出 ---\n{stdout}\n\n--- 错误输出 ---\n{stderr}"
        if result is not None:
            result_output += f"\n\n--- 返回值 ---\n{result}"
        return result_output

    def load_template(template_name):
        """加载预定义的代码模板"""
        templates = get_code_templates()
        return templates.get(template_name, "# 无法加载所选模板")

    with gr.Tab("💻 代码管理"):
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### ✨ 新建代码")
                new_code_name = gr.Textbox(
                    label="新代码名称", placeholder="例如: my_strategy_v1"
                )

                # 添加模板选择
                template_dropdown = gr.Dropdown(
                    choices=list(get_code_templates().keys()),
                    label="选择模板",
                    value=None,
                )

                new_code_content = gr.Code(
                    language="python",
                    lines=15,
                    label="新代码内容",
                    value="# 在此输入您的 Python 代码...\n\ndef play_game():\n    # 返回 'rock', 'paper', 或 'scissors'\n    return 'rock'\n",
                )
                save_new_code_btn = gr.Button("💾 保存新代码")

            with gr.Column(scale=2):
                gr.Markdown("### ✏️ 编辑 / 🐞 调试")
                with gr.Row():
                    code_selector = gr.Dropdown(
                        choices=[], label="选择代码进行操作", interactive=True, scale=4
                    )
                    refresh_list_btn = gr.Button("🔄 刷新列表", scale=1)
                code_editor = gr.Code(
                    language="python",
                    lines=20,
                    label="代码内容 (编辑/查看)",
                    interactive=True,
                )
                with gr.Row():
                    save_edit_btn = gr.Button("💾 保存修改")
                    debug_input = gr.Textbox(
                        label="调试输入参数 (可选)", placeholder="如果代码需要输入"
                    )
                    debug_btn = gr.Button("▶️ 运行调试")
                debug_output = gr.Textbox(
                    label="调试输出结果", lines=10, interactive=False
                )

        # 事件处理
        template_dropdown.change(
            fn=load_template, inputs=[template_dropdown], outputs=[new_code_content]
        )

        refresh_list_btn.click(fn=load_user_codes, inputs=[], outputs=[code_selector])

        save_new_code_btn.click(
            fn=save_new_code,
            inputs=[new_code_name, new_code_content],
            outputs=[new_code_name, new_code_content, code_selector],
        )

        code_selector.change(
            fn=load_code_content, inputs=[code_selector], outputs=[code_editor]
        )

        save_edit_btn.click(
            fn=save_edited_code, inputs=[code_selector, code_editor], outputs=[]
        )

        debug_btn.click(
            fn=debug_code, inputs=[code_selector, debug_input], outputs=[debug_output]
        )

    return {"code_selector": code_selector, "refresh_list_btn": refresh_list_btn}
