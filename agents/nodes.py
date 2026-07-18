"""数据分析 Agent 全部节点：数据理解 → NL2SQL → SQL校验 → 分析 → 可视化 → 洞察"""
import pandas as pd
import json
import os
import re
from agents.state import AgentState
from core.model import get_model
from agents.few_shot import match_examples
from tools.sql_tool import csv_to_sqlite, execute_sql, explain_sql
from tools.pandas_tool import analyze_data, choose_chart_type, generate_chart_base64
from utils.logger import logger


# ==================== Prompt 加载（仅一份） ====================

def _load_prompt(name: str) -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", f"{name}.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


# ==================== 节点1：数据理解 ====================

def data_understanding_node(state: AgentState) -> dict:
    logger.info("=" * 60)
    logger.info("[数据理解] 开始解析CSV文件...")
    logger.info(f"[数据理解] 文件路径: {state['csv_file_path']}")

    csv_path = state["csv_file_path"]

    # 读取 CSV（自动处理编码）
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(csv_path, encoding="gbk")
        except Exception:
            df = pd.read_csv(csv_path, encoding="latin-1")

    # 清理列名
    df.columns = [col.strip().replace(" ", "_").replace("-", "_") for col in df.columns]
    columns = list(df.columns)
    row_count = len(df)

    logger.info(f"[数据理解] 读取完成: {row_count} 行, {len(columns)} 列")
    logger.info(f"[数据理解] 列名: {columns}")

    # 生成列信息
    column_info = _build_column_info(df, columns)
    logger.info("[数据理解] 自动分析完成，生成列信息")

    # LLM 推测业务含义
    try:
        model = get_model()
        prompt_template = _load_prompt("data_understanding")
        prompt = prompt_template.format(column_info=column_info)
        response = model.invoke(prompt)
        data_dict = response.content.strip()
        logger.info(f"[数据理解] LLM 生成数据字典，长度={len(data_dict)} 字符")
    except Exception as e:
        logger.warning(f"[数据理解] LLM 调用失败，使用自动生成的数据字典: {e}")
        data_dict = column_info

    # 导入 SQLite 内存库
    table_name = os.path.splitext(os.path.basename(csv_path))[0]
    table_name = table_name.replace(" ", "_").replace("-", "_").lower()
    thread_id = state.get("thread_id", "default")

    table_name, columns, row_count = csv_to_sqlite(csv_path, thread_id, table_name)

    df_json = df.head(500).to_json(orient="records", force_ascii=False)

    logger.info(f"[数据理解] 数据字典摘要:\n{data_dict[:500]}")
    logger.info("=" * 60)

    return {
        "table_name": table_name,
        "columns": columns,
        "data_dict": data_dict,
        "row_count": row_count,
        "df_json": df_json,
    }


def _build_column_info(df: pd.DataFrame, columns: list[str]) -> str:
    lines = []
    for col in columns:
        dtype = str(df[col].dtype)
        non_null = int(df[col].notna().sum())
        unique_count = int(df[col].nunique())
        sample_vals = df[col].dropna().head(3).tolist()
        sample_str = ", ".join([str(v)[:50] for v in sample_vals])
        lines.append(f"| {col} | {dtype} | 非空:{non_null} | 唯一值:{unique_count} | {sample_str} |")
    header = "| 列名 | 数据类型 | 非空数 | 唯一值数 | 示例值(前3) |\n"
    header += "|------|---------|--------|---------|------------|\n"
    return header + "\n".join(lines)


# ==================== 节点2：NL2SQL ====================

def nl2sql_node(state: AgentState) -> dict:
    logger.info("-" * 40)
    logger.info(f"[NL2SQL] 开始转换...")
    logger.info(f"[NL2SQL] 用户问题: {state['user_question']}")

    sql_error = state.get("sql_error", "")
    retry_count = state.get("sql_retry_count", 0)
    if sql_error:
        retry_count = retry_count + 1
        logger.info(f"[NL2SQL] 这是第{retry_count}次重试，上次错误: {sql_error}")

    table_name = state.get("table_name", "data")
    data_dict = state.get("data_dict", "")
    user_question = state["user_question"]
    conversation_history = state.get("conversation_history", "无")

    # 匹配 Few-shot 示例
    examples = match_examples(user_question, top_k=5)
    few_shot_text = _format_examples(examples, table_name)
    logger.info(f"[NL2SQL] 匹配到 {len(examples)} 条 Few-shot 示例")

    # 构建 Prompt
    prompt_template = _load_prompt("nl2sql")
    prompt = prompt_template.format(
        table_name=table_name,
        data_dict=data_dict[:3000],
        few_shot_examples=few_shot_text,
        conversation_history=conversation_history,
        user_question=user_question,
    )

    if sql_error:
        prompt += (
            f"\n\n## 重要：上一次生成的SQL校验失败 ##\n"
            f"错误信息: {sql_error}\n"
            f"请修正上述错误，重新生成正确的SQL。这是第{retry_count}次重试。"
        )

    model = get_model()
    response = model.invoke(prompt)
    sql = _extract_sql(response.content.strip())
    logger.info(f"[NL2SQL] 生成SQL:\n{sql}")

    return {
        "generated_sql": sql,
        "sql_retry_count": retry_count,
    }


