"""
游戏辅助模块 - 提供辅助功能供玩家代码使用
"""

import os
import json
import time
import logging
import threading
from typing import Dict, Any, List, Tuple, Optional, Callable

# 导入LLM相关的类和接口
from .llm_config import LLMInstanceConfig
from .llm_adapters import BaseLLMAdapter, LLMAdapterFactory, LLMProviderResponse

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("GameHelper")

# LLM相关配置
_INIT_SYSTRM_PROMPT = """
你是一个专业助理。
"""  # 后期可修改
_MAX_CALL_COUNT_PER_ROUND = 3  # 一轮最多调用 LLM 次数

# 初始用户库JSON
INIT_PRIVA_LOG_DICT = {
    "logs": [],
    "llm_history": [{"role": "system", "content": _INIT_SYSTRM_PROMPT}],
    "llm_call_counts": [
        0 for _ in range(6)
    ],  # 第 0~5 轮分别用了几次 (Note: array size 6 for rounds 0-5)
}


class GameHelper:
    """游戏辅助类，管理LLM调用和日志功能"""

    def __init__(
        self,
        data_dir=None,
        llm_config: Optional[LLMInstanceConfig] = None,
        referee_llm_submit_task_method: Optional[Callable] = None,
    ):
        self.current_player_id = None
        self.game_session_id = None
        self.data_dir = data_dir or os.environ.get("AVALON_DATA_DIR", "./data")
        self.current_round = 0  # Default to 0, will be set by referee
        self.call_count_added = 0
        self.tokens = [{"input": 0, "output": 0} for _ in range(7)]

        # LLM相关配置
        if llm_config is None:
            logger.warning(
                "LLMInstanceConfig not provided to GameHelper. LLM calls may fail or use incomplete defaults."
            )
            # Attempting to create a very basic default, but API key/base_url will be missing
            # It's better if llm_config is always provided by the caller (e.g., Referee)
            default_model_name = os.environ.get(
                "OPENAI_MODEL_NAME",
                "default-model",  # Avoid hardcoding specific model names here
            )
            default_provider = "openai"
            self.llm_config = LLMInstanceConfig(
                provider=default_provider, model_name=default_model_name
            )
        else:
            self.llm_config = llm_config

        self.submit_task_to_referee = referee_llm_submit_task_method

        # 创建LLM适配器
        try:
            if self.llm_config:  # Ensure llm_config is not None
                self.llm_adapter = LLMAdapterFactory.create_adapter(self.llm_config)
                if self.llm_adapter:
                    logger.info(
                        f"成功创建LLM适配器: {self.llm_adapter.__class__.__name__}"
                    )
                else:
                    logger.error(
                        f"创建LLM适配器失败，提供者可能不受支持: {self.llm_config.provider}"
                    )
                    self.llm_adapter = None  # Explicitly set to None
            else:  # Should not happen if llm_config is always provided
                logger.error("无法创建LLM适配器，因为llm_config为空")
                self.llm_adapter = None

        except Exception as e:
            logger.error(f"创建LLM适配器时出错: {str(e)}")
            self.llm_adapter = None

        # 初始化线程本地存储
        self._initialize_thread_local_data()

        # LLM调用完整日志
        self.llm_full_log = []

    def _initialize_thread_local_data(self):
        """初始化线程本地数据"""
        self.thread_local_data = threading.local()
        self.thread_local_data.llm_history = [
            {"role": "system", "content": _INIT_SYSTRM_PROMPT}
        ]
        self.thread_local_data.llm_call_counts = [
            0 for _ in range(6)
        ]  # 第 0~5 轮分别用了几次
        self.thread_local_data.llm_full_log = []

    def set_current_context(self, player_id: int, game_id: str) -> None:
        """
        设置当前上下文 - 这个函数由 referee 在调用玩家代码前设置

        参数:
            player_id: 当前玩家 ID
            game_id: 当前游戏会话 ID
        """
        self.current_player_id = player_id
        self.game_session_id = game_id

    def reset_llm_limit(self, round_: int) -> None:
        """
        公投未通过，重置本轮llm调用限制
        """
        # 获取日志
        existing_data = self._get_private_lib_content()
        # 获取LLM调用次数记录 - 使用传入的round_参数
        player_call_counts = existing_data["llm_call_counts"][round_]
        # 同时更新当前轮次，确保一致性
        self.current_round = round_
        self.call_count_added += player_call_counts

        # 更新线程本地数据
        if hasattr(self, "thread_local_data"):
            self.thread_local_data.llm_call_counts[round_] = 0

    def set_current_round(self, round_: int) -> None:
        """
        设置当前 ROUND 上下文 - 这个函数由 referee 在更改 ROUND 时设置

        参数:
            round_: 当前游戏运行到第几轮
        """
        self.current_round = round_
        # 重置本轮追加llm调用次数
        self.call_count_added = 0

    def _check_llm_limits(self) -> Tuple[bool, str]:
        """
        检查LLM调用是否超出限制

        返回:
            (成功标志, 错误消息)
        """
        if not self.current_player_id or not self.game_session_id:
            return False, "LLM调用错误：未设置玩家或游戏上下文"

        if self.current_round is None:
            return False, "LLM调用错误：未设置当前轮次"

        # 获取当前轮次的调用次数
        if not hasattr(self, "thread_local_data"):
            self._initialize_thread_local_data()

        # 检查本轮调用次数是否已达上限
        current_calls = self.thread_local_data.llm_call_counts[self.current_round]
        max_calls = _MAX_CALL_COUNT_PER_ROUND + self.call_count_added

        if current_calls >= max_calls:
            error_msg = f"本轮LLM调用次数已达上限({max_calls}次)"
            logger.warning(
                f"玩家{self.current_player_id}在第{self.current_round}轮: {error_msg}"
            )
            return False, error_msg

        return True, ""

    def askLLM(self, prompt: str, temperature_override: Optional[float] = None) -> str:
        """
        向大语言模型发送提示并获取回答

        参数:
            prompt: 发送给LLM的提示文本
            temperature_override: 可选的温度参数覆盖值 (used by system/referee, not directly by player's askLLM)

        返回:
            LLM的回答文本, 或在错误时返回描述性错误信息
        """
        # 检查LLM适配器是否可用
        if not self.llm_adapter:
            error_msg = "LLM适配器未初始化或初始化失败"
            logger.error(error_msg)
            return f"LLM调用错误: {error_msg}"

        # 检查是否设置了任务提交方法
        if not self.submit_task_to_referee:
            error_msg = "未设置任务提交方法 (referee_llm_submit_task_method)"
            logger.error(error_msg)
            return f"LLM调用错误: {error_msg}"

        # 检查调用限制
        can_proceed, error_message = self._check_llm_limits()
        if not can_proceed:
            return f"LLM调用错误: {error_message}"

        # 准备日志条目
        request_time = time.time()
        # Ensure self.llm_config exists before accessing attributes
        current_temperature = 1.0  # Fallback, though _TEMPERATURE is now removed. Better: self.llm_config.temperature if self.llm_config else 1.0
        if self.llm_config:
            current_temperature = self.llm_config.temperature

        request_log_entry = {
            "timestamp": request_time,
            "player_id": self.current_player_id,
            "round": self.current_round,
            "prompt": prompt,
            "temperature": (
                temperature_override
                if temperature_override is not None
                else current_temperature
            ),
        }

        try:
            # 记录线程本地历史
            if not hasattr(self, "thread_local_data"):
                self._initialize_thread_local_data()  # Should have been called in __init__

            # 创建当前调用的消息列表
            current_messages_for_call = self.thread_local_data.llm_history.copy()
            current_messages_for_call.append({"role": "user", "content": prompt})

            # 调用referee提供的任务提交方法
            start_time = time.time()
            # The response_obj is expected to be LLMProviderResponse or a similar structure
            # with attributes: success, content, usage, finish_reason
            response_obj = self.submit_task_to_referee(
                current_messages_for_call, temperature_override
            )
            call_duration = time.time() - start_time

            # Ensure response_obj has expected attributes
            if not hasattr(response_obj, "success") or not hasattr(
                response_obj, "content"
            ):
                error_msg = "LLM响应对象格式不正确"
                logger.error(f"{error_msg} from submit_task_to_referee")
                request_log_entry.update(
                    {"success": False, "error": error_msg, "duration": call_duration}
                )
                self.llm_full_log.append(request_log_entry)
                return f"LLM调用错误: {error_msg}"

            # 处理响应
            if not response_obj.success:
                error_msg = f"LLM调用失败: {response_obj.content}"
                logger.error(error_msg)

                request_log_entry.update(
                    {
                        "success": False,
                        "error": error_msg,
                        "duration": call_duration,
                        "finish_reason": getattr(response_obj, "finish_reason", None),
                    }
                )
                self.llm_full_log.append(request_log_entry)
                return error_msg

            reply = response_obj.content
            usage_data = getattr(
                response_obj, "usage", {"prompt_tokens": 0, "completion_tokens": 0}
            )

            self._update_history_and_tokens(prompt, reply, usage_data)

            request_log_entry.update(
                {
                    "success": True,
                    "reply": reply,
                    "duration": call_duration,
                    "tokens": usage_data,
                    "finish_reason": getattr(response_obj, "finish_reason", None),
                }
            )
            self.llm_full_log.append(request_log_entry)
            return reply

        except Exception as e:
            error_msg = f"LLM调用时发生异常: {str(e)}"
            logger.error(error_msg, exc_info=True)

            # 更新日志
            request_log_entry.update(
                {
                    "success": False,
                    "error": error_msg,
                    "duration": time.time() - request_time,
                }
            )
            self.llm_full_log.append(request_log_entry)

            return f"LLM调用错误: {str(e)}"

    def _update_history_and_tokens(
        self, prompt: str, reply: str, usage: Dict[str, int]
    ):
        """
        更新对话历史和token计数

        参数:
            prompt: 用户提示
            reply: LLM回复
            usage: token使用情况
        """
        # 更新对话历史
        self.thread_local_data.llm_history.append({"role": "user", "content": prompt})
        self.thread_local_data.llm_history.append(
            {"role": "assistant", "content": reply}
        )

        # 更新调用计数
        self.thread_local_data.llm_call_counts[self.current_round] += 1

        # 更新token统计
        if self.current_player_id and 1 <= self.current_player_id <= len(self.tokens):
            if "prompt_tokens" in usage:
                self.tokens[self.current_player_id - 1]["input"] += usage[
                    "prompt_tokens"
                ]
            if "completion_tokens" in usage:
                self.tokens[self.current_player_id - 1]["output"] += usage[
                    "completion_tokens"
                ]

        # 将更新写入私有库
        try:
            existing_data = self._get_private_lib_content()
            existing_data["llm_history"] = self.thread_local_data.llm_history.copy()
            existing_data["llm_call_counts"] = (
                self.thread_local_data.llm_call_counts.copy()
            )
            self._write_back_private(data=existing_data)
        except Exception as e:
            logger.error(f"更新私有库时出错: {str(e)}")

    def _get_private_lib_content(self) -> dict:
        """
        获取私有库内容

        该函数用于构建私有数据文件路径，并读取现有数据。
        如果文件不存在或无法解析，将返回默认数据结构。

        返回:
            dict: 包含现有数据或默认数据结构的字典。
        """
        # 构建私有数据文件路径
        private_file = os.path.join(
            self.data_dir,
            f"game_{self.game_session_id}_player_{self.current_player_id}_private.json",
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

    def _write_back_private(self, data: dict) -> None:
        """统一处理：写回私有库 JSON 文件"""
        # 构建私有数据文件路径
        private_file = os.path.join(
            self.data_dir,
            f"game_{self.game_session_id}_player_{self.current_player_id}_private.json",
        )

        # 确保目录存在
        os.makedirs(os.path.dirname(private_file), exist_ok=True)

        # 打开文件，写回
        with open(private_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def read_private_lib(self) -> List[str]:
        """从私有库中读取内容"""
        if self.current_player_id is None or not self.game_session_id:
            logger.error("尝试在无玩家ID或游戏ID上下文的情况下读取私有日志")
            return []

        try:
            existing_data = self._get_private_lib_content()  # 获取日志
            return existing_data["logs"]
        except Exception as e:
            logger.error(f"读取私有日志时出错: {str(e)}")
            return []

    def write_into_private(self, content: str) -> None:
        """
        向当前玩家的私有存储中追加写入内容

        参数:
            content: 需要保存的文本内容
        """
        if self.current_player_id is None or not self.game_session_id:
            logger.error("尝试在无玩家ID或游戏ID上下文的情况下写入私有日志")
            return

        try:
            # 获取日志
            existing_data = self._get_private_lib_content()

            # 追加新日志
            existing_data["logs"].append({"timestamp": time.time(), "content": content})

            # 写回文件
            self._write_back_private(data=existing_data)

        except Exception as e:
            logger.error(f"写入私有日志时出错: {str(e)}")

    def read_public_lib(self) -> Dict[str, Any]:
        """
        读取当前游戏的公共历史记录

        返回:
            游戏历史记录字典
        """
        if not self.game_session_id:
            logger.error("尝试在无游戏ID上下文的情况下读取游戏历史")
            return {"error": "未设置游戏上下文", "events": []}

        try:
            public_file = os.path.join(
                self.data_dir, f"game_{self.game_session_id}_public.json"
            )

            if os.path.exists(public_file):
                with open(public_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                return {"error": "找不到游戏历史文件", "events": []}

        except Exception as e:
            logger.error(f"读取游戏历史时出错: {str(e)}")
            return {"error": str(e), "events": []}

    def get_tokens(self) -> List[Dict[str, int]]:
        """获取所有玩家的token使用情况"""
        return self.tokens

    def get_llm_full_log(self) -> List[Dict[str, Any]]:
        """获取完整的LLM调用日志"""
        return self.llm_full_log


_thread_local = threading.local()


def get_current_helper() -> Optional[GameHelper]:  # Added Optional return type
    """获取当前线程的 GameHelper 实例"""
    if not hasattr(_thread_local, "helper"):
        # Avoid creating a default GameHelper here if it's not properly initialized
        # The helper should be set by the referee context
        logger.warning(
            "get_current_helper called before helper was set for this thread."
        )
        return None
    return _thread_local.helper


def set_thread_helper(helper: GameHelper):  # Added type hint
    """设置当前线程的 GameHelper 实例"""
    _thread_local.helper = helper


# 修改为使用线程本地存储的 helper 实例
def set_current_context(player_id: int, game_id: str) -> None:
    helper = get_current_helper()
    if helper:
        helper.set_current_context(player_id, game_id)


def reset_llm_limit(round_: int) -> None:
    helper = get_current_helper()
    if helper:
        helper.reset_llm_limit(round_)


def set_current_round(round_: int) -> None:
    helper = get_current_helper()
    if helper:
        helper.set_current_round(round_)


def askLLM(prompt: str) -> str:
    helper = get_current_helper()
    if helper:
        # Player-facing askLLM does not pass temperature_override
        return helper.askLLM(prompt)
    return "LLM调用错误: GameHelper未初始化"


def read_private_lib() -> List[str]:
    helper = get_current_helper()
    if helper:
        return helper.read_private_lib()
    return []


def write_into_private(content: str) -> None:
    helper = get_current_helper()
    if helper:
        helper.write_into_private(content)


def read_public_lib() -> Dict[str, Any]:
    helper = get_current_helper()
    if helper:
        return helper.read_public_lib()
    return {"error": "GameHelper未初始化", "events": []}
