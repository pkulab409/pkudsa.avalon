"""
玩家代码加载模块 - 负责动态加载和执行玩家代码
"""
import os
import sys
import time
import logging
import importlib.util
import traceback
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from typing import Dict, Any, Optional, Tuple

# 配置日志
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PlayerLoader")

def execute_player_code(code_content: str, player_id: int) -> Tuple[Any, str, str]:
    """
    安全执行玩家代码并返回Player实例
    
    参数:
        code_content: 玩家代码内容
        player_id: 玩家ID
        
    返回:
        (player_instance, stdout, stderr) 元组或 (error_message, stdout, stderr) 元组
    """
    try:
        # 创建模块
        module_name = f"player_module_{player_id}_{int(time.time()*1000)}"
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        
        # 重定向标准输出和错误
        stdout = StringIO()
        stderr = StringIO()
        
        with redirect_stdout(stdout), redirect_stderr(stderr):
            # 执行代码
            exec(code_content, module.__dict__)
            
            # 检查Player类
            if hasattr(module, "Player"):
                player_instance = module.Player()
                return player_instance, stdout.getvalue(), stderr.getvalue()
            else:
                return f"错误: Player类未找到", stdout.getvalue(), stderr.getvalue()
    
    except Exception as e:
        error_msg = traceback.format_exc()
        logger.error(f"执行玩家 {player_id} 代码时出错: {error_msg}")
        return f"错误: {str(e)[:100]}", stdout.getvalue() if 'stdout' in locals() else "", stderr.getvalue() if 'stderr' in locals() else ""

def load_baseline_code(baseline_name: str) -> Optional[str]:
    """
    加载基准玩家代码
    
    参数:
        baseline_name: 基准代码名称，如'basic_player'或'smart_player'
        
    返回:
        基准代码的字符串内容，加载失败时返回None
    """
    try:
        # 构建文件路径，首先尝试相对路径
        file_path = f"{baseline_name}.py"
        
        # 如果相对路径不存在，尝试其他可能的路径
        if not os.path.exists(file_path):
            # 尝试在当前脚本目录下查找
            current_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(current_dir, f"{baseline_name}.py")
            
            # 如果仍然不存在，尝试在上级目录查找
            if not os.path.exists(file_path):
                parent_dir = os.path.dirname(current_dir)
                file_path = os.path.join(parent_dir, f"{baseline_name}.py")
        
        # 读取文件内容
        with open(file_path, "r", encoding="utf-8") as f:
            code_content = f.read()
            
        logger.info(f"成功加载基准代码: {baseline_name}, 路径: {file_path}")
        return code_content
        
    except Exception as e:
        logger.error(f"加载基准代码 {baseline_name} 失败: {str(e)}")
        return None