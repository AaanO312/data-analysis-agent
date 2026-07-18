"""应用配置：使用 pydantic-settings 统一管理环境变量"""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """全局配置，自动从 .env / 环境变量读取"""

    DASHSCOPE_API_KEY: str = Field(default="", description="通义千问 API Key")
    DASHSCOPE_MODEL: str = Field(default="qwen-plus", description="模型名称")
    LLM_MAX_TOKENS: int = Field(default=4096, description="LLM 最大输出 token 数")
    LLM_TEMPERATURE: float = Field(default=0.3, description="LLM 温度参数")

    BACKEND_HOST: str = Field(default="0.0.0.0", description="FastAPI 监听地址")
    BACKEND_PORT: int = Field(default=8000, description="FastAPI 监听端口")

    UPLOAD_DIR: str = Field(default="uploads", description="CSV 文件上传目录")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
