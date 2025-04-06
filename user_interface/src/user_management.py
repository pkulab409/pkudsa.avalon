import gradio as gr
from data_storage import register_user, verify_user, get_user_profile, get_user_duels


def register(username, password):
    if not username or not password:
        return "用户名和密码不能为空"

    success, message = register_user(username, password)
    return message


def login(username, password, user_state):
    if not username or not password:
        return "用户名和密码不能为空", "", ""

    success, message = verify_user(username, password)
    if success:
        user_state["username"] = username
        return message, username, f"欢迎您，{username}"
    else:
        return message, "", ""


def view_profile(user_state):
    if user_state["username"] is None:
        return "请先登录"

    user_data = get_user_profile(user_state["username"])
    if not user_data:
        return "获取用户信息失败"

    # 获取用户的对战记录
    user_duels = get_user_duels(user_state["username"])
    duels_info = f"共参与 {len(user_duels)} 场对战\n"

    # 格式化个人信息
    profile_info = f"""
    用户名: {user_state["username"]}
    天梯积分: {user_data.get('ladder_points', 1000)}
    当前分区: {user_data.get('division', '新手区')}
    {duels_info}
    """

    return profile_info


def create_user_management_tab(user_state):
    with gr.Tab("用户管理"):
        with gr.Row():
            with gr.Column():
                gr.Markdown("### 用户注册")
                register_username = gr.Textbox(label="用户名")
                register_password = gr.Textbox(label="密码", type="password")
                register_btn = gr.Button("注册")
                register_result = gr.Textbox(label="注册结果")

                register_btn.click(
                    fn=register,
                    inputs=[register_username, register_password],
                    outputs=register_result,
                )

            with gr.Column():
                gr.Markdown("### 用户登录")
                login_username = gr.Textbox(label="用户名")
                login_password = gr.Textbox(label="密码", type="password")
                login_btn = gr.Button("登录")
                login_result = gr.Textbox(label="登录结果")
                current_user_label = gr.Textbox(label="当前用户", interactive=False)

                # 添加这一行来初始化profile_info组件
                profile_info = gr.Markdown("请先登录查看个人资料")

                login_btn.click(
                    fn=login,
                    inputs=[login_username, login_password, user_state],
                    outputs=[login_result, current_user_label, profile_info],
                )

        with gr.Row():
            with gr.Column():
                gr.Markdown("### 个人信息")
                view_profile_btn = gr.Button("查看个人信息")
                profile_info = gr.Textbox(label="个人信息展示", lines=10)

                view_profile_btn.click(
                    fn=view_profile, inputs=[user_state], outputs=profile_info
                )

    return user_state
