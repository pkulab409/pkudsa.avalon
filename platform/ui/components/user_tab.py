import gradio as gr
import logging
import matplotlib.pyplot as plt


def create_user_tab():
    """创建用户中心Tab界面"""
    from services.user_service import get_user_profile

    def load_user_profile(request: gr.Request):
        """加载用户个人资料"""
        username = request.session.get("username")
        if not username:
            return (
                "未登录",  # 用户名
                "N/A",  # 分区
                "N/A",  # 积分
                "请先登录后查看个人资料",  # 个人简介
                None,  # 对战统计图表
            )

        # 获取用户资料
        user_profile = get_user_profile(username)
        if not user_profile:
            return (
                username,
                "数据加载失败",
                "数据加载失败",
                "无法加载个人资料数据",
                None,
            )

        # 用户积分和分区
        ladder_points = user_profile.get("ladder_points", 1000)
        division = user_profile.get("division", "新手区")

        # 个人简介 (示例)
        profile_text = f"用户 {username} 目前在 {division}，积分为 {ladder_points}。"

        # 创建图表 - 积分信息
        try:
            fig = plt.figure(figsize=(6, 4))
            divisions = ["新手区", "进阶区", "大师区"]
            division_thresholds = [0, 1000, 1500, 3000]

            # 创建积分条形图
            plt.barh(["积分"], [ladder_points], color="skyblue")

            # 添加分区指示线
            for i, threshold in enumerate(division_thresholds[1:-1]):
                plt.axvline(x=threshold, color="red", linestyle="--", alpha=0.7)
                plt.text(
                    threshold + 50, 0, divisions[i + 1], verticalalignment="center"
                )

            plt.xlim(0, division_thresholds[-1])
            plt.title(f"当前积分: {ladder_points}")
            plt.tight_layout()

            stats_plot = fig
        except Exception as e:
            logging.error(f"创建图表时出错: {e}")
            stats_plot = None

        return (
            username,
            division,
            str(ladder_points),
            profile_text,
            stats_plot,
        )

    with gr.Tab("👤 用户中心"):
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📝 个人资料")

                username_display = gr.Textbox(
                    label="用户名", value="加载中...", interactive=False
                )

                division_display = gr.Textbox(
                    label="当前分区", value="加载中...", interactive=False
                )

                points_display = gr.Textbox(
                    label="当前积分", value="加载中...", interactive=False
                )

                profile_text = gr.Textbox(
                    label="个人简介", value="加载中...", lines=5, interactive=False
                )

                refresh_profile_btn = gr.Button("🔄 刷新个人资料")

            with gr.Column(scale=1):
                gr.Markdown("### 📊 对战统计")

                stats_plot = gr.Plot(label="积分与排名统计")

        # 事件处理
        refresh_profile_btn.click(
            fn=load_user_profile,
            inputs=[],
            outputs=[
                username_display,
                division_display,
                points_display,
                profile_text,
                stats_plot,
            ],
        )

    return {"refresh_profile_btn": refresh_profile_btn}
