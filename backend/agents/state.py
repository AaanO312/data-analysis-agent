from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """LangGraph 全局状态 — 通用数据分析 Agent"""

    # === 输入 ===
    user_question: str
    csv_file_path: str
    thread_id: str

    # === 数据理解输出 ===
    table_name: str
    columns: list[str]
    data_dict: str
    row_count: int
    df_json: str

    # === NL2SQL 输出 ===
    generated_sql: str
    sql_retry_count: int

    # === SQL校验输出 ===
    sql_valid: bool
    sql_error: str

    # === 查询执行输出 ===
    query_result_json: str
    query_columns: list[str]

    # === 分析输出 ===
    analysis_result: str

    # === 可视化输出 ===
    chart_base64: str

    # === 洞察输出 ===
    insight_text: str

    # === 工作记忆（多轮追问） ===
    conversation_history: str

    # === LangGraph 内置 ===
    messages: Annotated[list[BaseMessage], add_messages]
