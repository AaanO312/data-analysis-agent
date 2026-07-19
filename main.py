"""通用数据分析 Agent — FastAPI 入口（路由 + 中间件 + 启动）"""
import os
import json
import uuid
import time
import asyncio
import pandas as pd
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from schemas.agent import ChatRequest, ChatResponse, UploadResponse
from tools.sql_tool import csv_to_sqlite
from tools.session_store import load_sessions, create_session, get_session, update_conversation
from tools.metrics import metrics
from agents.graph import build_graph
from core.config import settings
from utils.logger import logger, set_trace_id

app = FastAPI(
    title="通用数据分析 Agent",
    description="上传 CSV，自然语言提问，AI 自动查数据、画图、给洞察",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# LangGraph 实例 + 持久化会话存储
_graph = build_graph()
_session_state: dict = load_sessions()

# 限流：每 IP 每分钟最多 10 次请求
_rate_window: dict[str, list[float]] = {}
RATE_LIMIT = 10
RATE_WINDOW = 60  # 秒

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


def _check_rate_limit(client_ip: str) -> bool:
    now = time.time()
    timestamps = _rate_window.get(client_ip, [])
    timestamps = [t for t in timestamps if now - t < RATE_WINDOW]
    if len(timestamps) >= RATE_LIMIT:
        return False
    timestamps.append(now)
    _rate_window[client_ip] = timestamps
    return True


# ── 全局中间件：trace_id + 异常捕获 ──
@app.middleware("http")
async def request_middleware(request: Request, call_next):
    tid = uuid.uuid4().hex[:12]
    set_trace_id(tid)
    response = None
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"未捕获异常: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"code": 500, "msg": "内部错误", "detail": str(e)})


# ── 健康检查 ──
@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/metrics")
async def get_metrics():
    return metrics.snapshot()


# ── 上传 CSV ──
def _save_upload_file(upload_file: UploadFile, thread_id: str) -> str:
    upload_dir = settings.UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    base, ext = os.path.splitext(upload_file.filename or "data.csv")
    file_path = os.path.join(upload_dir, f"{base}_{thread_id[:8]}{ext}")
    with open(file_path, "wb") as f:
        f.write(upload_file.file.read())
    return file_path


@app.post("/upload", response_model=UploadResponse)
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="仅支持 CSV 文件")

    # 文件大小校验
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail=f"文件过大，限制 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")
    await file.seek(0)

    # 内容嗅探：前 500 字节必须包含逗号（CSV 基本特征）
    head = content[:500].decode("utf-8", errors="ignore")
    if "," not in head:
        raise HTTPException(status_code=400, detail="文件内容不是合法 CSV 格式（未检测到逗号分隔符）")

    thread_id = uuid.uuid4().hex
    logger.info(f"/upload: thread_id={thread_id}, file={file.filename}, size={len(content)}B")
    metrics.record_upload()
    csv_path = _save_upload_file(file, thread_id)

    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(csv_path, encoding="gbk")
        except Exception:
            df = pd.read_csv(csv_path, encoding="latin-1")

    df.columns = [col.strip().replace(" ", "_").replace("-", "_") for col in df.columns]
    table_name, columns, row_count = csv_to_sqlite(csv_path, thread_id)
    data_dict = _build_basic_data_dict(df, columns)

    create_session(_session_state, thread_id, {
        "csv_file_path": csv_path, "table_name": table_name,
        "columns": columns, "data_dict": data_dict, "row_count": row_count,
    })

    logger.info(f"[API] /upload 完成: {table_name}, {len(columns)} 列, {row_count} 行")
    return UploadResponse(thread_id=thread_id, table_name=table_name,
                          columns=columns, row_count=row_count, data_dict=data_dict)


