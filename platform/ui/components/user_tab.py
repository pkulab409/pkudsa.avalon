import gradio as gr
import logging
import matplotlib.pyplot as plt


# 接收 username_state
def create_user_tab(username_state):
    """创建用户中心Tab界面"""
    from services.user_service import get_user_profile

    # 修改函数签名，接收用户名
    def load_user_profile(current_username):
        """加载用户个人资料"""
        # 直接使用传入的用户名
        if not current_username or current_username == "未登录":
            return (
                "Not Logged In",
                "N/A",
                "N/A",
                "Please log in to view your profile.",
                None,
            )

        # 获取用户资料
        user_profile = get_user_profile(current_username)
        if not user_profile:
            return (
                current_username,
                "Data Load Failed",
                "Data Load Failed",
                "Could not load profile data.",
                None,
            )

        # 用户积分和分区
        ladder_points = user_profile.get("ladder_points", 1000)
        # 保持内部逻辑使用中文分区名，但显示时用英文
        division_internal = user_profile.get("division", "新手区")
        division_map_en = {"新手区": "Bronze", "进阶区": "Silver", "大师区": "Gold"}
        division_display_en = division_map_en.get(division_internal, "Unknown")

        # 个人简介 (示例) - 使用英文
        profile_text = f"User {current_username} is currently in {division_display_en} with {ladder_points} points."

        # 创建图表 - 积分信息
        try:
            fig = plt.figure(figsize=(6, 4))
            # 使用英文分区名称
            divisions_en = ["Bronze", "Silver", "Gold"]
            division_thresholds = [0, 1500, 1800, 3000]  # 阈值保持不变

            # 创建积分条形图 - 使用英文标签
            plt.barh(["Points"], [ladder_points], color="skyblue")

            # 添加分区指示线 - 使用英文标签
            for i, threshold in enumerate(division_thresholds[1:-1]):
                plt.axvline(x=threshold, color="red", linestyle="--", alpha=0.7)
                plt.text(
                    threshold + 50, 0, divisions_en[i + 1], verticalalignment="center"
                )  # 使用英文分区名

            plt.xlim(0, division_thresholds[-1])
            # 使用英文标题
            plt.title(f"Current Points: {ladder_points}")
            plt.tight_layout()

            stats_plot = fig
        except Exception as e:
            logging.error(f"Error creating chart: {e}")
            stats_plot = None
            # 如果创建图表失败，关闭可能已创建的 figure
            if "fig" in locals() and fig is not None and plt.fignum_exists(fig.number):
                plt.close(fig)

        return (
            current_username,
            division_display_en,  # 返回英文分区名给 UI
            str(ladder_points),
            profile_text,
            stats_plot,
        )

    with gr.Tab("👤 User Center"):  # Tab 标题保持中文，如果需要也可修改
        with gr.Row():
            with gr.Column(scale=1):
                # 使用英文标签
                gr.Markdown("### 📝 Profile")

                username_display = gr.Textbox(
                    label="Username", value="Loading...", interactive=False
                )

                division_display = gr.Textbox(
                    label="Current Division", value="Loading...", interactive=False
                )

                points_display = gr.Textbox(
                    label="Current Points", value="Loading...", interactive=False
                )

                profile_text = gr.Textbox(
                    label="Profile Bio", value="Loading...", lines=5, interactive=False
                )

                refresh_profile_btn = gr.Button("🔄 Refresh Profile")

            with gr.Column(scale=1):
                # 使用英文标签
                gr.Markdown("### 📊 Statistics")

                stats_plot = gr.Plot(label="Points & Ranking Stats")  # 使用英文标签

        # 事件处理 - 使用 username_state 作为输入
        refresh_profile_btn.click(
            fn=load_user_profile,
            inputs=[username_state],
            outputs=[
                username_display,
                division_display,
                points_display,
                profile_text,
                stats_plot,
            ],
        )

    return {"refresh_profile_btn": refresh_profile_btn}
