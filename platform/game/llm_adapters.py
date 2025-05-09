import requests
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from .llm_config import LLMInstanceConfig


class LLMProviderResponse:
    """标准化LLM调用的返回结果类"""

    def __init__(
        self,
        text: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        error: Optional[str] = None,
        raw_response: Any = None,
    ):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.error = error
        self.raw_response = raw_response

    @property
    def is_error(self) -> bool:
        """检查响应是否包含错误"""
        return self.error is not None

    @property
    def total_tokens(self) -> int:
        """获取使用的总token数"""
        return self.input_tokens + self.output_tokens


class BaseLLMAdapter(ABC):
    """LLM适配器抽象基类"""

    def __init__(self, config: LLMInstanceConfig, app_config=None, logger=None):
        """
        初始化适配器

        Args:
            config: LLM实例配置
            app_config: 全局应用配置（可选）
            logger: 日志记录器（可选）
        """
        self.config = config
        self.app_config = app_config
        self.logger = logger or logging.getLogger(__name__)
        self.session = requests.Session()

    @abstractmethod
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature_override: Optional[float] = None,
        max_tokens_override: Optional[int] = None,
    ) -> LLMProviderResponse:
        """
        发送聊天完成请求到LLM提供商

        Args:
            messages: 消息列表，每条包含role和content
            temperature_override: 覆盖默认temperature（可选）
            max_tokens_override: 覆盖默认max_tokens（可选）

        Returns:
            LLMProviderResponse对象，包含结果或错误
        """
        pass


class OpenAIAdapter(BaseLLMAdapter):
    """OpenAI API适配器"""

    def __init__(self, config: LLMInstanceConfig, app_config=None, logger=None):
        super().__init__(config, app_config, logger)

        # 获取API密钥和基础URL
        self.api_key = "sk-ChenBin_KnMMX4C9yC64"
        self.base_url = "https://chat.noc.pku.edu.cn/v1"

        # 设置会话头信息
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature_override: Optional[float] = None,
        max_tokens_override: Optional[int] = None,
    ) -> LLMProviderResponse:
        """
        发送聊天完成请求到OpenAI API

        Args:
            messages: 消息列表，每条包含role和content
            temperature_override: 覆盖默认temperature（可选）
            max_tokens_override: 覆盖默认max_tokens（可选）

        Returns:
            LLMProviderResponse对象，包含结果或错误
        """
        # 确定最终参数
        model = "deepseek-v3-250324-64k-local"
        temperature = (
            temperature_override
            if temperature_override is not None
            else self.config.temperature
        )
        max_tokens = (
            max_tokens_override
            if max_tokens_override is not None
            else self.config.max_output_tokens
        )

        # 构建请求载荷
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **self.config.custom_params,
        }

        api_endpoint = f"{self.base_url}/chat/completions"

        try:
            # 发送请求
            response = self.session.post(
                api_endpoint, json=payload, timeout=self.config.timeout
            )
            response.raise_for_status()  # 对HTTP错误码抛出异常

            # 解析响应
            response_data = response.json()

            # 提取完成文本
            if "choices" in response_data and len(response_data["choices"]) > 0:
                completion_text = (
                    response_data["choices"][0].get("message", {}).get("content", "")
                )
            else:
                return LLMProviderResponse(
                    error="OpenAI API响应格式无效", raw_response=response_data
                )

            # 提取token计数
            input_tokens = response_data.get("usage", {}).get("prompt_tokens", 0)
            output_tokens = response_data.get("usage", {}).get("completion_tokens", 0)

            return LLMProviderResponse(
                text=completion_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                raw_response=response_data,
            )

        except requests.exceptions.Timeout:
            error_msg = f"OpenAI API请求在{self.config.timeout}秒后超时"
            self.logger.error(error_msg)
            return LLMProviderResponse(error=error_msg)

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if hasattr(e, "response") else "未知"
            error_content = e.response.text if hasattr(e, "response") else "无详情"
            error_msg = f"OpenAI API返回HTTP错误{status_code}: {error_content}"
            self.logger.error(error_msg)
            return LLMProviderResponse(error=error_msg)

        except Exception as e:
            error_msg = f"调用OpenAI API时出错: {str(e)}"
            self.logger.error(error_msg)
            return LLMProviderResponse(error=error_msg)


class LLMAdapterFactory:
    """根据提供商创建LLM适配器的工厂类"""

    @staticmethod
    def create_adapter(
        config: LLMInstanceConfig, app_config=None, logger=None
    ) -> Optional[BaseLLMAdapter]:
        """
        根据提供商创建适当的LLM适配器

        Args:
            config: LLM实例配置
            app_config: 全局应用配置（可选）
            logger: 日志记录器（可选）

        Returns:
            适当的LLM适配器实例，或None（如果提供商不支持）
        """
        if not logger:
            logger = logging.getLogger(__name__)

        if config.provider.lower() == "openai":
            return OpenAIAdapter(config, app_config, logger)
        else:
            error_msg = f"不支持的LLM提供商: {config.provider}"
            logger.error(error_msg)
            return None
