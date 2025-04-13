import gradio as gr
from data_storage import get_user_codes, save_code, get_code_content
import io
import sys
import traceback

# --- Backend Logic ---


def save_new_code(user_state, code_name, code_content):
    """保存新代码，并返回更新给UI组件"""
    username = user_state.get("username")
    if not username:
        gr.Warning("请先登录")
        # 返回对应outputs数量的更新
        return gr.update(), gr.update(), gr.update(choices=load_user_codes(user_state))

    if not code_name or not code_content:
        gr.Warning("代码名称和内容不能为空")
        return gr.update(), gr.update(), gr.update(choices=load_user_codes(user_state))

    user_codes = get_user_codes(username)
    if code_name in user_codes:
        gr.Warning("代码名称已存在，请选择该代码进行编辑")
        # 保留名称和内容，更新列表
        return gr.update(), gr.update(), gr.update(choices=load_user_codes(user_state))

    success, message = save_code(username, code_name, code_content)
    if success:
        gr.Info(message)
        # 清空输入框，更新列表
        return (
            gr.update(value=""),
            gr.update(value=""),
            gr.update(choices=load_user_codes(user_state)),
        )
    else:
        gr.Error(message)
        # 保留输入，更新列表
        return gr.update(), gr.update(), gr.update(choices=load_user_codes(user_state))


def load_user_codes(user_state):
    """加载当前登录用户的代码列表"""
    username = user_state.get("username")
    if not username:
        return []
    user_codes = get_user_codes(username)
    return list(user_codes.keys())


def load_code_content_for_display(user_state, code_name):
    """加载代码内容到编辑器/显示区域"""
    username = user_state.get("username")
    if not username or not code_name:
        # 如果没有选择代码，返回空或默认提示
        return ""
    return get_code_content(username, code_name)


def save_edited_code(user_state, code_name, code_content):
    """保存编辑后的代码"""
    username = user_state.get("username")
    if not username:
        gr.Warning("请先登录")
        return gr.update()  # 返回更新给输出组件（例如，状态消息）

    if not code_name:
        gr.Warning("请先从下拉列表中选择要编辑的代码")
        return gr.update()

    if not code_content:
        gr.Warning("代码内容不能为空")
        return gr.update()

    success, message = save_code(username, code_name, code_content)
    if success:
        gr.Info(message)
    else:
        gr.Error(message)
    # 可以返回一个状态消息，或者如果需要更新其他组件，返回gr.update()
    return gr.update()  # 假设只显示Info/Error


def debug_code(user_state, code_name, input_params):
    """执行代码调试"""
    username = user_state.get("username")
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

    # --- 捕获输出和执行逻辑 (保持不变) ---
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    redirected_output = io.StringIO()
    redirected_error = io.StringIO()
    sys.stdout = redirected_output
    sys.stderr = redirected_error

    try:
        exec_globals = {"input_params": input_params, "__builtins__": __builtins__}
        exec(code_content, exec_globals)
        if "play_game" in exec_globals:
            result = exec_globals["play_game"]()
            print(f"play_game() 返回结果: {result}")
    except Exception as e:
        print(f"执行错误: {str(e)}")
        traceback.print_exc(file=sys.stderr)
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    output = redirected_output.getvalue()
    error = redirected_error.getvalue()
    result_output = f"--- 标准输出 ---\n{output}\n\n--- 错误输出 ---\n{error}"
    return result_output


# --- Gradio UI Creation (Refactored) ---


def create_code_management_tab(user_state):
    """创建代码管理Tab界面 (重构版)"""

    # --- Helper function to update the main dropdown ---
    def update_code_selector(current_user_state):
        codes = load_user_codes(current_user_state)
        return gr.update(choices=codes, value=None)  # 更新选项并清空选择

    with gr.Tab("💻 代码管理"):
        with gr.Row():
            # --- 左侧：新建代码 ---
            with gr.Column(scale=1):
                gr.Markdown("### ✨ 新建代码")
                new_code_name = gr.Textbox(
                    label="新代码名称", placeholder="例如: my_strategy_v1"
                )
                new_code_content = gr.Code(
                    language="python",
                    lines=15,
                    label="新代码内容",
                    value="# 在此输入您的 Python 代码...\n\ndef play_game():\n    # 返回 'rock', 'paper', 或 'scissors'\n    return 'rock'\n",
                )
                save_new_code_btn = gr.Button("💾 保存新代码")

            # --- 右侧：编辑与调试 ---
            with gr.Column(scale=2):
                gr.Markdown("### ✏️ 编辑 / 🐞 调试")
                with gr.Row():
                    code_selector_dropdown = gr.Dropdown(
                        choices=load_user_codes(user_state.value),  # 初始加载
                        label="选择代码进行操作",
                        interactive=True,
                        scale=4,  # 给下拉菜单更多空间
                    )
                    refresh_code_list_btn = gr.Button("🔄 刷新列表", scale=1)

                code_editor_area = gr.Code(
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

        # --- 事件处理 ---

        # 刷新按钮更新主代码选择器
        refresh_code_list_btn.click(
            fn=update_code_selector, inputs=[user_state], outputs=code_selector_dropdown
        )

        # 保存新代码按钮
        save_new_code_btn.click(
            fn=save_new_code,
            inputs=[user_state, new_code_name, new_code_content],
            # 输出: 清空名称, 清空内容, 更新主代码选择器
            outputs=[new_code_name, new_code_content, code_selector_dropdown],
        )

        # 主代码选择器变化时，加载代码到编辑器
        code_selector_dropdown.change(
            fn=load_code_content_for_display,
            inputs=[user_state, code_selector_dropdown],
            outputs=code_editor_area,
        )

        # 保存修改按钮
        save_edit_btn.click(
            fn=save_edited_code,
            inputs=[user_state, code_selector_dropdown, code_editor_area],
            outputs=None,  # 仅显示提示信息
        )

        # 调试按钮
        debug_btn.click(
            fn=debug_code,
            inputs=[user_state, code_selector_dropdown, debug_input],
            outputs=debug_output,
        )

        # --- 状态同步 (示例，需要从 user_management 触发) ---
        # 当用户登录/注销时，自动刷新代码列表
        # 这通常需要在 app.py 中设置更复杂的事件监听或回调
        # 例如，在 user_management 的登录成功事件后，触发这里的刷新按钮点击
        # def handle_login_success_updates(current_user_state):
        #     # ... 其他登录成功后的更新 ...
        #     # 返回一个更新给 code_selector_dropdown
        #     codes = load_user_codes(current_user_state)
        #     return ..., gr.update(choices=codes, value=None)
        #
        # 在 user_management.py 的 action_button.click.then(...) 中添加输出到 code_selector_dropdown
        # 这需要将 code_selector_dropdown 作为参数传递给 create_user_management_tab 或通过 app 实例访问
        # 为了保持模块独立性，目前依赖手动刷新。
