import gradio as gr
from data_storage import get_user_codes, save_code, get_code_content
import io
import sys
import traceback


def save_new_code(user_state, code_name, code_content):
    if not user_state["username"]:
        return "请先登录"

    if not code_name or not code_content:
        return "代码名称和内容不能为空"

    user_codes = get_user_codes(user_state["username"])
    if code_name in user_codes:
        return "代码名称已存在，请使用编辑功能修改代码"

    success, message = save_code(user_state["username"], code_name, code_content)
    return message


def load_user_codes(user_state):
    if not user_state["username"]:
        return []

    user_codes = get_user_codes(user_state["username"])
    return list(user_codes.keys())


def load_code_for_edit(user_state, code_name):
    if not user_state["username"] or not code_name:
        return ""

    return get_code_content(user_state["username"], code_name)


def save_edited_code(user_state, code_name, code_content):
    if not user_state["username"]:
        return "请先登录"

    if not code_name or not code_content:
        return "代码名称和内容不能为空"

    success, message = save_code(user_state["username"], code_name, code_content)
    return message


def debug_code(user_state, code_name, input_params):
    if not user_state["username"] or not code_name:
        return "请先登录并选择代码"

    code_content = get_code_content(user_state["username"], code_name)
    if not code_content:
        return "获取代码内容失败"

    # 捕获标准输出和错误
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    redirected_output = io.StringIO()
    redirected_error = io.StringIO()
    sys.stdout = redirected_output
    sys.stderr = redirected_error

    try:
        # 准备执行环境
        exec_globals = {"input_params": input_params, "__builtins__": __builtins__}

        # 执行代码
        exec(code_content, exec_globals)

        # 如果代码中有play_game函数，尝试调用它
        if "play_game" in exec_globals:
            result = exec_globals["play_game"]()
            print(f"play_game() 返回结果: {result}")

    except Exception as e:
        print(f"执行错误: {str(e)}")
        traceback.print_exc(file=sys.stderr)
    finally:
        # 恢复标准输出和错误
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    # 获取输出和错误
    output = redirected_output.getvalue()
    error = redirected_error.getvalue()

    return f"标准输出:\n{output}\n\n错误输出:\n{error}"


# 添加一个新函数，返回两个下拉菜单的更新
def update_all_code_lists(user_state):
    codes = load_user_codes(user_state)
    return gr.update(choices=codes), gr.update(choices=codes)


# 添加刷新代码列表的功能
def update_code_list(user_state):
    return gr.update(choices=load_user_codes(user_state))


def create_code_management_tab(user_state):
    with gr.Tab("代码管理"):
        # 首先预先定义所有的下拉菜单变量
        edit_code_dropdown = gr.Dropdown(choices=[], label="选择要编辑的代码")
        debug_code_dropdown = gr.Dropdown(choices=[], label="选择要调试的代码")

        with gr.Row():
            with gr.Column():
                gr.Markdown("### 新建代码")
                new_code_name = gr.Textbox(label="代码名称")
                new_code_content = gr.Code(
                    language="python", lines=20, label="代码内容"
                )
                save_new_code_btn = gr.Button("保存代码")
                new_code_result = gr.Textbox(label="代码保存结果")

                save_new_code_btn.click(
                    fn=save_new_code,
                    inputs=[user_state, new_code_name, new_code_content],
                    outputs=new_code_result,
                )

                # 保存代码后自动刷新所有代码列表
                save_new_code_btn.click(
                    fn=update_all_code_lists,
                    inputs=[user_state],
                    outputs=[edit_code_dropdown, debug_code_dropdown],
                )

        with gr.Row():
            with gr.Column():
                gr.Markdown("### 编辑代码")

                # 这里不需要再次定义edit_code_dropdown，使用上面已定义的变量
                refresh_code_btn = gr.Button("刷新代码列表")
                edit_code_content = gr.Code(
                    language="python", lines=20, label="代码内容 (编辑)"
                )
                save_edit_btn = gr.Button("保存修改")
                edit_result = gr.Textbox(label="代码修改保存结果")

                # 添加刷新代码列表的功能
                refresh_code_btn.click(
                    fn=update_code_list, inputs=[user_state], outputs=edit_code_dropdown
                )

                # 选择代码时加载内容
                edit_code_dropdown.change(
                    fn=load_code_for_edit,
                    inputs=[user_state, edit_code_dropdown],
                    outputs=edit_code_content,
                )

                # 保存修改
                save_edit_btn.click(
                    fn=save_edited_code,
                    inputs=[user_state, edit_code_dropdown, edit_code_content],
                    outputs=edit_result,
                )

        with gr.Row():
            with gr.Column():
                gr.Markdown("### 辅助调试")
                # 使用上面已定义的debug_code_dropdown，不要重新定义
                debug_refresh_btn = gr.Button("刷新代码列表")
                debug_code_display = gr.Code(
                    language="python",
                    lines=10,
                    label="要调试的代码 (只读)",
                    interactive=False,
                )
                debug_input = gr.Textbox(label="输入参数 (可选)")
                debug_btn = gr.Button("运行调试")
                debug_output = gr.Textbox(label="调试输出结果", lines=10)

                # 刷新调试代码列表
                debug_refresh_btn.click(
                    fn=update_code_list,
                    inputs=[user_state],
                    outputs=debug_code_dropdown,
                )

                # 选择代码时加载内容
                debug_code_dropdown.change(
                    fn=load_code_for_edit,
                    inputs=[user_state, debug_code_dropdown],
                    outputs=debug_code_display,
                )

                # 运行调试
                debug_btn.click(
                    fn=debug_code,
                    inputs=[user_state, debug_code_dropdown, debug_input],
                    outputs=debug_output,
                )
