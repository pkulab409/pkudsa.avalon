"""
游戏辅助模块 - 提供辅助功能供玩家代码使用
"""
import os
import json
import time
import logging
import requests
from typing import Dict, Any, Optional, Set, List

# 配置日志
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GameHelper")

# 全局上下文变量
_CURRENT_PLAYER_ID = None  # 当前玩家ID
_GAME_SESSION_ID = None  # 当前游戏会话ID
_DATA_DIR = os.environ.get("AVALON_DATA_DIR", "./data")

# LLM相关配置
_LLM_API_ENDPOINT = os.environ.get(
    "LLM_API_ENDPOINT", "http://localhost:8000/api/v1/generate")
_LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
_LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", 1000))
_LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", 0.7))
_LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", 30))  # 请求超时时间（秒）


def set_current_context(player_id: int, game_id: str) -> None:
    """
    设置当前上下文 - 这个函数由游戏服务器在调用玩家代码前设置

    参数:
        player_id: 当前玩家ID
        game_id: 当前游戏会话ID
    """
    global _CURRENT_PLAYER_ID, _GAME_SESSION_ID
    _CURRENT_PLAYER_ID = player_id
    _GAME_SESSION_ID = game_id


def askLLM(prompt: str) -> str:
    """
    向大语言模型发送提示并获取回答

    参数:
        prompt: 发送给LLM的提示文本

    返回:
        LLM的回答文本, 或在错误时返回描述性错误信息
    """
    if not _CURRENT_PLAYER_ID or not _GAME_SESSION_ID:
        logger.error("LLM调用缺少上下文（玩家ID或游戏ID缺失）")
        return "LLM调用错误：未设置玩家或游戏上下文"

    try:
        # 构建API请求
        headers = {"Content-Type": "application/json"}
        if _LLM_API_KEY:
            headers["Authorization"] = f"Bearer {_LLM_API_KEY}"

        payload = {
            "prompt": prompt,
            "max_tokens": _LLM_MAX_TOKENS,
            "temperature": _LLM_TEMPERATURE
        }

        # 记录到私有日志
        write_into_private(f"LLM请求: {prompt[:100]}...")

        # 发送请求
        response = requests.post(
            _LLM_API_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=_LLM_TIMEOUT
        )

        # 检查响应
        if response.status_code == 200:
            result = response.json()
            answer = result.get("generated_text", "未找到生成的文本")
            write_into_private(f"LLM回答: {answer[:100]}...")
            return answer
        else:
            error_msg = f"LLM API调用失败，状态码: {response.status_code}"
            write_into_private(error_msg)
            return error_msg

    except Exception as e:
        error_msg = f"LLM调用错误: {str(e)}"
        write_into_private(error_msg)
        return error_msg


def read_private_lib() -> List[str]:
    """从私有库中读取内容"""
    if _CURRENT_PLAYER_ID is None or not _GAME_SESSION_ID:
        logger.error("尝试在无玩家ID或游戏ID上下文的情况下读取私有日志")
        return

    try:
        # 构建私有数据文件路径
        private_file = os.path.join(
            _DATA_DIR,
            f"game_{_GAME_SESSION_ID}_player_{_CURRENT_PLAYER_ID}_private.json"
        )

        # 确保目录存在
        os.makedirs(os.path.dirname(private_file), exist_ok=True)

        # 读取现有数据
        existing_data = {}
        if os.path.exists(private_file):
            try:
                with open(private_file, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except json.JSONDecodeError:
                existing_data = {"logs": []}
        else:
            existing_data = {"logs": []}

        return existing_data["logs"]

    except Exception as e:
        logger.error(f"写入私有日志时出错: {str(e)}")


def write_into_private(content: str) -> None:
    """
    向当前玩家的私有存储中追加写入内容

    参数:
        content: 需要保存的文本内容
    """
    if _CURRENT_PLAYER_ID is None or not _GAME_SESSION_ID:
        logger.error("尝试在无玩家ID或游戏ID上下文的情况下写入私有日志")
        return

    try:
        # 构建私有数据文件路径
        private_file = os.path.join(
            _DATA_DIR,
            f"game_{_GAME_SESSION_ID}_player_{_CURRENT_PLAYER_ID}_private.json"
        )

        # 确保目录存在
        os.makedirs(os.path.dirname(private_file), exist_ok=True)

        # 读取现有数据
        existing_data = {}
        if os.path.exists(private_file):
            try:
                with open(private_file, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except json.JSONDecodeError:
                existing_data = {"logs": []}
        else:
            existing_data = {"logs": []}

        # 追加新日志
        existing_data["logs"].append({
            "timestamp": time.time(),
            "content": content
        })

        # 写回文件
        with open(private_file, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=2)

    except Exception as e:
        logger.error(f"写入私有日志时出错: {str(e)}")


def read_public_lib() -> Dict[str, Any]:
    """
    读取当前游戏的公共历史记录

    返回:
        游戏历史记录字典
    """
    if not _GAME_SESSION_ID:
        logger.error("尝试在无游戏ID上下文的情况下读取游戏历史")
        return {"error": "未设置游戏上下文", "events": []}

    try:
        public_file = os.path.join(
            _DATA_DIR, f"game_{_GAME_SESSION_ID}_public.json")

        if os.path.exists(public_file):
            with open(public_file, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            return {"error": "找不到游戏历史文件", "events": []}

    except Exception as e:
        logger.error(f"读取游戏历史时出错: {str(e)}")
        return {"error": str(e), "events": []}
