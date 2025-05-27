"""
AI评论助手模块 - 专门用于生成对局点评
与游戏中的LLM调用分离，不受游戏限制参数影响
"""

import os
import json
import logging
import time
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from openai import OpenAI

# 配置日志
logger = logging.getLogger("AICommentHelper")


class AICommentHelper:
    """AI评论助手类，专门用于生成对局点评"""

    def __init__(self):
        self.client = None
        self.model_name = None
        self._init_client()

    def _init_client(self):
        """初始化OpenAI客户端"""
        try:
            # 1. 首先尝试加载当前目录下的.env文件
            env_path = os.path.join(os.path.dirname(__file__), ".env")
            if os.path.exists(env_path):
                logger.info(f"Loading .env file from: {env_path}")
                load_dotenv(env_path)
            else:
                # 尝试从项目根目录加载
                project_root = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "..")
                )
                env_path = os.path.join(project_root, ".env")
                if os.path.exists(env_path):
                    logger.info(f"Loading .env file from project root: {env_path}")
                    load_dotenv(env_path)
                else:
                    logger.warning(f".env file not found at project root: {env_path}.")
                    # 尝试默认加载（搜索当前工作目录和父目录）
                    if load_dotenv():
                        logger.info(
                            "Successfully loaded .env using default search (CWD or parent dirs)."
                        )
                    else:
                        logger.warning(
                            "Could not find .env file. Will try using system environment variables."
                        )

            # 获取环境变量
            api_key = os.environ.get("OPENAI_API_KEY")
            base_url = os.environ.get("OPENAI_BASE_URL")
            model_name = os.environ.get("OPENAI_MODEL_NAME")

            if not api_key or not base_url or not model_name:
                raise Exception("缺少必要的环境变量: OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL_NAME")

            # 创建客户端
            self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=60)
            self.model_name = model_name

            # 验证客户端连接
            try:
                models = self.client.models.list()
                logger.info("AI评论助手客户端连接验证成功")
            except Exception as conn_err:
                raise Exception(f"API连接测试失败: {conn_err}")

            logger.info(f"AI评论助手初始化成功，使用模型: {model_name}")

        except Exception as e:
            logger.error(f"AI评论助手初始化失败: {e}")
            raise

    def generate_comment(self, battle_id: str, log_content: str) -> Dict[str, Any]:
        """
        生成AI对局点评

        参数:
            battle_id: 对局ID
            log_content: 对局日志内容

        返回:
            包含点评结果的字典
        """
        if not self.client:
            return {
                "battle_id": battle_id,
                "error": True,
                "message": "AI评论助手未正确初始化",
                "generated_at": time.time()
            }

        try:
            logger.info(f"开始为对局 {battle_id} 生成AI点评")

            # 如果日志内容过长，进行截断
            max_log_length = 50000  # 比游戏中的限制更宽松
            if len(log_content) > max_log_length:
                log_content = log_content[:max_log_length] + "\n... [日志已截断] ..."
                logger.info(f"对局 {battle_id} 的日志已截断至 {max_log_length} 字符")

            system_prompt = (
                "你是一位资深的阿瓦隆游戏（The Resistance: Avalon）裁判和分析师。"
                "你的任务是根据提供的游戏日志，对整场对战进行复盘和点评。"
                "日志包含了玩家的发言、任务的执行、队伍的组成、投票情况以及最终的游戏结果。"
                "请你重点分析以下几个方面：\n"
                "1. **关键决策点**：哪些队伍提议、投票或任务执行对战局走向产生了重大影响？为什么？\n"
                "2. **玩家表现**：哪些玩家的发言或行为表现突出（无论是正面还是负面）？请结合其角色进行分析（如果角色信息可见）。\n"
                "3. **红蓝阵营策略**：双方阵营在任务选择、人员派遣、信息传递（或误导）方面有何策略？效果如何？\n"
                "4. **梅林和刺客**：如果游戏进行到刺杀阶段，刺客的选择是否合理？梅林的隐藏或引导是否成功？\n"
                "5. **可改进之处**：对局中是否存在明显的失误或可以改进的策略选择？\n"
                "请以客观、中立的视角进行分析，并给出清晰、有条理的点评报告。"
                "报告的开头可以简要总结游戏结果和时长。"
                "你的回答将直接作为JSON文件中的 `comment` 字段的值。请确保你的回答是完整的文本。"
            )

            user_prompt = f"以下是阿瓦隆对局 {battle_id} 的游戏日志：\n\n{log_content}\n\n请根据上述日志，生成详细的对局复盘和点评。"

            # 调用LLM，使用更宽松的参数设置
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,  # 适中的创造性
                max_tokens=4096,  # 更大的输出长度限制
                top_p=0.9,
                presence_penalty=0.2,  # 较低的重复惩罚
                frequency_penalty=0.2,  # 较低的频率惩罚
            )

            response_content = completion.choices[0].message.content
            logger.info(f"成功为对局 {battle_id} 生成AI点评")

            return {
                "battle_id": battle_id,
                "comment": response_content,
                "generated_at": time.time(),
                "model_used": self.model_name
            }

        except Exception as e:
            logger.error(f"为对局 {battle_id} 生成AI点评失败: {e}")
            return {
                "battle_id": battle_id,
                "error": True,
                "message": f"AI点评生成失败: {str(e)}",
                "generated_at": time.time()
            }


# 全局实例
_comment_helper = None


def get_ai_comment_helper() -> AICommentHelper:
    """获取AI评论助手实例（单例模式）"""
    global _comment_helper
    if _comment_helper is None:
        _comment_helper = AICommentHelper()
    return _comment_helper


def generate_battle_comment(battle_id: str, log_content: str) -> Dict[str, Any]:
    """
    便捷函数：生成对局AI点评

    参数:
        battle_id: 对局ID
        log_content: 对局日志内容

    返回:
        包含点评结果的字典
    """
    helper = get_ai_comment_helper()
    return helper.generate_comment(battle_id, log_content)


if __name__ == "__main__":
    # 测试代码
    helper = AICommentHelper()
    test_log = "这是一个测试日志内容..."
    result = helper.generate_comment("test_battle", test_log)
    print(json.dumps(result, ensure_ascii=False, indent=2)) 