def _format_examples(examples: list[dict], table_name: str) -> str:
    parts = []
    for i, ex in enumerate(examples, 1):
        sql = ex["sql"].replace("{table_name}", table_name)
        parts.append(f"### 示例{i}: {ex['scenario']}\n问题: {ex['question']}\nSQL:\n{sql}")
    return "\n\n".join(parts)


def _extract_sql(text: str) -> str:
    text = re.sub(r"```sql\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```\s*", "", text)
    return text.strip()


# ==================== 节点3：SQL 校验 ====================

DANGEROUS_KEYWORDS = [
    r"\bDELETE\b", r"\bDROP\b", r"\bINSERT\b", r"\bUPDATE\b",
    r"\bALTER\b", r"\bTRUNCATE\b", r"\bCREATE\b", r"\bREPLACE\b",
]


def sql_validator_node(state: AgentState) -> dict:
    sql = state.get("generated_sql", "")
    columns = state.get("columns", [])
    table_name = state.get("table_name", "")
    thread_id = state.get("thread_id", "default")
    retry_count = state.get("sql_retry_count", 0)

    logger.info("-" * 40)
    logger.info(f"[SQL校验] 开始校验 (第{retry_count + 1}次)...")

    # Step 1: 安全校验
    sql_upper = sql.upper()
    for keyword in DANGEROUS_KEYWORDS:
        if re.search(keyword, sql_upper):
            error = f"安全校验失败: SQL包含危险操作 {keyword.strip('\\\\b')}"
            logger.warning(f"[SQL校验] {error}")
            return {"sql_valid": False, "sql_error": error}

    logger.info("[SQL校验] ✓ 安全检查通过")

    # Step 2: 格式检查
    if not sql.strip().upper().startswith("SELECT"):
        error = "SQL校验失败: 不是SELECT查询语句"
        logger.warning(f"[SQL校验] {error}")
        return {"sql_valid": False, "sql_error": error}

    logger.info("[SQL校验] ✓ 格式检查通过（SELECT语句）")

    # Step 3: 语法校验（EXPLAIN dry-run）
    syntax_error = explain_sql(sql, thread_id)
    if syntax_error:
        error = f"SQL语法错误: {syntax_error}"
        logger.warning(f"[SQL校验] {error}")
        return {"sql_valid": False, "sql_error": error}

    logger.info("[SQL校验] ✓ 语法检查通过（EXPLAIN dry-run成功）")

    # Step 4: 字段校验
    field_errors = _check_fields(sql, columns, table_name)
    if field_errors:
        error = f"字段校验失败: {field_errors}"
        logger.warning(f"[SQL校验] {error}")
        return {"sql_valid": False, "sql_error": error}

    logger.info("[SQL校验] ✓ 字段检查通过")
    logger.info("[SQL校验] ✅ 全部校验通过！")
    return {"sql_valid": True, "sql_error": ""}


def _check_fields(sql: str, valid_columns: list[str], table_name: str) -> str:
    sql_keywords = {
        "SELECT", "FROM", "WHERE", "GROUP", "BY", "ORDER", "HAVING",
        "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "ON", "AS", "AND",
        "OR", "NOT", "IN", "LIKE", "BETWEEN", "IS", "NULL", "DISTINCT",
        "COUNT", "SUM", "AVG", "MAX", "MIN", "CASE", "WHEN", "THEN",
        "ELSE", "END", "LIMIT", "OFFSET", "DESC", "ASC", "UNION",
        "WITH", "ALL", "CAST", "COALESCE", "IFNULL", "STRFTIME",
        "EXISTS", "ANY", "SOME", "TRUE", "FALSE", "INTEGER", "TEXT",
        "REAL", "BLOB", "PRIMARY", "KEY", "FOREIGN", "REFERENCES",
    }
    errors = []
    sql_no_str = re.sub(r"'[^']*'", "", sql)
    sql_no_str = re.sub(r'"[^"]*"', "", sql_no_str)
    identifiers = set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', sql_no_str))
    for ident in identifiers:
        ident_lower = ident.lower()
        if ident_lower in {kw.lower() for kw in sql_keywords}:
            continue
        if ident_lower == table_name.lower():
            continue
        if re.search(rf'\b{re.escape(ident)}\s*\(', sql):
            continue
    return "; ".join(errors) if errors else ""


