'''该模块主要用于管理用户代码，包括新建、编辑、调试代码等。
它依赖于 gradio 库构建用户交互界面，以及 data_storage 模块中提供的存储操作函数。
'''
# 我感觉这个文件的代码难读一点，而且参数比较多，就生成了带Args和Returns的文档…


import gradio as gr
from data_storage import get_user_codes, save_code, get_code_content
import io
import sys
import traceback


def save_new_code(user_state, code_name, code_content):
    '''
    为用户保存一段新的代码。

    首先判断用户是否已登录，并检查代码名称及内容是否为空；
    然后检查用户是否已存在相同名称的代码，如果不存在则调用存储接口保存代码。

    Arguments:
        user_state: 包含用户状态信息的gr.State，必须包含键 "username"。
        code_name: 用户为代码指定的名称。
        code_content: 代码的具体内容。
    '''
    if not user_state["username"]:  # 未登录
        return "请先登录"

    if not code_name or not code_content:
        return "代码名称和内容不能为空"

    user_codes = get_user_codes(user_state["username"])
    if code_name in user_codes:
        return "代码名称已存在，请使用编辑功能修改代码"

    success, message = save_code(user_state["username"], code_name, code_content)
    return message


def load_user_codes(user_state):
    '''
    加载当前登录用户的所有代码列表。如果未登录，则返回空列表。

    Arguments:
        user_state: 包含用户状态信息的gr.State。

    Returns:
        (list): 当前用户保存的代码名称列表。如果用户未登录则返回空列表。
    '''
    if not user_state["username"]:
        return []

    user_codes = get_user_codes(user_state["username"])
    return list(user_codes.keys())


def load_code_for_edit(user_state, code_name):
    '''
    根据用户和代码名称获取代码内容，主要用于编辑前加载代码。

    Arguments:
        user_state: 包含用户状态信息的gr.State。
        code_name: 要加载的代码名称。

    Returns:
        (str): 对应代码的内容。如果用户未登录或代码名称为空，则返回空字符串。
    '''
    if not user_state["username"] or not code_name:
        return ""

    return get_code_content(user_state["username"], code_name)


def save_edited_code(user_state, code_name, code_content):
    '''
    保存对已存在代码的修改。与保存新代码类似，但不检查代码是否已存在，因为这里是覆盖操作。

    Arguments:
        user_state: 用户状态信息。
        code_name: 要保存的代码名称。
        code_content: 编辑后的代码内容。

    Returns:
        (str): 保存操作的结果信息，例如“请先登录”、“代码名称和内容不能为空”或保存后的反馈信息。
    '''

    if not user_state["username"]:
        return "请先登录"

    if not code_name or not code_content:
        return "代码名称和内容不能为空"

    success, message = save_code(user_state["username"], code_name, code_content)
    return message


def debug_code(user_state, code_name, input_params):
    '''
    执行用户保存的代码并捕获执行过程中的标准输出和错误信息。
    支持动态执行代码，并在代码中若存在 play_game 函数，则调用该函数并输出返回结果。
    使用 exec 动态执行代码时捕获异常并输出详细错误信息。

    Arguments:
        user_state: 用户状态信息。
        code_name: 要调试的代码名称。
        input_params: 调试代码时传递的输入参数，作为执行环境中的变量 input_params。

    Returns:
        (str): 包含标准输出和错误输出的调试信息。如果用户未登录、未选择代码或获取代码内容失败，会返回相应的提示信息。
    '''
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
    '''
    辅助函数，用于同时刷新两个下拉菜单（编辑和调试代码列表）的选项。
    通过调用 load_user_codes 获取最新的代码列表，并更新两个下拉组件。

    Arguments:
        user_state: 用户状态信息。

    Returns:
        返回两个Gradio更新对象，分别对应编辑和调试代码的下拉菜单选项更新。
    '''
    codes = load_user_codes(user_state)
    return gr.update(choices=codes), gr.update(choices=codes)


# 添加刷新代码列表的功能
def update_code_list(user_state):
    '''
    辅助函数，用于刷新单个代码列表的选项。
    通过调用 load_user_codes 获取最新的代码列表，并更新下拉组件。

    Arguments:
        user_state: 用户状态信息。

    Returns:
        Gradio更新对象，分别对应编辑和调试代码的下拉菜单选项更新。
    '''
    return gr.update(choices=load_user_codes(user_state))


def create_code_management_tab(user_state):
    '''
    创建“代码管理”标签页界面，该界面包含三个主要部分：
     - 新建代码区域：包含代码名称输入框、代码内容编辑器及保存按钮，保存新代码后自动刷新代码列表。
     - 编辑代码区域：包含下拉菜单选择代码、刷新按钮、代码内容编辑器及保存修改按钮，支持加载选中代码进行编辑并保存修改。
     - 辅助调试区域：包含下拉菜单选择代码、刷新按钮、只读代码展示框、输入参数输入框和调试按钮，用于执行调试并展示调试结果。

    Arguments:
        user_state (dict): 用户状态信息。
    '''
    with gr.Tab("代码管理"):
        # 首先预先定义所有的下拉菜单变量
        edit_code_dropdown = gr.Dropdown(choices=[], label="选择要编辑的代码")
        debug_code_dropdown = gr.Dropdown(choices=[], label="选择要调试的代码")

        with gr.Row():  # 新建代码区域
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

        with gr.Row():  # 编辑代码区域
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

        with gr.Row():  # 调试代码区域
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
