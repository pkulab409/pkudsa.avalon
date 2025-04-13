import gradio as gr
import logging

# Import user service functions needed for login/register
from services.user_service import register_user, verify_user


def create_main_app():
    """创建包含认证和主功能的应用界面"""
    from ui.components.code_tab import create_code_tab
    from ui.components.duel_tab import create_duel_tab
    from ui.components.user_tab import create_user_tab
    from ui.components.ladder_tab import create_ladder_tab

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # --- Authentication Handlers (moved from auth_app.py) ---
    def handle_auth_register(username, password, confirm_password):
        """处理注册逻辑"""
        if not username or not password or not confirm_password:
            gr.Warning("所有字段均为必填项")
            return gr.update(), gr.update(), gr.update(), "所有字段均为必填项"
        if password != confirm_password:
            gr.Warning("两次输入的密码不匹配")
            return (
                gr.update(),
                gr.update(value=""),
                gr.update(value=""),
                "两次输入的密码不匹配",
            )
        success, message = register_user(username, password)
        if success:
            gr.Info(message + " 请切换到登录模式进行登录。")
            return (
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=""),
                f"注册成功: {message}",
            )
        else:
            gr.Warning(message)
            return (
                gr.update(),
                gr.update(value=""),
                gr.update(value=""),
                f"注册失败: {message}",
            )

    def handle_login(username, password, request: gr.Request):
        """处理登录按钮点击，验证、设置会话并更新UI状态"""
        logging.info(f"handle_login attempt for user: {username}")
        if not username or not password:
            gr.Warning("用户名和密码不能为空")
            # Return updates for all relevant outputs on failure
            return (
                "用户名和密码不能为空",
                None,
                False,
                gr.update(visible=True),
                gr.update(visible=False),
            )

        success, message = verify_user(username, password)
        if success:
            try:
                request.session["username"] = username
                logging.info(f"Login successful for {username}. Session set.")
                gr.Info("登录成功！")
                # Return updates: clear status, set username_state, set logged_in_state, hide login, show main
                return (
                    f"登录成功: {message}",
                    username,
                    True,
                    gr.update(visible=False),
                    gr.update(visible=True),
                )
            except Exception as e:
                logging.error(f"Failed to set session after login: {e}", exc_info=True)
                gr.Error("登录验证成功，但设置会话失败。")
                # Return updates on session setting failure
                return (
                    "登录验证成功，但设置会话失败。",
                    None,
                    False,
                    gr.update(visible=True),
                    gr.update(visible=False),
                )
        else:
            logging.warning(f"Login failed for {username}: {message}")
            gr.Warning(f"登录失败: {message}")
            # Return updates on verification failure
            return (
                f"登录失败: {message}",
                None,
                False,
                gr.update(visible=True),
                gr.update(visible=False),
            )

    def handle_logout(request: gr.Request):
        """处理登出逻辑"""
        try:
            if "session" in request.scope:
                request.session.clear()
                logging.info("User logged out, session cleared.")
                gr.Info("您已成功登出。")
            else:
                logging.warning("Logout attempt but session scope not found.")
        except Exception as e:
            logging.error(f"Error during logout: {e}", exc_info=True)
            gr.Error("登出时发生错误。")
        # Return updates: clear username_state, set logged_in_state to False, show login, hide main
        return None, False, gr.update(visible=True), gr.update(visible=False)

    # --- UI Definition ---
    with gr.Blocks(title="代码对战平台") as app:
        # --- States ---
        username_state = gr.State(None)
        logged_in_state = gr.State(False)  # Controls visibility

        # --- Login/Register UI (Initially Visible) ---
        with gr.Group(visible=True) as login_ui_group:
            gr.Markdown("# 代码对战平台 - 请登录或注册")
            with gr.Tabs():
                with gr.TabItem("登录"):
                    with gr.Column():
                        login_username = gr.Textbox(
                            label="用户名", placeholder="输入用户名"
                        )
                        login_password = gr.Textbox(
                            label="密码", type="password", placeholder="输入密码"
                        )
                        login_status_message = gr.Markdown("")
                        login_button = gr.Button("✅ 登录", variant="primary")
                with gr.TabItem("注册"):
                    with gr.Column():
                        reg_username = gr.Textbox(
                            label="用户名", placeholder="设置用户名"
                        )
                        reg_password = gr.Textbox(
                            label="密码", type="password", placeholder="设置密码"
                        )
                        reg_confirm_password = gr.Textbox(
                            label="确认密码",
                            type="password",
                            placeholder="再次输入密码",
                        )
                        reg_message = gr.Markdown("")
                        register_button = gr.Button("🚀 注册新账户", variant="primary")

        # --- Main Application UI (Initially Hidden) ---
        with gr.Group(visible=False) as main_app_group:
            # Header
            with gr.Row():
                with gr.Column(scale=4):
                    gr.Markdown("# 代码对战平台")
                    gr.Markdown("欢迎回来！")
                with gr.Column(scale=1):
                    # Add Logout Button here
                    logout_button = gr.Button("🚪 登出")

            # Status Indicator (Optional, can be removed if logout button is prominent)
            username_indicator = gr.Markdown(elem_classes=["status-indicator"])

            # Main Tabs
            with gr.Tabs() as tabs:
                with gr.TabItem("👤 用户中心") as tab_user:
                    # Pass username_state to the tab creation function
                    user_components = create_user_tab(username_state)
                with gr.TabItem("💻 代码管理") as tab_code:
                    code_components = create_code_tab(username_state)
                with gr.TabItem("⚔️ 对战中心") as tab_duel:
                    duel_components = create_duel_tab(username_state)
                with gr.TabItem("🏆 天梯排名") as tab_ladder:
                    ladder_components = create_ladder_tab()

            # Footer
            with gr.Row():
                gr.Markdown("© 2025 代码对战平台 | 技术支持：Gradio")

        # --- Event Handlers ---

        # Login Button Click
        login_button.click(
            fn=handle_login,
            inputs=[login_username, login_password],
            outputs=[
                login_status_message,
                username_state,
                logged_in_state,
                login_ui_group,
                main_app_group,
            ],
        )

        # Register Button Click
        register_button.click(
            fn=handle_auth_register,
            inputs=[reg_username, reg_password, reg_confirm_password],
            outputs=[reg_username, reg_password, reg_confirm_password, reg_message],
        )

        # Logout Button Click
        logout_button.click(
            fn=handle_logout,
            inputs=[],  # Request is automatically passed
            outputs=[username_state, logged_in_state, login_ui_group, main_app_group],
        )

        # Update indicator when username_state changes (after login/logout)
        username_state.change(
            fn=lambda u: u if u else "未登录",
            inputs=[username_state],
            outputs=[username_indicator],
        )

        # Initial Load: Check session and set initial UI visibility
        def check_initial_login(request: gr.Request):
            username = request.session.get("username")
            if username:
                logging.info(f"Initial load: Found active session for {username}")
                return username, True, gr.update(visible=False), gr.update(visible=True)
            else:
                logging.info("Initial load: No active session found.")
                return None, False, gr.update(visible=True), gr.update(visible=False)

        app.load(
            fn=check_initial_login,
            inputs=[],  # Request is automatically passed
            outputs=[username_state, logged_in_state, login_ui_group, main_app_group],
        )

    return app
