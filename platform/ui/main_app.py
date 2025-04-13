import gradio as gr
import logging


def create_main_app():
    """创建主应用界面"""
    from ui.components.code_tab import create_code_tab
    from ui.components.duel_tab import create_duel_tab
    from ui.components.user_tab import create_user_tab
    from ui.components.ladder_tab import create_ladder_tab

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    def get_username(request: gr.Request):
        """获取当前登录用户名"""
        return request.session.get("username", "未登录")

    with gr.Blocks(
        title="代码对战平台",
        theme=gr.themes.Soft(
            primary_hue="blue", secondary_hue="purple", neutral_hue="slate"
        ),
        css="""
        .status-indicator {
            position: fixed;
            bottom: 10px;
            right: 10px;
            padding: 5px 10px;
            background-color: rgba(0,0,0,0.5);
            color: white;
            border-radius: 5px;
            font-size: 12px;
        }
        """,
    ) as app:
        # 页面顶部
        with gr.Row():
            with gr.Column():
                gr.Markdown("# 代码对战平台")
                gr.Markdown(
                    "欢迎，这是一个专为编程爱好者设计的代码对战平台。在这里，您可以编写自己的代码，参与有趣的对战，并在天梯排名中一争高下。"
                )

        # 状态指示器
        username_indicator = gr.Markdown(
            value="加载中...", visible=True, elem_classes=["status-indicator"]
        )

        # 主体标签页
        with gr.Tabs() as tabs:
            # 用户中心
            with gr.TabItem("👤 用户中心") as tab_user:
                user_components = create_user_tab()

            # 代码管理
            with gr.TabItem("💻 代码管理") as tab_code:
                code_components = create_code_tab()

            # 对战中心
            with gr.TabItem("⚔️ 对战中心") as tab_duel:
                duel_components = create_duel_tab()

            # 天梯排名
            with gr.TabItem("🏆 天梯排名") as tab_ladder:
                ladder_components = create_ladder_tab()

        # 页脚
        with gr.Row():
            gr.Markdown("© 2025 代码对战平台 | 技术支持：Gradio")

        # 页面加载时更新状态
        app.load(fn=get_username, inputs=[], outputs=[username_indicator])

        # 标签切换时更新状态和内容
        for tab in [tab_user, tab_code, tab_duel, tab_ladder]:
            tab.select(fn=get_username, inputs=[], outputs=[username_indicator])

    return app
