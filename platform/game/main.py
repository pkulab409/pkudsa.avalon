"""
阿瓦隆游戏 - 主程序入口
"""
import os
import sys
import argparse
from typing import Dict, Any, List

from battle_manager import BattleManager
from player_loader import load_baseline_code

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="阿瓦隆游戏系统")
    parser.add_argument("--mode", choices=["basic", "smart", "mixed"], default="smart",
                        help="游戏模式: basic(基础AI), smart(智能AI), mixed(混合)")
    parser.add_argument("--games", type=int, default=1, help="运行的游戏数量")
    parser.add_argument("--data-dir", default="./data", help="数据存储目录")
    return parser.parse_args()

def setup_environment(args):
    """设置环境变量"""
    os.environ["AVALON_DATA_DIR"] = args.data_dir
    # 确保数据目录存在
    os.makedirs(args.data_dir, exist_ok=True)
    print(f"数据将存储在: {args.data_dir}")

def create_player_codes(mode: str) -> Dict[int, str]:
    """创建玩家代码"""
    player_codes = {}
    
    if mode == "basic":
        # 所有玩家使用基础AI
        basic_code = load_baseline_code("basic_player")
        for i in range(1, 8):
            player_codes[i] = basic_code
            
    elif mode == "smart":
        # 所有玩家使用智能AI
        smart_code = load_baseline_code("smart_player")
        for i in range(1, 8):
            player_codes[i] = smart_code
            
    elif mode == "mixed":
        # 混合模式：一半基础AI，一半智能AI
        basic_code = load_baseline_code("basic_player")
        smart_code = load_baseline_code("smart_player")
        for i in range(1, 8):
            player_codes[i] = smart_code if i <= 4 else basic_code
    
    return player_codes

def run_games(args):
    """运行游戏"""
    # 初始化对战管理器
    battle_manager = BattleManager()
    
    # 游戏结果统计
    results = {"blue_wins": 0, "red_wins": 0, "errors": 0}
    battle_ids = []
    
    print(f"开始运行 {args.games} 场游戏，模式: {args.mode}")
    
    # 创建并启动所有游戏
    for i in range(args.games):
        player_codes = create_player_codes(args.mode)
        battle_id = battle_manager.create_battle(player_codes)
        battle_ids.append(battle_id)
        print(f"游戏 {i+1}/{args.games} 已启动，ID: {battle_id}")
    
    # 等待所有游戏完成
    for i, battle_id in enumerate(battle_ids):
        print(f"等待游戏 {i+1}/{args.games} (ID: {battle_id}) 完成...")
        
        # 简单轮询等待游戏完成
        while True:
            status = battle_manager.get_battle_status(battle_id)
            if status in ["completed", "error"]:
                break
            import time
            time.sleep(0.5)
        
        # 获取游戏结果
        result = battle_manager.get_battle_result(battle_id)
        
        if "error" in result:
            print(f"游戏 {i+1} 发生错误: {result['error']}")
            results["errors"] += 1
        else:
            winner = result["winner"]
            print(f"游戏 {i+1} 结果: {winner}方获胜")
            
            if winner == "blue":
                results["blue_wins"] += 1
            else:
                results["red_wins"] += 1
            
            # 打印详细信息
            print(f"  - 蓝队胜利: {result['blue_wins']} 轮")
            print(f"  - 红队胜利: {result['red_wins']} 轮")
            print(f"  - 角色分配: {result['roles']}")
            print(f"  - 总共进行: {result['rounds_played']} 轮")
    
    # 打印总结
    print("\n=== 游戏结果总结 ===")
    print(f"总场次: {args.games}")
    print(f"蓝队获胜: {results['blue_wins']} ({results['blue_wins']/args.games*100:.1f}%)")
    print(f"红队获胜: {results['red_wins']} ({results['red_wins']/args.games*100:.1f}%)")
    print(f"错误场次: {results['errors']}")

def main():
    """主函数"""
    # 解析命令行参数
    args = parse_arguments()
    
    # 设置环境
    setup_environment(args)
    
    # 运行游戏
    run_games(args)

if __name__ == "__main__":
    main()