# ── 自然语言对话 ──
@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    thread_id = req.thread_id

    # 限流检查
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        metrics.record_rate_limited()
        raise HTTPException(status_code=429, detail=f"请求过快，每分钟最多 {RATE_LIMIT} 次")

    logger.info(f"/chat: thread_id={thread_id}, question={req.question[:80]}")
    session = get_session(_session_state, thread_id)
    if not session:
        raise HTTPException(status_code=400, detail="无效的 thread_id，请先上传 CSV 文件")

    config = {"configurable": {"thread_id": thread_id}}
    t0 = time.time()

    try:
        conversation_history = session.get("conversation_history", "")
        state_input = {
            "user_question": req.question,
            "csv_file_path": session["csv_file_path"],
            "thread_id": thread_id,
            "table_name": session["table_name"],
            "columns": session["columns"],
            "data_dict": session["data_dict"],
            "conversation_history": conversation_history,
            "sql_retry_count": 0, "sql_valid": False, "sql_error": "",
        }
        state = _graph.invoke(state_input, config)

        insight_text = state.get("insight_text", "")
        update_conversation(_session_state, thread_id, req.question, insight_text)

        query_result_json = state.get("query_result_json", "[]")
        try:
            data_table = json.loads(query_result_json)
        except (json.JSONDecodeError, TypeError):
            data_table = []

        logger.info(f"/chat 完成: sql_valid={state.get('sql_valid')}")
        metrics.record_chat(time.time() - t0, error=False)
        return ChatResponse(
            sql_text=state.get("generated_sql", ""),
            data_table=data_table,
            chart_base64=state.get("chart_base64", ""),
            insight=state.get("insight_text", ""),
        )
    except Exception as e:
        metrics.record_chat(time.time() - t0, error=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── 流式对话（SSE）──
@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        metrics.record_rate_limited()
        raise HTTPException(status_code=429, detail="请求过快")

    thread_id = req.thread_id
    session = get_session(_session_state, thread_id)
    if not session:
        raise HTTPException(status_code=400, detail="无效的 thread_id")

    config = {"configurable": {"thread_id": thread_id}}
    conversation_history = session.get("conversation_history", "")
    state_input = {
        "user_question": req.question,
        "csv_file_path": session["csv_file_path"],
        "thread_id": thread_id,
        "table_name": session["table_name"],
        "columns": session["columns"],
        "data_dict": session["data_dict"],
        "conversation_history": conversation_history,
        "sql_retry_count": 0, "sql_valid": False, "sql_error": "",
    }

    async def event_stream():
        t0 = time.time()
        last_sql = ""
        last_chart = ""
        last_data = ""
        last_insight = ""
        try:
            for chunk in _graph.stream(state_input, config, stream_mode="values"):
                sql = chunk.get("generated_sql", "")
                chart = chunk.get("chart_base64", "")
                result_json = chunk.get("query_result_json", "[]")
                insight = chunk.get("insight_text", "")
                err = chunk.get("sql_error", "")

                if err:
                    yield f"data: {json.dumps({'type': 'error', 'msg': err}, ensure_ascii=False)}\n\n"
                if sql and sql != last_sql:
                    last_sql = sql
                    yield f"data: {json.dumps({'type': 'sql', 'text': sql}, ensure_ascii=False)}\n\n"
                if result_json and result_json != last_data:
                    last_data = result_json
                    try:
                        tbl = json.loads(result_json)
                    except Exception:
                        tbl = []
                    yield f"data: {json.dumps({'type': 'data', 'table': tbl}, ensure_ascii=False, default=str)}\n\n"
                if chart and chart != last_chart:
                    last_chart = chart
                    yield f"data: {json.dumps({'type': 'chart', 'base64': chart}, ensure_ascii=False)}\n\n"
                if insight and insight != last_insight:
                    last_insight = insight
                    yield f"data: {json.dumps({'type': 'insight', 'text': insight}, ensure_ascii=False)}\n\n"

            metrics.record_chat(time.time() - t0, error=False)
            update_conversation(_session_state, thread_id, req.question, last_insight)
            yield "data: {\"type\": \"done\"}\n\n"

        except Exception as e:
            metrics.record_chat(time.time() - t0, error=True)
            yield f"data: {json.dumps({'type': 'error', 'msg': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _build_basic_data_dict(df: pd.DataFrame, columns: list[str]) -> str:
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.BACKEND_HOST, port=settings.BACKEND_PORT, reload=True)
