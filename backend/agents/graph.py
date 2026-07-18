"""LangGraph 工作流：Supervisor 模式编排 — 通用数据分析 Agent"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from backend.agents.state import AgentState
from backend.agents.nodes import (
    data_understanding_node,
    nl2sql_node,
    sql_validator_node,
    analysis_node,
    visualization_node,
    insight_node,
)


def build_graph() -> StateGraph:
    """构建数据分析 Agent 状态图"""
    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("data_understanding", data_understanding_node)
    workflow.add_node("nl2sql", nl2sql_node)
    workflow.add_node("sql_validator", sql_validator_node)
    workflow.add_node("analysis", analysis_node)
    workflow.add_node("visualization", visualization_node)
    workflow.add_node("insight", insight_node)

    # 入口
    workflow.set_entry_point("data_understanding")

    # 数据理解 → 条件路由：有问题→NL2SQL，仅上传→结束
    workflow.add_conditional_edges(
        "data_understanding",
        _route_after_understanding,
        {"nl2sql": "nl2sql", "end": END},
    )

    # NL2SQL → SQL校验
    workflow.add_edge("nl2sql", "sql_validator")

    # SQL校验 → 条件路由
    workflow.add_conditional_edges(
        "sql_validator",
        _route_after_validation,
        {"analysis": "analysis", "nl2sql": "nl2sql", "insight": "insight"},
    )

    # 分析 → 并行（可视化 + 洞察）
    workflow.add_edge("analysis", "visualization")
    workflow.add_edge("analysis", "insight")

    # 结束
    workflow.add_edge("visualization", END)
    workflow.add_edge("insight", END)

    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)
    return app


def _route_after_understanding(state: AgentState) -> str:
    """数据理解后的路由：如果只是上传（无问题），直接结束"""
    if not state.get("user_question", "").strip():
        return "end"
    return "nl2sql"


def _route_after_validation(state: AgentState) -> str:
    """SQL校验后的路由决策"""
    if state.get("sql_valid"):
        return "analysis"
    retry_count = state.get("sql_retry_count", 0)
    if retry_count < 2:
        return "nl2sql"
    return "insight"
