import gradio as gr
import logging
from tinydb import Query
from db.database import get_user_db
import matplotlib.pyplot as plt


def create_ladder_tab():
    """创建天梯排名Tab界面"""

    def load_ranking_data():
        """加载天梯排名数据"""
        try:
            db = get_user_db()
            users = db.all()

            # 按积分排序
            ranked_users = sorted(
                users, key=lambda x: x.get("ladder_points", 0), reverse=True
            )

            # 英文分区映射
            division_map_en = {"新手区": "Bronze", "进阶区": "Silver", "大师区": "Gold"}

            # 构建排名表格数据 - 使用英文分区
            rows = []
            for i, user in enumerate(ranked_users):
                username = user.get("username", "Unknown")
                points = user.get("ladder_points", 0)
                division_internal = user.get("division", "新手区")
                division_display_en = division_map_en.get(division_internal, "Unknown")

                rows.append(
                    [i + 1, username, points, division_display_en]
                )  # 使用英文分区

            # 格式化为表格字符串 - 使用英文表头
            table_str = "| Rank | Username | Points | Division |\n"
            table_str += "|------|----------|--------|----------|\n"
            for row in rows:
                table_str += f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |\n"

            # 创建统计图表 - 使用英文标签
            division_counts_en = {"Bronze": 0, "Silver": 0, "Gold": 0}
            for user in users:
                division_internal = user.get("division", "新手区")
                division_display_en = division_map_en.get(division_internal, "Unknown")
                if division_display_en in division_counts_en:
                    division_counts_en[division_display_en] += 1

            fig, ax = plt.subplots(figsize=(6, 4))
            divisions_en = list(division_counts_en.keys())  # 使用英文分区键
            counts = list(division_counts_en.values())

            ax.bar(
                divisions_en, counts, color=["#cd7f32", "#c0c0c0", "#ffd700"]
            )  # 使用 Bronze, Silver, Gold 颜色
            ax.set_title("User Distribution by Division")  # 英文标题
            ax.set_xlabel("Division")  # 英文 X 轴标签
            ax.set_ylabel("Number of Users")  # 英文 Y 轴标签

            for i, count in enumerate(counts):
                ax.text(i, count + 0.1, str(count), ha="center")

            return table_str, fig
        except Exception as e:
            logging.error(f"Error loading ranking data: {e}")
            # 返回英文错误信息
            return "Failed to load ranking data: " + str(e), None

    # 使用英文 Tab 标题
    with gr.Tab("🏆 Ladder Rankings"):
        with gr.Row():
            with gr.Column(scale=2):
                # 使用英文 Markdown 标题
                gr.Markdown("### 📊 Leaderboard")

                ranking_table = gr.Markdown(
                    "Loading...",  # 英文加载提示
                )

                # 使用英文按钮文本
                refresh_ranking_btn = gr.Button("🔄 Refresh Rankings")

            with gr.Column(scale=1):
                # 使用英文 Markdown 标题
                gr.Markdown("### 📈 Division Stats")

                # 使用英文 Plot 标签
                division_plot = gr.Plot(label="Division Statistics")

        # 事件处理
        refresh_ranking_btn.click(
            fn=load_ranking_data, inputs=[], outputs=[ranking_table, division_plot]
        )

    return {"refresh_ranking_btn": refresh_ranking_btn}