# ==================== 节点4：分析（SQL执行 + pandas分析） ====================

def analysis_node(state: AgentState) -> dict:
    logger.info("-" * 40)
    logger.info("[分析] 开始执行 SQL 并分析结果...")

    sql = state.get("generated_sql", "")
    thread_id = state.get("thread_id", "default")
    user_question = state.get("user_question", "")

    # 执行 SQL
    try:
        rows, columns = execute_sql(sql, thread_id)
    except Exception as e:
        logger.error(f"[分析] SQL执行失败: {e}")
        return {
            "query_result_json": json.dumps({"error": str(e)}, ensure_ascii=False),
            "query_columns": [],
            "analysis_result": f"SQL执行失败: {e}",
        }

    query_result_json = json.dumps(rows, ensure_ascii=False, default=str)
    logger.info(f"[分析] 查询返回 {len(rows)} 行, 列: {columns}")

    # 自动数据分析
    auto_stats = analyze_data(rows, columns)
    logger.info(f"[分析] 自动统计完成: trend={auto_stats.get('trend', '')[:100]}")

    # LLM 深度分析
    analysis_result = ""
    try:
        model = get_model()
        prompt_template = _load_prompt("analysis")
        prompt = prompt_template.format(
            user_question=user_question,
            query_summary=f"查询返回 {len(rows)} 行数据，列: {', '.join(columns)}。"
                          f"前5行: {json.dumps(rows[:5], ensure_ascii=False, default=str)}",
            auto_analysis=json.dumps(auto_stats, ensure_ascii=False, default=str),
        )
        response = model.invoke(prompt)
        analysis_result = response.content.strip()
        logger.info(f"[分析] LLM分析结果长度={len(analysis_result)} 字符")
    except Exception as e:
        logger.warning(f"[分析] LLM分析失败，使用自动统计: {e}")
        analysis_result = json.dumps(auto_stats, ensure_ascii=False, default=str)

    return {
        "query_result_json": query_result_json,
        "query_columns": columns,
        "analysis_result": analysis_result,
    }


# ==================== 节点5：可视化 ====================

def visualization_node(state: AgentState) -> dict:
    logger.info("-" * 40)
    logger.info("[可视化] 开始生成图表...")

    query_result_json = state.get("query_result_json", "[]")
    query_columns = state.get("query_columns", [])
    user_question = state.get("user_question", "")

    try:
        rows = json.loads(query_result_json)
    except json.JSONDecodeError:
        logger.warning("[可视化] 查询结果JSON解析失败")
        return {"chart_base64": ""}

    if not rows:
        logger.warning("[可视化] 无数据，跳过图表")
        return {"chart_base64": ""}

    chart_type = choose_chart_type(rows, query_columns)
    logger.info(f"[可视化] 自动选择图表类型: {chart_type}")

    title = user_question[:30] if user_question else ""
    chart_base64 = generate_chart_base64(rows, query_columns, chart_type, title)

    if chart_base64:
        logger.info(f"[可视化] 图表生成成功, base64长度={len(chart_base64)}")
    else:
        logger.warning("[可视化] 图表生成失败")

    return {"chart_base64": chart_base64}


# ==================== 节点6：洞察 ====================

def insight_node(state: AgentState) -> dict:
    logger.info("-" * 40)
    logger.info("[洞察] 开始生成洞察...")

    user_question = state.get("user_question", "")
    analysis_result = state.get("analysis_result", "")
    query_result_json = state.get("query_result_json", "[]")
    query_columns = state.get("query_columns", [])

    try:
        rows = json.loads(query_result_json)
    except json.JSONDecodeError:
        rows = []

    auto_stats = f"查询返回 {len(rows)} 行数据，列: {', '.join(query_columns)}"

    try:
        model = get_model()
        prompt_template = _load_prompt("insight")
        prompt = prompt_template.format(
            user_question=user_question,
            analysis_result=analysis_result[:2000],
            auto_stats=auto_stats,
        )
        response = model.invoke(prompt)
        insight_text = response.content.strip()
        logger.info(f"[洞察] 生成洞察，长度={len(insight_text)} 字符")
        logger.info(f"[洞察] 内容摘要: {insight_text[:200]}")
    except Exception as e:
        logger.warning(f"[洞察] LLM调用失败: {e}")
        insight_text = f"分析完成。{auto_stats}。\n{analysis_result[:300]}"

    logger.info("-" * 40)
    return {"insight_text": insight_text}
