# 天梯排名模块
import gradio as gr
import pandas as pd
from data_storage import get_ladder_ranking, get_division_ranking, get_all_divisions


def get_overall_ladder():
    ranking = get_ladder_ranking()

    # 创建排行榜数据
    data = []
    for user in ranking:
        data.append([user["rank"], user["username"], user["ladder_points"]])

    # 如果没有数据，返回空DataFrame
    if not data:
        return pd.DataFrame(columns=["排名", "用户名", "天梯积分"])

    return pd.DataFrame(data, columns=["排名", "用户名", "天梯积分"])


def get_division_ladder(division):
    if not division:
        return pd.DataFrame(columns=["排名", "用户名", "天梯积分"])

    division_ranking = get_division_ranking(division)

    # 创建排行榜数据
    data = []
    for user in division_ranking:
        data.append([user["division_rank"], user["username"], user["ladder_points"]])

    # 如果没有数据，返回空DataFrame
    if not data:
        return pd.DataFrame(columns=["排名", "用户名", "天梯积分"])

    return pd.DataFrame(data, columns=["排名", "用户名", "天梯积分"])


def create_ladder_ranking_tab():
    with gr.Tab("天梯排名"):
        with gr.Row():
            with gr.Column():
                gr.Markdown("### 总天梯榜")
                overall_ladder = gr.DataFrame(
                    headers=["排名", "用户名", "天梯积分"],
                    value=get_overall_ladder(),
                    datatype=["number", "str", "number"],
                )
                refresh_overall_btn = gr.Button("刷新总榜")

                refresh_overall_btn.click(
                    fn=get_overall_ladder, inputs=[], outputs=overall_ladder
                )

        with gr.Row():
            with gr.Column():
                gr.Markdown("### 分区榜")
                all_divisions = get_all_divisions()  # 获取分区列表
                initial_division = (
                    all_divisions[0] if all_divisions else None
                )  # 获取初始值

                division_dropdown = gr.Dropdown(
                    choices=all_divisions,
                    label="选择分区",
                    value=initial_division,  # 在这里设置初始值
                )
                division_ladder = gr.DataFrame(
                    headers=["排名", "用户名", "天梯积分"],
                    datatype=["number", "str", "number"],
                    value=get_division_ladder(
                        initial_division
                    ),  # 同时加载初始值对应的排行榜
                )

                division_dropdown.change(
                    fn=get_division_ladder,
                    inputs=division_dropdown,
                    outputs=division_ladder,
                )
