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

            # 构建排名表格数据
            rows = []
            for i, user in enumerate(ranked_users):
                username = user.get("username", "未知")
                points = user.get("ladder_points", 0)
                division = user.get("division", "未知")

                rows.append([i + 1, username, points, division])

            # 格式化为表格字符串
            table_str = "| 排名 | 用户名 | 积分 | 分区 |\n"
            table_str += "|------|--------|------|------|\n"
            for row in rows:
                table_str += f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |\n"

            # 创建统计图表
            division_counts = {"新手区": 0, "进阶区": 0, "大师区": 0}
            for user in users:
                division = user.get("division", "新手区")
                if division in division_counts:
                    division_counts[division] += 1

            fig, ax = plt.subplots(figsize=(6, 4))
            divisions = list(division_counts.keys())
            counts = list(division_counts.values())

            ax.bar(divisions, counts, color=["green", "blue", "purple"])
            ax.set_title("各分区用户分布")
            ax.set_xlabel("分区")
            ax.set_ylabel("用户数")

            for i, count in enumerate(counts):
                ax.text(i, count + 0.1, str(count), ha="center")

            return table_str, fig
        except Exception as e:
            logging.error(f"加载排名数据时出错: {e}")
            return "加载排名数据失败: " + str(e), None

    with gr.Tab("🏆 天梯排名"):
        with gr.Row():
            with gr.Column(scale=2):
                gr.Markdown("### 📊 排行榜")

                ranking_table = gr.Markdown(
                    "加载中...",
                )

                refresh_ranking_btn = gr.Button("🔄 刷新排名")

            with gr.Column(scale=1):
                gr.Markdown("### 📈 分区统计")

                division_plot = gr.Plot(label="分区人数统计")

        # 事件处理
        refresh_ranking_btn.click(
            fn=load_ranking_data, inputs=[], outputs=[ranking_table, division_plot]
        )

    return {"refresh_ranking_btn": refresh_ranking_btn}
