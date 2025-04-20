import json
import os
import requests
from typing import List, Dict, Any, Optional
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("avalon_helper")

# 全局变量
_CURRENT_PLAYER_ID = None  # 当前玩家ID
_GAME_SESSION_ID = None   # 当前游戏会话ID
_LLM_API_ENDPOINT = os.environ.get("LLM_API_ENDPOINT", "http://localhost:8000/api/v1/generate")
_LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
_DATA_DIR = os.environ.get("AVALON_DATA_DIR", "./data")

# 设置当前玩家ID（由游戏服务器调用）
def set_current_context(player_id: int, game_id: str) -> None:
    """
    设置当前上下文 - 这个函数由游戏服务器在调用玩家代码前设置
    
    参数:
        player_id (int): 当前玩家ID
        game_id (str): 当前游戏会话ID
    """
    global _CURRENT_PLAYER_ID, _GAME_SESSION_ID
    _CURRENT_PLAYER_ID = player_id
    _GAME_SESSION_ID = game_id
    logger.info(f"Context set: Player {player_id}, Game {game_id}")

def askLLM(prompt: str) -> str:
    """
    向大语言模型发送提示并获取回答
    
    参数:
        prompt (str): 发送给LLM的提示文本
        
    返回:
        str: LLM的回答文本
    """
    try:
        # 构建API请求
        headers = {
            "Content-Type": "application/json"
        }
        if _LLM_API_KEY:
            headers["Authorization"] = f"Bearer {_LLM_API_KEY}"
            
        payload = {
            "prompt": prompt,
            "max_tokens": 1000,
            "temperature": 0.7,
            "player_id": _CURRENT_PLAYER_ID,
            "game_id": _GAME_SESSION_ID
        }
        
        # 记录请求（但不记录完整prompt以节省空间）
        logger.info(f"LLM Request: {prompt[:50]}... (Player {_CURRENT_PLAYER_ID})")
        
        # 发送请求
        response = requests.post(_LLM_API_ENDPOINT, headers=headers, json=payload, timeout=30)
        
        # 检查响应
        if response.status_code == 200:
            result = response.json()
            answer = result.get("text", "")
            logger.info(f"LLM Response: {answer[:50]}...")
            return answer
        else:
            logger.error(f"LLM API Error: {response.status_code} - {response.text}")
            return f"API调用失败 (状态码: {response.status_code})"
            
    except Exception as e:
        logger.exception(f"LLM调用异常: {str(e)}")
        return f"LLM调用出现异常: {str(e)}"

def read_public_lib() -> List[Dict[str, Any]]:
    """
    读取所有玩家可见的公共对局记录库
    
    返回:
        list[dict]: 包含所有公共对局记录的字典列表
    """
    try:
        # 构建公共记录文件路径
        public_file = os.path.join(_DATA_DIR, f"game_{_GAME_SESSION_ID}_public.json")
        
        # 检查文件是否存在
        if not os.path.exists(public_file):
            logger.warning(f"公共记录文件不存在: {public_file}")
            return []
            
        # 读取并解析JSON文件
        with open(public_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        logger.info(f"已读取公共记录 (Player {_CURRENT_PLAYER_ID})")
        return data
        
    except json.JSONDecodeError as e:
        logger.error(f"公共记录JSON解析错误: {str(e)}")
        return []
    except Exception as e:
        logger.exception(f"读取公共记录异常: {str(e)}")
        return []

def read_private_lib() -> Dict[str, Any]:
    """
    读取仅对当前玩家可见的私有存储数据
    
    返回:
        dict: 私有存储的完整内容
    """
    try:
        # 确保已设置当前玩家
        if _CURRENT_PLAYER_ID is None:
            logger.error("未设置当前玩家ID")
            return {}
            
        # 构建私有数据文件路径
        private_file = os.path.join(_DATA_DIR, f"game_{_GAME_SESSION_ID}_player_{_CURRENT_PLAYER_ID}_private.json")
        
        # 检查文件是否存在
        if not os.path.exists(private_file):
            logger.warning(f"私有数据文件不存在，将创建新文件: {private_file}")
            return {}
            
        # 读取并解析JSON文件
        with open(private_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        logger.info(f"已读取私有数据 (Player {_CURRENT_PLAYER_ID})")
        return data
        
    except json.JSONDecodeError as e:
        logger.error(f"私有数据JSON解析错误: {str(e)}")
        return {}
    except Exception as e:
        logger.exception(f"读取私有数据异常: {str(e)}")
        return {}

def write_into_private(content: str) -> None:
    """
    向当前玩家的私有存储中追加写入内容
    
    参数:
        content (str): 需要保存的文本内容（建议使用JSON格式）
    """
    try:
        # 确保已设置当前玩家
        if _CURRENT_PLAYER_ID is None:
            logger.error("未设置当前玩家ID")
            return
            
        # 构建私有数据文件路径
        private_file = os.path.join(_DATA_DIR, f"game_{_GAME_SESSION_ID}_player_{_CURRENT_PLAYER_ID}_private.json")
        
        # 读取现有数据
        existing_data = {}
        if os.path.exists(private_file):
            try:
                with open(private_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except json.JSONDecodeError:
                logger.warning("现有私有数据解析错误，将重置")
                existing_data = {}
                
        # 确保目录存在
        os.makedirs(os.path.dirname(private_file), exist_ok=True)
        
        # 追加新内容
        timestamp = import_time_module().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {content}"
        
        # 如果私有数据中没有logs字段，创建一个
        if "logs" not in existing_data:
            existing_data["logs"] = []
            
        # 添加新日志
        existing_data["logs"].append(log_entry)
        
        # 保存更新后的数据
        with open(private_file, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
            
        logger.info(f"已写入私有数据 (Player {_CURRENT_PLAYER_ID}): {content[:50]}...")
        
    except Exception as e:
        logger.exception(f"写入私有数据异常: {str(e)}")

# 辅助函数 - 导入time模块
def import_time_module():
    """安全导入time模块"""
    import time
    from datetime import datetime
    return datetime.now