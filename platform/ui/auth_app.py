import gradio as gr
import logging

# 移除 json 导入，因为不再需要 JS
# import json


def create_auth_app():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    def handle_auth_register(username, password, confirm_password):
        """处理注册逻辑"""
        from services.user_service import register_user

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

    # 修改 Gradio 的登录处理函数
    def handle_login(username, password, request: gr.Request):  # 确保 request 参数存在
        """处理 Gradio 登录按钮点击，验证并尝试设置会话"""
        from services.user_service import verify_user

        logging.info(f"Gradio handle_login attempt for user: {username}")

        if not username or not password:
            gr.Warning("用户名和密码不能为空")
            return "用户名和密码不能为空"

        # 1. 验证用户
        success, message = verify_user(username, password)

        if success:
            # 2. 验证成功，尝试设置 FastAPI 会话
            try:
                # 直接尝试访问和设置 session
                request.session["username"] = username
                logging.info(
                    f"Gradio handle_login: Verification successful for {username}. Session set: {dict(request.session)}"
                )
                gr.Info("登录成功！请手动访问 /gradio 路径。")
                # 返回成功消息，提示用户下一步操作
                return f"登录成功: {message}. 请手动导航到 /gradio"
            except Exception as e:
                # 捕获访问或设置 session 时可能发生的任何错误
                logging.error(
                    f"Gradio handle_login: Failed to access or set session. Error: {e}",
                    exc_info=True,  # 记录详细的回溯信息
                )
                gr.Error("登录验证成功，但设置会话失败。请检查服务器日志或联系管理员。")
                return "登录验证成功，但设置会话失败。"

        else:
            # 3. 验证失败
            logging.warning(
                f"Gradio handle_login: Verification failed for {username}: {message}"
            )
            gr.Warning(f"登录失败: {message}")
            return f"登录失败: {message}"

    with gr.Blocks(title="认证中心") as auth_app:
        gr.Markdown("# 代码对战平台 - 认证中心")
        with gr.Tabs() as auth_tabs:
            with gr.TabItem("登录"):
                with gr.Column():
                    gr.Markdown("请输入您的凭据登录。")
                    login_username = gr.Textbox(
                        label="用户名", placeholder="输入用户名"
                    )
                    login_password = gr.Textbox(
                        label="密码", type="password", placeholder="输入密码"
                    )
                    # 添加用于显示状态的 Markdown 组件
                    login_status_message = gr.Markdown("")
                    # 移除 elem_id
                    login_button = gr.Button("✅ 登录", variant="primary")

                    # 绑定 Gradio 的 click 事件
                    login_button.click(
                        fn=handle_login,
                        inputs=[login_username, login_password],
                        outputs=[login_status_message],
                        # Gradio 会自动将 gr.Request 注入到带有类型提示的 request 参数
                        api_name="handle_login_gradio",
                    )

            with gr.TabItem("注册"):
                with gr.Column():
                    gr.Markdown("创建新账户。")
                    reg_username = gr.Textbox(label="用户名", placeholder="设置用户名")
                    reg_password = gr.Textbox(
                        label="密码", type="password", placeholder="设置密码"
                    )
                    reg_confirm_password = gr.Textbox(
                        label="确认密码", type="password", placeholder="再次输入密码"
                    )
                    reg_message = gr.Markdown("")
                    register_button = gr.Button("🚀 注册新账户", variant="primary")

                    # 注册按钮的逻辑保持不变
                    register_button.click(
                        fn=handle_auth_register,
                        inputs=[reg_username, reg_password, reg_confirm_password],
                        outputs=[
                            reg_username,
                            reg_password,
                            reg_confirm_password,
                            reg_message,
                        ],
                    )

    return auth_app
