"""通义千问模型初始化（DashScope）— 单例模式"""
from langchain_community.chat_models.tongyi import ChatTongyi
from core.config import settings

_model = None


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
