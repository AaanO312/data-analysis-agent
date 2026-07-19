"""Pydantic 数据模型：请求与响应 Schema"""
from pydantic import BaseModel, Field
from typing import Any


class ChatRequest(BaseModel):
    """聊天请求"""
    question: str = Field(..., description="用户自然语言问题")
    thread_id: str = Field(..., description="会话 ID，用于多轮对话上下文")


class UploadResponse(BaseModel):
    """文件上传响应"""
    thread_id: str = Field(..., description="新创建的会话 ID")
    table_name: str = Field(..., description="导入 SQLite 的表名")
    columns: list[str] = Field(..., description="列名列表")
    row_count: int = Field(..., description="总行数")
    data_dict: str = Field(..., description="数据字典")


class InsightResult(BaseModel):
    """结构化洞察输出 — 强制 LLM 按此 Schema 输出"""
    summary: str = Field(default="", description="一句话核心发现概括")
    key_findings: list[str] = Field(default_factory=list, description="2-3条关键数据发现")
    suggestion: str = Field(default="", description="具体可执行的业务建议")


class ChatResponse(BaseModel):
    """聊天响应 — 严格按需求四字段"""
    sql_text: str = Field(default="", description="生成的 SQL 语句")
    data_table: list[dict[str, Any]] = Field(default_factory=list, description="查询结果数据表")
    chart_json: str = Field(default="", description="Plotly 交互式图表的 JSON 字符串")
    insight: str = Field(default="", description="LLM 生成的业务洞察文字")


class ErrorResponse(BaseModel):
    """统一错误响应"""
    code: int = Field(default=500, description="错误码")
    msg: str = Field(default="内部错误", description="错误消息")
    detail: str = Field(default="", description="错误详情")
