import gradio as gr
import logging
import json


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

    def handle_login(username, password):
        """处理登录逻辑 - 返回API调用需要的数据"""
        if not username or not password:
            return json.dumps({"status": "error", "message": "用户名和密码不能为空"})

        return json.dumps(
            {"status": "success", "username": username, "password": password}
        )

    with gr.Blocks(
        title="认证中心",
        theme=gr.themes.Soft(),
        css="""
        #login-error { 
            color: red; 
            margin-top: 10px; 
            min-height: 20px;
        }
        #login-success {
            color: green;
            margin-top: 10px;
            min-height: 20px;
        }
        """,
    ) as auth_app:
        gr.Markdown("# 代码对战平台 - 认证中心")

        # 隐藏的状态值
        login_result = gr.JSON(value="{}", visible=False)

        # 添加简化的JavaScript实现直接登录
        gr.HTML(
            """
            <script>
            document.addEventListener("DOMContentLoaded", function() {
                // 等待Gradio界面完全加载
                setTimeout(function() {
                    // 找到登录按钮并添加点击事件
                    const loginButton = document.getElementById('login-button');
                    if (loginButton) {
                        console.log("找到登录按钮，正在添加事件监听器");
                        
                        loginButton.addEventListener('click', function() {
                            // 登录按钮添加Gradio的原始事件处理后，再添加我们的处理
                            setTimeout(async function() {
                                // 获取用户名和密码输入
                                const usernameInput = document.querySelector('input[placeholder="输入用户名"]');
                                const passwordInput = document.querySelector('input[type="password"][placeholder="输入密码"]');
                                const errorDiv = document.getElementById('login-error');
                                const successDiv = document.getElementById('login-success');
                                
                                if (!usernameInput || !passwordInput) {
                                    console.error("找不到用户名或密码输入框");
                                    return;
                                }
                                
                                const username = usernameInput.value;
                                const password = passwordInput.value;
                                
                                if (!username || !password) {
                                    if (errorDiv) errorDiv.textContent = "用户名和密码不能为空";
                                    return;
                                }
                                
                                // 显示正在登录
                                if (errorDiv) errorDiv.textContent = "登录中...";
                                if (successDiv) successDiv.textContent = "";
                                
                                try {
                                    // 发送登录请求
                                    const response = await fetch('/api/login', {
                                        method: 'POST',
                                        headers: {
                                            'Content-Type': 'application/json',
                                        },
                                        body: JSON.stringify({ username, password }),
                                        credentials: 'same-origin'
                                    });
                                    
                                    if (response.ok) {
                                        // 登录成功
                                        if (errorDiv) errorDiv.textContent = "";
                                        if (successDiv) successDiv.textContent = "登录成功！正在跳转...";
                                        console.log("登录成功，正在跳转...");
                                        
                                        // 延迟跳转，让用户看到成功消息
                                        setTimeout(function() {
                                            window.location.href = '/gradio';
                                        }, 800);
                                    } else {
                                        // 登录失败
                                        const errorData = await response.json();
                                        if (errorDiv) errorDiv.textContent = `登录失败: ${errorData.detail || response.statusText}`;
                                    }
                                } catch (error) {
                                    // 网络错误
                                    console.error("登录请求失败:", error);
                                    if (errorDiv) errorDiv.textContent = "登录请求失败，请检查网络连接";
                                }
                            }, 100);
                        }, true);
                    } else {
                        console.error("找不到登录按钮");
                    }
                }, 1000); // 给Gradio界面充分加载的时间
            });
            </script>
            """
        )

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
                    gr.HTML("<div id='login-error'></div>")
                    gr.HTML("<div id='login-success'></div>")
                    login_button = gr.Button(
                        "✅ 登录", variant="primary", elem_id="login-button"
                    )

                    # 将登录结果设为可见，并给定ID，供JavaScript使用
                    login_button.click(
                        fn=handle_login,
                        inputs=[login_username, login_password],
                        outputs=[login_result],
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
