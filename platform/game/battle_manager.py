"""
对战管理器 - 单例模式设计的中央控制器
负责创建、管理和监控所有对战
"""
import os
import uuid
import logging
import threading
import time
from typing import Dict, Any, Optional, List, Tuple

# 配置日志
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BattleManager")

class BattleManager:
    """阿瓦隆游戏对战管理器 - 单例模式"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BattleManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        # 初始化对战管理器
        self.battles = {}  # 存储所有对战 {battle_id: battle_thread}
        self.battle_results = {}  # 存储对战结果 {battle_id: result}
        self.battle_status = {}  # 存储对战状态 {battle_id: status}
        self.data_dir = os.environ.get("AVALON_DATA_DIR", "./data")
        
        # 确保数据目录存在
        os.makedirs(self.data_dir, exist_ok=True)
        logger.info(f"对战管理器初始化完成，数据目录：{self.data_dir}")
        self._initialized = True
    
    def create_battle(self, player_codes: Dict[int, str], config: Dict[str, Any] = None) -> str:
        """
        创建新的对战
        
        参数:
            player_codes: 玩家代码字典 {player_id: code_content}
            config: 对战配置参数
            
        返回:
            battle_id: 对战唯一标识符
        """
        # 生成唯一对战ID
        battle_id = str(uuid.uuid4())
        
        # 导入依赖项 - 避免循环导入
        from referee import AvalonReferee
        
        # 创建对战线程
        def battle_thread_func():
            try:
                # 初始化裁判
                referee = AvalonReferee(battle_id, self.data_dir)
                
                # 加载玩家代码
                player_modules = referee._load_codes(player_codes)
                
                # 初始化玩家实例 <--- 添加这一行
                referee.load_player_codes(player_modules) 
                # 开始游戏
                result = referee.run_game()
                
                # 记录结果
                self.battle_results[battle_id] = result
                self.battle_status[battle_id] = "completed"
                logger.info(f"对战 {battle_id} 完成")
                
            except Exception as e:
                logger.error(f"对战 {battle_id} 发生错误: {str(e)}")
                self.battle_status[battle_id] = "error"
                self.battle_results[battle_id] = {"error": str(e)}
        
        # 创建并启动线程
        battle_thread = threading.Thread(target=battle_thread_func)
        self.battles[battle_id] = battle_thread
        self.battle_status[battle_id] = "running"
        battle_thread.start()
        
        logger.info(f"对战 {battle_id} 已创建并启动")
        return battle_id
    
    def get_battle_status(self, battle_id: str) -> Optional[str]:
        """获取对战状态"""
        return self.battle_status.get(battle_id)
    
    def get_battle_result(self, battle_id: str) -> Optional[Dict[str, Any]]:
        """获取对战结果"""
        return self.battle_results.get(battle_id)
    
    def get_all_battles(self) -> List[Tuple[str, str]]:
        """获取所有对战及其状态"""
        return [(bid, self.battle_status.get(bid, "unknown")) for bid in self.battles.keys()]