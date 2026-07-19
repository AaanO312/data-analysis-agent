"""LangGraph 工作流：Supervisor 模式编排 — 通用数据分析 Agent"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from agents.state import AgentState
from agents.nodes import (
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

    # SQL校验 → 条件路由：通过→分析，失败且可重试→NL2SQL，重试耗尽→洞察降级
    workflow.add_conditional_edges(
        "sql_validator",
        _route_after_validation,
        {"analysis": "analysis", "nl2sql": "nl2sql", "insight": "insight"},
    )

    # 分析 → 条件路由：SQL执行失败且可重试→NL2SQL纠错闭环，成功/重试耗尽→可视化
    workflow.add_conditional_edges(
        "analysis",
        _route_after_analysis,
        {"nl2sql": "nl2sql", "visualization": "visualization", "insight": "insight"},
    )

    # 可视化 → 洞察（串行，洞察依赖分析结果）
    workflow.add_edge("visualization", "insight")

    # 结束
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
    # 重试耗尽 → 跳过分析和可视化，直接给降级洞察
    return "insight"


def _route_after_analysis(state: AgentState) -> str:
    """SQL执行后的路由决策：成功→继续，执行失败且可重试→退回NL2SQL纠错"""
    query_result = state.get("query_result_json", "")
    retry_count = state.get("sql_retry_count", 0)
    # 检查是否为执行错误（analysis_node 将错误编码为 {"error": ...}）
    has_exec_error = '"error"' in query_result
    if has_exec_error and retry_count < 2:
        return "nl2sql"
    if has_exec_error:
        # 重试耗尽 → 跳过可视化，降级给洞察
        return "insight"
    return "visualization"
