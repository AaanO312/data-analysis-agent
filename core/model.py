"""通义千问模型初始化（DashScope）— 单例 + 重试"""
import time
from langchain_community.chat_models.tongyi import ChatTongyi
from core.config import settings
from utils.logger import logger

_model = None
LLM_MAX_RETRIES = 3
LLM_RETRY_BASE_DELAY = 1.0  # 秒


def get_model() -> ChatTongyi:
    """单例获取 LLM 实例"""
    global _model
    if _model is None:
        _model = ChatTongyi(
            model=settings.DASHSCOPE_MODEL,
            dashscope_api_key=settings.DASHSCOPE_API_KEY,
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
        )
    return _model


def invoke_llm(prompt: str) -> str:
    """调用 LLM，带指数退避重试（最多3次）"""
    model = get_model()
    last_error = None
    for attempt in range(LLM_MAX_RETRIES):
        try:
            response = model.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            last_error = e
            if attempt < LLM_MAX_RETRIES - 1:
                delay = LLM_RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f"LLM 调用失败 (第{attempt+1}/{LLM_MAX_RETRIES}次): {e}，{delay:.1f}s 后重试")
                time.sleep(delay)
    raise last_error
