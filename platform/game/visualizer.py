"""
游戏可视化模块 - 负责将游戏数据可视化展示
"""
import os
import json
import logging
from typing import Dict, Any, List

# 配置日志
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Visualizer")

class GameVisualizer:
    """游戏可视化器"""
    
    def __init__(self, data_dir: str):
        """
        初始化可视化器
        
        参数:
            data_dir: 游戏数据目录
        """
        self.data_dir = data_dir
        logger.info(f"可视化器初始化，数据目录: {data_dir}")
    
    def visualize_game(self, game_id: str):
        """
        可视化单场游戏
        
        参数:
            game_id: 游戏ID
        """
        try:
            # 读取游戏公共日志
            log_file = os.path.join(self.data_dir, f"game_{game_id}_public.json")
            if not os.path.exists(log_file):
                logger.error(f"游戏日志文件不存在: {log_file}")
                return
                
            with open(log_file, "r", encoding="utf-8") as f:
                game_data = json.load(f)
                
            # 打印游戏摘要
            self._print_game_summary(game_data)
            
        except Exception as e:
            logger.error(f"可视化游戏 {game_id} 时出错: {str(e)}")
    
    def _print_game_summary(self, game_data: Dict[str, Any]):
        """打印游戏摘要"""
        events = game_data.get("events", [])
        
        print("\n=== 游戏摘要 ===")
        
        # 找到游戏结束事件
        end_event = None
        for event in events:
            if event.get("type") == "game_end":
                end_event = event
                break
                
        if not end_event:
            print("游戏尚未结束或日志不完整")
            return
            
        # 打印游戏结果
        print(f"获胜方: {end_event.get('winner', '未知')}队")
        print(f"蓝队获胜轮数: {end_event.get('blue_wins', 0)}")
        print(f"红队获胜轮数: {end_event.get('red_wins', 0)}")
        
        # 打印角色分配
        roles = end_event.get("roles", {})
        print("\n角色分配:")
        for player_id, role in roles.items():
            print(f"  玩家 {player_id}: {role}")
        
        # 打印各轮任务结果
        mission_results = []
        for event in events:
            if event.get("type") == "mission_result":
                mission_results.append(event)
                
        print("\n任务结果:")
        for i, result in enumerate(mission_results):
            success = "成功" if result.get("success", False) else "失败"
            fail_count = result.get("fail_count", 0)
            print(f"  任务 {i+1}: {success} (失败票数: {fail_count})")

def visualize_game_console(game_id: str, data_dir: str = "./data"):
    """便捷函数：从控制台可视化游戏"""
    visualizer = GameVisualizer(data_dir)
    visualizer.visualize_game(game_id)

if __name__ == "__main__":
    # 如果直接运行此模块，提供命令行接口
    import argparse
    parser = argparse.ArgumentParser(description="阿瓦隆游戏可视化工具")
    parser.add_argument("game_id", help="要可视化的游戏ID")
    parser.add_argument("--data-dir", default="./data", help="数据目录")
    args = parser.parse_args()
    
    visualize_game_console(args.game_id, args.data_dir)