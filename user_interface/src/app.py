'''Avalon代码对战平台。
它是一个基于Gradio构建的Web应用，允许用户通过不同的Tab页进行交互。平台包含以下主要功能模块：
- 用户管理：处理用户的注册、登录以及状态维护。
- 代码管理：允许用户编写、上传和管理代码。
- 对战管理：提供代码对战功能，用户可以参与编程对战。
- 天梯排名：展示用户在平台中的排名情况，鼓励良性竞争。
'''


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
with gr.Blocks(title="Avalon代码对战平台", theme=gr.themes.Soft()) as app:
    gr.Markdown("# Avalon代码对战平台")
    gr.Markdown(
        "欢迎来到Avalon，这是一个专为编程爱好者设计的代码对战平台。在这里，您可以编写自己的代码，参与有趣的对战，并在天梯排名中一争高下。"
    )

    # 创建用户状态组件
    user_state = gr.State({"username": None})

    # 创建各个Tab页面
    with gr.Tabs():
        # 用户管理Tab - 返回当前用户信息，供其他Tab使用
        create_user_management_tab(user_state)

        # 代码管理Tab
        create_code_management_tab(user_state)

        # 对战管理Tab
        create_duel_management_tab(user_state)

        # 天梯排名Tab
        create_ladder_ranking_tab()


# 启动应用
if __name__ == "__main__":
    app.launch()
