"""
游戏辅助模块 - 提供辅助功能供玩家代码使用
"""

import os
import json
import time
import logging
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv
from openai import OpenAI


# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("GameHelper")


# 为LLM的API自动加载.env文件
if not load_dotenv("LLM.env"):
    logger.error(f"Error when loading environment variables from `LLM.env`.")
    # 这里只要有一个环境变量被读取成功就不会报错
# 在和avalon_game_helper相同目录下创建一个`LLM.env`，包含三行：
# OPENAI_API_KEY={API_KEY}（需要填入）
# OPENAI_BASE_URL=https://chat.noc.pku.edu.cn/v1
# OPENAI_MODEL_NAME=deepseek-v3-250324-64k-local


# openai初始配置
try:
    client = OpenAI()  # 自动读取（来自load_dotenv的）环境变量
    models = client.models.list()
    # 不出意外的话这里有三个模型：
    #   - deepseek-v3-250324
    #   - deepseek-v3-250324-64k-local
    #   - deepseek-r1-64k-local
except Exception as e:
    logger.error(f"Error when initializing LLM MODEL - {e}")
else:
    logger.info(f"Successfully imported LLM MODELs - {models}")


# 全局上下文变量
_CURRENT_PLAYER_ID = None  # 当前玩家ID
_GAME_SESSION_ID = None  # 当前游戏会话ID
_DATA_DIR = os.environ.get("AVALON_DATA_DIR", "./data")


# LLM相关配置
_USE_STREAM = False  # 使用流式
_INIT_SYSTRM_PROMPT = """
你是一个专业助理。
"""  # 后期可修改
_TEMPERATURE = 1  # 创造性 (0-2, 默认1)
_MAX_TOKENS = 500  # 最大生成长度
_TOP_P = 0.9  # 输出多样性控制
_PRESENCE_PENALTY = 0.5  # 避免重复话题 (-2~2)
_FREQUENCY_PENALTY = 0.5  # 避免重复用词 (-2~2)


# 初始用户库JSON
INIT_PRIVA_LOG_DICT = {
    "logs": [],
    "llm_history": [{"role": "system", "content": _INIT_SYSTRM_PROMPT}],
}


def set_current_context(player_id: int, game_id: str) -> None:
    """
    设置当前上下文 - 这个函数由 referee 在调用玩家代码前设置

    参数:
        player_id: 当前玩家 ID
        game_id: 当前游戏会话 ID
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

    # 获取日志
    existing_data = _get_private_lib_content()
    # 获取LLM聊天记录
    _player_chat_history = existing_data["llm_history"]

    # 调LLM
    try:
        reply = _fetch_LLM_reply(_player_chat_history, prompt)
    except Exception as e:
        return f"LLM调用错误: {str(e)}"

    # 追加新日志
    try:
        existing_data["llm_history"].append({"role": "user", "content": prompt})
        existing_data["llm_history"].append({"role": "assistant", "content": reply})
    except Exception as e:
        return f"LLM聊天记录保存错误: {str(e)}"

    # 写回私有库文件
    _write_back_private(data=existing_data)

    return reply


def _fetch_LLM_reply(history, cur_prompt) -> str:
    """
    从历史记录和当前提示中获取LLM回复。

    参数:
        history (list): 包含先前对话的消息列表。
        cur_prompt (str): 当前用户输入的提示。

    返回:
        Tuple[bool, str]: 返回一个元组，第一个元素是布尔值，表示操作是否成功；
                          第二个元素是字符串，包含LLM的回复内容。
    """
    model_name = os.environ.get("OPENAI_MODEL_NAME", None)
    completion = client.chat.completions.create(
        model=model_name,
        messages=history + [{"role": "user", "content": cur_prompt}],
        stream=_USE_STREAM,
        temperature=_TEMPERATURE,
        max_tokens=_MAX_TOKENS,
        top_p=_TOP_P,
        presence_penalty=_PRESENCE_PENALTY,
        frequency_penalty=_FREQUENCY_PENALTY,
    )

    return completion.choices[0].message.content


def _get_private_lib_content() -> dict:
    """
    获取私有库内容

    该函数用于构建私有数据文件路径，并读取现有数据。
    如果文件不存在或无法解析，将返回默认数据结构。

    返回:
        dict: 包含现有数据或默认数据结构的字典。
    """
    # 构建私有数据文件路径
    private_file = os.path.join(
        _DATA_DIR, f"game_{_GAME_SESSION_ID}_player_{_CURRENT_PLAYER_ID}_private.json"
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
            existing_data = INIT_PRIVA_LOG_DICT
    else:
        existing_data = INIT_PRIVA_LOG_DICT

    return existing_data


def _write_back_private(data: dict) -> None:
    # 构建私有数据文件路径
    private_file = os.path.join(
        _DATA_DIR, f"game_{_GAME_SESSION_ID}_player_{_CURRENT_PLAYER_ID}_private.json"
    )

    # 确保目录存在
    os.makedirs(os.path.dirname(private_file), exist_ok=True)

    # 打开文件，写回
    with open(private_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def read_private_lib() -> List[str]:
    """从私有库中读取内容"""
    if _CURRENT_PLAYER_ID is None or not _GAME_SESSION_ID:
        logger.error("尝试在无玩家ID或游戏ID上下文的情况下读取私有日志")
        return

    try:
        existing_data = _get_private_lib_content()  # 获取日志

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
        # 获取日志
        existing_data = _get_private_lib_content()

        # 追加新日志
        existing_data["logs"].append({"timestamp": time.time(), "content": content})

        # 写回文件
        _write_back_private(data=existing_data)

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
        public_file = os.path.join(_DATA_DIR, f"game_{_GAME_SESSION_ID}_public.json")

        if os.path.exists(public_file):
            with open(public_file, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            return {"error": "找不到游戏历史文件", "events": []}

    except Exception as e:
        logger.error(f"读取游戏历史时出错: {str(e)}")
        return {"error": str(e), "events": []}


if __name__ == "__main__":
    print(
        _fetch_LLM_reply(  # 测试LLM
            history=[{"role": "system", "content": "你是一个专业助理"}],
            cur_prompt="L3自动驾驶自行车",
        )
    )
