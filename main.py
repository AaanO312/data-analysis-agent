"""通用数据分析 Agent — FastAPI 入口（路由 + 中间件 + 启动）"""
import os
import json
import uuid
import pandas as pd
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from schemas.agent import ChatRequest, ChatResponse, UploadResponse
from tools.sql_tool import csv_to_sqlite
from agents.graph import build_graph
from core.config import settings
from utils.logger import logger

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

# LangGraph 实例
_graph = build_graph()
_session_state: dict = {}


# ── 全局异常中间件 ──
@app.middleware("http")
async def global_exception_handler(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"[Global] 未捕获异常: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"code": 500, "msg": "内部错误", "detail": str(e)})


# ── 健康检查 ──
@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


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

    thread_id = uuid.uuid4().hex
    logger.info(f"[API] /upload: thread_id={thread_id}, file={file.filename}")
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

    _session_state[thread_id] = {
        "csv_file_path": csv_path, "table_name": table_name,
        "columns": columns, "data_dict": data_dict, "row_count": row_count,
    }

    logger.info(f"[API] /upload 完成: {table_name}, {len(columns)} 列, {row_count} 行")
    return UploadResponse(thread_id=thread_id, table_name=table_name,
                          columns=columns, row_count=row_count, data_dict=data_dict)


# ── 自然语言对话 ──
@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    thread_id = req.thread_id
    logger.info(f"[API] /chat: thread_id={thread_id}, question={req.question[:80]}")

    session = _session_state.get(thread_id)
    if not session:
        raise HTTPException(status_code=400, detail="无效的 thread_id，请先上传 CSV 文件")

    config = {"configurable": {"thread_id": thread_id}}

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
        _session_state[thread_id]["conversation_history"] = (
            f"{conversation_history}\n用户: {req.question}\n助手: {insight_text[:300]}"
        )

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
