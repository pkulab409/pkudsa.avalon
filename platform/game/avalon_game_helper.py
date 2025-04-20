import json
import os
import requests
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime  # 直接导入 datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("avalon_helper")

# 全局变量
_CURRENT_PLAYER_ID = None  # 当前玩家ID
_GAME_SESSION_ID = None  # 当前游戏会话ID
_LLM_API_ENDPOINT = os.environ.get(
    "LLM_API_ENDPOINT", "http://localhost:8000/api/v1/generate"
)
_LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
_DATA_DIR = os.environ.get("AVALON_DATA_DIR", "./data")

# 新增：LLM 相关配置
_LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", 1000))
_LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", 0.7))
_LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", 30))  # 请求超时时间（秒）


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
    # 移除日志记录，避免重复（set_current_context 通常在 safe_execute 前调用，那里已有日志）
    # logger.info(f"Context set: Player {player_id}, Game {game_id}")


def askLLM(prompt: str) -> str:
    """
    向大语言模型发送提示并获取回答

    参数:
        prompt (str): 发送给LLM的提示文本

    返回:
        str: LLM的回答文本, 或在错误时返回描述性错误信息
    """
    if not _CURRENT_PLAYER_ID or not _GAME_SESSION_ID:
        logger.error(
            "LLM call attempted without context (Player ID or Game ID missing)"
        )
        return "LLM调用错误：未设置玩家或游戏上下文"

    try:
        # 构建API请求
        headers = {"Content-Type": "application/json"}
        if _LLM_API_KEY:
            headers["Authorization"] = f"Bearer {_LLM_API_KEY}"

        payload = {
            "prompt": prompt,
            "max_tokens": _LLM_MAX_TOKENS,  # 使用配置值
            "temperature": _LLM_TEMPERATURE,  # 使用配置值
            "player_id": _CURRENT_PLAYER_ID,
            "game_id": _GAME_SESSION_ID,
        }

        # 记录请求（简略）
        logger.info(
            f"LLM Request (Player {_CURRENT_PLAYER_ID}, Game {_GAME_SESSION_ID}): {prompt[:80]}..."
        )
        # 可以考虑增加更详细的日志级别，例如 DEBUG 级别记录完整 payload
        # logger.debug(f"LLM Request Payload: {json.dumps(payload)}")

        # 发送请求
        response = requests.post(
            _LLM_API_ENDPOINT, headers=headers, json=payload, timeout=_LLM_TIMEOUT
        )  # 使用配置的超时

        # 检查响应
        response.raise_for_status()  # 对 >= 400 的状态码抛出 HTTPError

        result = response.json()
        answer = result.get("text", "")  # 假设LLM API返回格式为 {"text": "..."}
        logger.info(f"LLM Response (Player {_CURRENT_PLAYER_ID}): {answer[:80]}...")
        return answer

    except requests.exceptions.Timeout:
        logger.error(
            f"LLM API Error: Request timed out after {_LLM_TIMEOUT} seconds (Player {_CURRENT_PLAYER_ID})"
        )
        return f"API调用失败：请求超时 ({_LLM_TIMEOUT}秒)"
    except requests.exceptions.RequestException as e:
        # 处理其他 requests 库可能抛出的错误 (连接错误, HTTP错误等)
        status_code = e.response.status_code if e.response is not None else "N/A"
        error_text = e.response.text if e.response is not None else str(e)
        logger.error(
            f"LLM API Error: Status {status_code} - {error_text} (Player {_CURRENT_PLAYER_ID})"
        )
        return f"API调用失败 (状态码: {status_code})"
    except Exception as e:
        logger.exception(f"LLM调用异常 (Player {_CURRENT_PLAYER_ID}): {str(e)}")
        return f"LLM调用出现未知异常: {str(e)}"


