"""
阿瓦隆游戏 - 主程序入口 (命令行测试用)
"""

import os
import sys
import argparse
from typing import Dict, Any, List
import time
import json  # 导入 json

# 假设 BattleManager 和 Observer 在 game 包下
from game.battle_manager import BattleManager

# from game.player_loader import load_baseline_code # 这个似乎不再需要
from game.observer import Observer

# 假设数据库模型和操作可以导入
# 需要配置 Flask App Context 或独立 SQLAlchemy Session 才能在脚本中使用数据库
# from database import create_battle as db_create_battle, get_ai_code_by_id, get_user_by_id
# from database.models import User, AICode


# 这是一个简化的示例，实际使用需要处理数据库交互和用户/AI选择
def create_dummy_participant_data(num_players=7) -> List[Dict[str, str]]:
    """为测试创建虚拟参与者数据 (需要配合数据库中的实际用户和AI)"""
    # !!! 警告: 这里的 user_id 和 ai_code_id 需要替换为数据库中实际存在的值 !!!
    # 例如，假设存在 user 'testuser1' (ID 'user-uuid-1') 和其 AI 'ai-code-uuid-1'
    # 以及其他6个AI玩家
    participants = []
    # 示例: 第一个玩家是真实用户
    participants.append({"user_id": "user-uuid-1", "ai_code_id": "ai-code-uuid-1"})
    # 示例: 其他玩家是AI (假设存在用户 'ai_user_X' 和他们的激活AI)
    for i in range(2, num_players + 1):
        # 你需要从数据库查询或硬编码有效的 user_id 和 ai_code_id
        participants.append(
            {"user_id": f"ai-user-{i}-uuid", "ai_code_id": f"ai-code-{i}-uuid"}
        )
    print(f"警告: 使用虚拟参与者数据: {participants}")
    print("请确保这些 ID 在数据库中有效!")
    if len(participants) != num_players:
        raise ValueError(f"需要 {num_players} 个参与者数据")
    return participants


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="运行阿瓦隆游戏对战")
    parser.add_argument("-g", "--games", type=int, default=1, help="要运行的游戏场数")
    # 移除 mode 参数，因为玩家选择现在通过 participant_data 处理
    # parser.add_argument(
    #     "-m", "--mode", type=str, default="basic_test", help="游戏模式 (影响AI选择)"
    # )
    # 移除 player_codes 参数，代码路径由 BattleManager 从数据库获取
    # parser.add_argument(
    #     "-p", "--player_codes", type=str, help="包含玩家代码路径的JSON文件"
    # )
    return parser.parse_args()


# setup_environment 函数保持不变
def setup_environment(args):
    """设置环境变量"""
    data_dir = os.environ.get("AVALON_DATA_DIR", "./data")
    os.makedirs(data_dir, exist_ok=True)
    print(f"数据目录: {data_dir}")


# create_player_codes 函数不再需要，由 BattleManager 处理
# def create_player_codes(mode: str, player_codes={}) -> Dict[int, str]:
#     ...


def run_games(args):
    """运行游戏"""
    # 初始化对战管理器
    battle_manager = BattleManager()

    # 游戏结果统计
    results_summary = {"blue_wins": 0, "red_wins": 0, "errors": 0}
    battle_ids = []

    print(f"开始运行 {args.games} 场游戏")

    # 创建并启动所有游戏
    for i in range(args.games):
        print(f"\n--- 准备游戏 {i+1}/{args.games} ---")
        # 1. 创建数据库 Battle 记录 (这里需要数据库操作)
        # !!! 此处需要替换为实际的数据库创建逻辑 !!!
        # participant_data = create_dummy_participant_data()
        # battle = db_create_battle(participant_data, status="waiting")
        # if not battle:
        #     print(f"错误：无法在数据库中创建游戏 {i+1}")
        #     results_summary["errors"] += 1
        #     continue
        # battle_id = battle.id
        # print(f"数据库记录创建成功，Battle ID: {battle_id}")

        # !!! 临时硬编码 Battle ID 和参与者数据用于测试，无数据库交互 !!!
        battle_id = str(uuid.uuid4())  # 仅用于 BattleManager 内部跟踪
        print(f"警告: 未创建数据库记录，使用临时 Battle ID: {battle_id}")
        try:
            participant_data = create_dummy_participant_data()
        except ValueError as e:
            print(f"错误: 无法创建参与者数据: {e}")
            results_summary["errors"] += 1
            continue
        # 模拟数据库状态为 waiting
        battle_manager.battle_status[battle_id] = "waiting"

        # 2. 启动对战线程
        print(f"尝试启动对战 {battle_id}...")
        start_success = battle_manager.start_battle(battle_id, participant_data)

        if start_success:
            print(f"游戏 {i+1}/{args.games} 已启动，ID: {battle_id}")
            battle_ids.append(battle_id)
        else:
            print(f"错误：启动游戏 {i+1} (ID: {battle_id}) 失败")
            results_summary["errors"] += 1
            # 状态可能已在 start_battle 内部被设为 error

    # 等待所有游戏完成
    print("\n--- 等待所有游戏完成 ---")
    for i, battle_id in enumerate(battle_ids):
        print(f"等待游戏 {i+1}/{args.games} (ID: {battle_id}) 完成...")

        # 轮询等待游戏完成
        while True:
            status = battle_manager.get_battle_status(battle_id)
            if status in ["completed", "error"]:
                print(f"游戏 {battle_id} 完成，状态: {status}")
                break
            time.sleep(1)  # 轮询间隔

        # 获取并打印快照 (可选)
        # snapshots_queue = battle_manager.get_snapshots_queue(battle_id)
        # print(f"游戏 {battle_id} 快照:")
        # for snapshot in snapshots_queue:
        #     print(snapshot)

        # 获取游戏结果
        result = battle_manager.get_battle_result(battle_id)
        print(f"游戏 {battle_id} 结果: {result}")

        if result and "error" not in result:
            winner = result.get("winner")  # 假设结果中有 'winner': 'blue' 或 'red'
            if winner == "blue":
                results_summary["blue_wins"] += 1
            elif winner == "red":
                results_summary["red_wins"] += 1
            else:
                print(f"警告: 游戏 {battle_id} 结果中未明确胜者")
                results_summary["errors"] += 1  # 算作错误或未定
        else:
            results_summary["errors"] += 1

    # 打印最终统计
    print("\n--- 所有游戏完成 ---")
    print(f"总场数: {args.games}")
    print(f"蓝方胜利: {results_summary['blue_wins']}")
    print(f"红方胜利: {results_summary['red_wins']}")
    print(f"错误/未定: {results_summary['errors']}")


def main():
    """主函数"""
    args = parse_arguments()
    setup_environment(args)
    run_games(args)


if __name__ == "__main__":
    # 确保 game 包在 Python 路径中
    # sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
