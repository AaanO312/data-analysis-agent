"""FastAPI 路由：/upload 和 /chat"""
import os
import json
import uuid
import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException
from backend.schemas.agent import ChatRequest, ChatResponse, UploadResponse
from backend.tools.sql_tool import csv_to_sqlite
from backend.agents.graph import build_graph
from backend.core.config import settings
from backend.utils.logger import logger

router = APIRouter()

# LangGraph 实例（模块级单例）
_graph = build_graph()

# 存储每个 thread_id 的 CSV 文件路径和列信息
_session_state: dict = {}


def _save_upload_file(upload_file: UploadFile, thread_id: str) -> str:
    """保存上传文件到 uploads/ 目录，返回文件路径"""
    upload_dir = settings.UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    base, ext = os.path.splitext(upload_file.filename or "data.csv")
    file_path = os.path.join(upload_dir, f"{base}_{thread_id[:8]}{ext}")
    with open(file_path, "wb") as f:
        f.write(upload_file.file.read())
    return file_path


@router.post("/upload", response_model=UploadResponse)
async def upload_csv(file: UploadFile = File(...)):
    """上传 CSV，存入 SQLite 内存库，返回表结构"""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="仅支持 CSV 文件")

    thread_id = uuid.uuid4().hex
    logger.info(f"[API] /upload: thread_id={thread_id}, file={file.filename}")

    # 保存文件
    csv_path = _save_upload_file(file, thread_id)

    # 读取 CSV 生成列信息（不调 LLM，直接做基础分析）
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(csv_path, encoding="gbk")
        except Exception:
            df = pd.read_csv(csv_path, encoding="latin-1")

    df.columns = [col.strip().replace(" ", "_").replace("-", "_") for col in df.columns]

    # 导入 SQLite
    table_name, columns, row_count = csv_to_sqlite(csv_path, thread_id)

    # 生成基础数据字典
    data_dict = _build_basic_data_dict(df, columns)

    # 缓存会话信息
    _session_state[thread_id] = {
        "csv_file_path": csv_path,
        "table_name": table_name,
        "columns": columns,
        "data_dict": data_dict,
        "row_count": row_count,
    }

    logger.info(f"[API] /upload 完成: {table_name}, {len(columns)} 列, {row_count} 行")
    return UploadResponse(
        thread_id=thread_id,
        table_name=table_name,
        columns=columns,
        row_count=row_count,
        data_dict=data_dict,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """接收自然语言问题，运行 LangGraph pipeline，返回结构化结果"""
    thread_id = req.thread_id
    logger.info(f"[API] /chat: thread_id={thread_id}, question={req.question[:80]}")

    # 校验 thread_id 是否有效（是否已上传 CSV）
    session = _session_state.get(thread_id)
    if not session:
        raise HTTPException(status_code=400, detail="无效的 thread_id，请先上传 CSV 文件")

    config = {"configurable": {"thread_id": thread_id}}

    try:
        # 建立对话历史
        conversation_history = session.get("conversation_history", "")

        state_input = {
            "user_question": req.question,
            "csv_file_path": session["csv_file_path"],
            "thread_id": thread_id,
            "table_name": session["table_name"],
            "columns": session["columns"],
            "data_dict": session["data_dict"],
            "conversation_history": conversation_history,
            "sql_retry_count": 0,
            "sql_valid": False,
            "sql_error": "",
        }

        state = _graph.invoke(state_input, config)

        # 更新对话历史
        insight_text = state.get("insight_text", "")
        _session_state[thread_id]["conversation_history"] = (
            f"{conversation_history}\n用户: {req.question}\n助手: {insight_text[:300]}"
        )

        # 解析 data_table
        query_result_json = state.get("query_result_json", "[]")
        try:
            data_table = json.loads(query_result_json)
        except (json.JSONDecodeError, TypeError):
            data_table = []

        logger.info(f"[API] /chat 完成: sql_valid={state.get('sql_valid')}")

        return ChatResponse(
            sql_text=state.get("generated_sql", ""),
            data_table=data_table,
            chart_base64=state.get("chart_base64", ""),
            insight=state.get("insight_text", ""),
        )

    except Exception as e:
        logger.error(f"[API] /chat 内部错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _build_basic_data_dict(df: pd.DataFrame, columns: list[str]) -> str:
    """生成基础数据字典（不调 LLM 的快速版本）"""
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
