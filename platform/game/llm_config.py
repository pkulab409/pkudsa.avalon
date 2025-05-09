from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class LLMInstanceConfig:
    """单个LLM实例的配置封装类"""

    provider: str
    model_name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_output_tokens: int = 500
    timeout: float = 60.0
    custom_params: Dict[str, Any] = field(default_factory=dict)

    def get_api_key(self, app_config=None) -> Optional[str]:
        """
        获取API密钥，优先使用实例自身的设置，然后尝试从全局配置获取

        Args:
            app_config: Flask应用的配置对象

        Returns:
            API密钥或None（如果未找到）
        """
        if self.api_key:
            return self.api_key

        if app_config:
            # 尝试获取特定提供商的API密钥（例如OpenAI的OPENAI_API_KEY）
            provider_key = f"{self.provider.upper()}_API_KEY"
            if provider_key in app_config:
                return app_config[provider_key]

        return None

    def get_base_url(self, app_config=None) -> Optional[str]:
        """
        获取基础URL，优先使用实例自身的设置，然后尝试从全局配置获取

        Args:
            app_config: Flask应用的配置对象

        Returns:
            基础URL或None（如果未找到）
        """
        if self.base_url:
            return self.base_url

        if app_config:
            # 尝试获取特定提供商的基础URL（例如OpenAI的OPENAI_API_BASE）
            provider_base = f"{self.provider.upper()}_API_BASE"
            if provider_base in app_config:
                return app_config[provider_base]

        return None
