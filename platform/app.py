import gradio as gr
import os
import importlib
import sys

# 重新加载模块
if "user_management" in sys.modules:
    importlib.reload(sys.modules["user_management"])
if "code_management" in sys.modules:
    importlib.reload(sys.modules["code_management"])
if "duel_management" in sys.modules:
    importlib.reload(sys.modules["duel_management"])
if "ladder_ranking" in sys.modules:
    importlib.reload(sys.modules["ladder_ranking"])

from user_management import create_user_management_tab
from code_management import create_code_management_tab
from duel_management import create_duel_management_tab
from ladder_ranking import create_ladder_ranking_tab


# 确保数据目录存在
os.makedirs("data", exist_ok=True)

# 创建Gradio应用
with gr.Blocks(
    title="代码对战平台",
    theme=gr.themes.Soft(
        primary_hue="blue", secondary_hue="purple", neutral_hue="slate"
    ),
) as app:
    with gr.Row(elem_id="header-row"):
        # Removed the gr.Column containing the gr.Image
        with gr.Column(scale=1):  # Adjusted scale or simply use default
            gr.Markdown("# 代码对战平台", elem_classes=["header-text"])
            gr.Markdown(
                "欢迎，这是一个专为编程爱好者设计的代码对战平台。在这里，您可以编写自己的代码，参与有趣的对战，并在天梯排名中一争高下。",
                elem_classes=["description-text"],
            )

    # 创建用户状态组件
    user_state = gr.State({"username": None})

    # 创建各个Tab页面
    with gr.Tabs(elem_classes=["custom-tabs"]) as tabs:
        with gr.TabItem("👤 用户中心", elem_classes=["tab-button"]):
            create_user_management_tab(user_state)

        with gr.TabItem("💻 代码管理", elem_classes=["tab-button"]):
            create_code_management_tab(user_state)

        with gr.TabItem("⚔️ 对战中心", elem_classes=["tab-button"]):
            create_duel_management_tab(user_state)

        with gr.TabItem("🏆 天梯排名", elem_classes=["tab-button"]):
            create_ladder_ranking_tab()

    # 添加页脚
    with gr.Row(elem_id="footer"):
        gr.Markdown(
            "© 2025 代码对战平台 | 技术支持：Gradio", elem_classes=["footer-text"]
        )

# 启动应用
if __name__ == "__main__":
    app.launch(share=True)  # 添加 share=True