def read_public_lib() -> List[Dict[str, Any]]:
    """
    读取所有玩家可见的公共对局记录库

    返回:
        list[dict]: 包含所有公共对局记录的字典列表
    """
    if not _GAME_SESSION_ID:
        logger.error("Attempted to read public lib without Game ID context")
        return []

    try:
        # 构建公共记录文件路径
        public_file = os.path.join(_DATA_DIR, f"game_{_GAME_SESSION_ID}_public.json")

        # 检查文件是否存在
        if not os.path.exists(public_file):
            # logger.warning(f"公共记录文件不存在: {public_file}") # 文件不存在是正常情况，无需警告
            return []

        # 读取并解析JSON文件
        with open(public_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # logger.info(f"已读取公共记录 (Player {_CURRENT_PLAYER_ID})") # 减少日志噪音
        return data

    except json.JSONDecodeError as e:
        logger.error(f"公共记录JSON解析错误: {public_file} - {str(e)}")
        return []
    except Exception as e:
        logger.exception(f"读取公共记录异常: {public_file} - {str(e)}")
        return []


def read_private_lib() -> Dict[str, Any]:
    """
    读取仅对当前玩家可见的私有存储数据

    返回:
        dict: 私有存储的完整内容 (如果文件不存在或无效则返回空字典)
    """
    if _CURRENT_PLAYER_ID is None or not _GAME_SESSION_ID:
        logger.error(
            "Attempted to read private lib without Player ID or Game ID context"
        )
        return {}

    try:
        # 构建私有数据文件路径
        private_file = os.path.join(
            _DATA_DIR,
            f"game_{_GAME_SESSION_ID}_player_{_CURRENT_PLAYER_ID}_private.json",
        )

        # 检查文件是否存在
        if not os.path.exists(private_file):
            # logger.warning(f"私有数据文件不存在，将返回空字典: {private_file}") # 文件不存在是正常情况
            return {}

        # 读取并解析JSON文件
        with open(private_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # logger.info(f"已读取私有数据 (Player {_CURRENT_PLAYER_ID})") # 减少日志噪音
        return data

    except json.JSONDecodeError as e:
        logger.error(f"私有数据JSON解析错误: {private_file} - {str(e)}")
        return {}  # 返回空字典，避免调用方出错
    except Exception as e:
        logger.exception(f"读取私有数据异常: {private_file} - {str(e)}")
        return {}  # 返回空字典


def write_into_private(content: str) -> None:
    """
    向当前玩家的私有存储中追加写入内容 (现在追加到 'logs' 列表)

    参数:
        content (str): 需要保存的文本内容
    """
    if _CURRENT_PLAYER_ID is None or not _GAME_SESSION_ID:
        logger.error(
            "Attempted to write to private lib without Player ID or Game ID context"
        )
        return

    try:
        # 构建私有数据文件路径
        private_file = os.path.join(
            _DATA_DIR,
            f"game_{_GAME_SESSION_ID}_player_{_CURRENT_PLAYER_ID}_private.json",
        )

        # 确保目录存在
        os.makedirs(os.path.dirname(private_file), exist_ok=True)

        # 读取现有数据
        existing_data = {}
        if os.path.exists(private_file):
            try:
                with open(private_file, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, dict):  # 确保读取的是字典
                        logger.warning(
                            f"私有数据文件 {private_file} 格式非字典，将重置。"
                        )
                        existing_data = {}
            except json.JSONDecodeError:
                logger.warning(f"现有私有数据 {private_file} 解析错误，将重置。")
                existing_data = {}

        # 追加新内容到 'logs' 键
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[
            :-3
        ]  # 包含毫秒的时间戳
        log_entry = f"[{timestamp}] {content}"

        if "logs" not in existing_data or not isinstance(
            existing_data.get("logs"), list
        ):
            existing_data["logs"] = []  # 初始化或重置 logs 列表

        existing_data["logs"].append(log_entry)

        # 保存更新后的数据
        with open(private_file, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)

        logger.info(f"已写入私有数据 (Player {_CURRENT_PLAYER_ID}): {content[:80]}...")

    except Exception as e:
        logger.exception(f"写入私有数据异常 (Player {_CURRENT_PLAYER_ID}): {str(e)}")
