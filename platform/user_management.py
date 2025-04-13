# 用户管理模块 (重构UI)

import gradio as gr
from data_storage import register_user, verify_user, get_user_profile, get_user_duels

# --- Backend Logic (Modified Register) ---


def handle_register(username, password, confirm_password):
    """处理注册逻辑，包含密码确认"""
    if not username or not password or not confirm_password:
        gr.Warning("所有字段均为必填项")
        return gr.update(), gr.update(), gr.update()  # 返回更新以清除或保留字段

    if password != confirm_password:
        gr.Warning("两次输入的密码不匹配")
        # 清空密码字段，保留用户名
        return gr.update(), gr.update(value=""), gr.update(value="")

    success, message = register_user(username, password)
    if success:
        gr.Info(message)
        # 注册成功后清空所有字段
        return gr.update(value=""), gr.update(value=""), gr.update(value="")
    else:
        gr.Warning(message)
        # 用户名已存在时，不清空用户名，清空密码
        return gr.update(), gr.update(value=""), gr.update(value="")


def handle_login(username, password, user_state):
    """处理登录逻辑"""
    if not username or not password:
        gr.Warning("用户名和密码不能为空")
        # 返回更新以匹配期望的输出数量 (状态标签, 个人信息, 密码框)
        return (
            gr.update(value="登录失败"),
            gr.update(value="请输入用户名和密码后登录。"),
            gr.update(value=""),
        )

    success, message = verify_user(username, password)
    if success:
        user_state["username"] = username
        profile_message = f"欢迎您，{username}！点击下方按钮查看个人信息。"
        gr.Info(message)
        # 更新状态标签, 个人信息占位符, 清空密码框
        return (
            gr.update(value=username),
            gr.update(value=profile_message),
            gr.update(value=""),
        )
    else:
        gr.Warning(message)
        # 更新状态标签, 个人信息占位符, 清空密码框
        return (
            gr.update(value="登录失败"),
            gr.update(value="登录失败，请检查用户名和密码。"),
            gr.update(value=""),
        )


def view_profile(user_state):
    """查看用户个人资料"""
    username = user_state.get("username")
    if not username:
        gr.Warning("请先登录")
        return "请先登录后查看个人信息。"

    user_data = get_user_profile(username)
    if not user_data:
        gr.Error("获取用户信息失败")
        return "无法加载用户信息。"

    user_duels = get_user_duels(username)
    duels_info = f"共参与 {len(user_duels)} 场对战"

    profile_info = f"""
    👤 **用户名:** {username}
    ⭐ **天梯积分:** {user_data.get('ladder_points', 1000)}
    🏆 **当前分区:** {user_data.get('division', '新手区')}
    ⚔️ **对战记录:** {duels_info}
    """
    return profile_info.strip()


# --- Gradio UI Creation ---


def create_user_management_tab(user_state):
    """创建用户管理Tab界面"""
    with gr.Tab("👤 用户中心"):  # 使用更合适的 emoji
        with gr.Row():
            # 左侧：登录/注册表单
            with gr.Column(scale=1):
                mode_selector = gr.Radio(
                    ["登录", "注册"], label="选择操作", value="登录", interactive=True
                )

                username_input = gr.Textbox(
                    label="用户名", placeholder="输入您的用户名"
                )
                password_input = gr.Textbox(
                    label="密码", type="password", placeholder="输入您的密码"
                )
                confirm_password_input = gr.Textbox(
                    label="确认密码",
                    type="password",
                    placeholder="再次输入您的密码",
                    visible=False,  # 初始隐藏
                    interactive=True,
                )

                action_button = gr.Button("✅ 登录")  # 初始为登录按钮

                current_user_label = gr.Textbox(
                    label="当前登录用户",
                    interactive=False,
                    placeholder="未登录",
                    scale=1,  # 让它占满宽度
                )

            # 右侧：个人信息展示
            with gr.Column(scale=1):
                gr.Markdown("### 📊 个人信息")
                view_profile_btn = gr.Button("👀 查看/刷新个人信息")
                profile_info = gr.Markdown(
                    value="*请先登录或成功登录后点击按钮查看个人信息。*",
                )

        # --- 事件处理 ---

        # 模式选择器变化时的处理
        def switch_mode(mode):
            if mode == "登录":
                return (
                    gr.update(visible=False),  # 隐藏确认密码
                    gr.update(value="✅ 登录"),  # 更新按钮文本
                )
            else:  # 注册模式
                return (
                    gr.update(visible=True),  # 显示确认密码
                    gr.update(value="🚀 注册"),  # 更新按钮文本
                )

        mode_selector.change(
            fn=switch_mode,
            inputs=mode_selector,
            outputs=[confirm_password_input, action_button],
        )

        # 主操作按钮点击事件
        def perform_action(
            mode, username, password, confirm_password, current_user_state
        ):
            if mode == "登录":
                # 调用登录处理函数
                login_status, profile_placeholder, pw_update = handle_login(
                    username, password, current_user_state
                )
                # 登录成功后自动刷新个人信息
                profile_update = (
                    view_profile(current_user_state)
                    if current_user_state.get("username")
                    else profile_placeholder
                )
                # 返回所有需要的更新
                return login_status, profile_update, pw_update
            else:  # 注册模式
                # 调用注册处理函数
                uname_update, pw_update, confirm_pw_update = handle_register(
                    username, password, confirm_password
                )
                # 注册不直接影响登录状态和个人信息显示，返回字段更新
                return (
                    gr.update(),
                    gr.update(),
                    pw_update,
                )  # 返回对应登录流程的输出数量，但不更新它们

        action_button.click(
            fn=perform_action,
            inputs=[
                mode_selector,
                username_input,
                password_input,
                confirm_password_input,
                user_state,
            ],
            # 输出需要匹配登录流程的输出：状态标签、个人信息区、密码输入框（用于清空）
            outputs=[current_user_label, profile_info, password_input],
        ).then(  # 链式调用：如果登录成功，再次调用 view_profile 更新信息
            fn=lambda s: (
                view_profile(s) if s.get("username") else gr.update()
            ),  # 仅在登录后执行
            inputs=user_state,
            outputs=profile_info,
        )

        # 查看/刷新个人信息按钮点击事件
        view_profile_btn.click(
            fn=view_profile, inputs=[user_state], outputs=profile_info
        )

        # (可选) 登录成功后自动更新代码管理等其他Tab的列表
        # 这需要更复杂的事件传递或状态共享机制，当前保持简单
