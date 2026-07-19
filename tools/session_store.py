"""会话持久化存储：JSON 文件，重启不丢失"""
import json
import os
from datetime import datetime
from utils.logger import logger

STORE_PATH = os.path.join(os.path.dirname(__file__), "..", "sessions.json")


def load_sessions() -> dict:
    """从磁盘加载所有会话"""
    if not os.path.exists(STORE_PATH):
        return {}
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"[Session] 加载 {len(data)} 个历史会话")
        return data
    except Exception as e:
        logger.warning(f"[Session] 加载失败: {e}")
        return {}


def save_sessions(sessions: dict):
    """保存所有会话到磁盘"""
    try:
        with open(STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[Session] 保存失败: {e}")


def get_session(store: dict, thread_id: str) -> dict | None:
    """获取指定会话"""
    return store.get(thread_id)


def create_session(store: dict, thread_id: str, session_data: dict) -> dict:
    """创建新会话并持久化"""
    session_data["created_at"] = datetime.now().isoformat()
    session_data["conversation_history"] = ""
    store[thread_id] = session_data
    save_sessions(store)
    logger.info(f"[Session] 创建会话: {thread_id}, 表={session_data.get('table_name')}")
    return store


def update_conversation(store: dict, thread_id: str, question: str, answer: str):
    """追加对话历史并持久化"""
    if thread_id not in store:
        return
    history = store[thread_id].get("conversation_history", "")
    store[thread_id]["conversation_history"] = (
        f"{history}\n用户: {question}\n助手: {answer[:300]}"
    )
    save_sessions(store)
