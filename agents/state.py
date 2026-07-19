"""LangGraph Agent 全局状态定义 — 通用数据分析 Agent"""
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """LangGraph 全局状态，贯穿数据理解 → NL2SQL → SQL校验 → 分析 → 可视化 → 洞察全流程"""

    # === 输入 ===
    user_question: str          # 用户自然语言提问
    csv_file_path: str          # 上传 CSV 文件的本地路径
    thread_id: str              # 会话唯一标识（用于 SQLite 连接隔离 + 会话持久化）

    # === 数据理解输出 ===
    table_name: str             # 导入 SQLite 的表名（从 CSV 文件名派生）
    columns: list[str]          # 清洗后的列名列表
    data_dict: str              # LLM 生成的业务含义数据字典（Markdown 表格）
    row_count: int              # CSV 总行数
    df_json: str                # 数据前 500 行的 JSON 快照（供 LLM 上下文使用）

    # === NL2SQL 输出 ===
    generated_sql: str          # LLM 生成的 SQLite SELECT 语句
    sql_retry_count: int        # SQL 生成失败后的重试次数（上限 2 次）

    # === SQL 校验输出 ===
    sql_valid: bool             # SQL 是否通过全部校验（安全 + 语法 + 字段）
    sql_error: str              # 校验失败时的错误详情（供重试时反馈给 LLM）

    # === 查询执行输出 ===
    query_result_json: str      # 查询结果的 JSON 序列化（dict 列表）
    query_columns: list[str]    # 查询返回的列名（保持顺序）

    # === 分析输出 ===
    analysis_result: str        # LLM 对查询结果的深度分析文字

    # === 可视化输出 ===
    chart_json: str             # Plotly 交互式图表的 JSON 字符串（前端 pio.from_json 渲染）

    # === 洞察输出 ===
    insight_text: str           # LLM 生成的业务洞察 + 可执行建议

    # === 工作记忆（多轮追问） ===
    conversation_history: str   # 裁剪后的对话历史摘要（每轮最多 300 字符）

    # === LangGraph 内置（消息通道，自动累积） ===
    messages: Annotated[list[BaseMessage], add_messages]
