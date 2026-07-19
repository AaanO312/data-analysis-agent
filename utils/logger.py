import logging
import json
import os
import sys
import contextvars
from datetime import datetime, timezone

LOG_ROOT = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_ROOT, exist_ok=True)

# 请求级 trace_id，贯穿所有节点
_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


def set_trace_id(tid: str):
    _trace_id.set(tid)


def get_trace_id() -> str:
    return _trace_id.get()


class JsonFormatter(logging.Formatter):
    """结构化 JSON 日志（文件用）"""
    def format(self, record):
        return json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "trace_id": get_trace_id(),
            "msg": record.getMessage(),
            "module": record.name,
        }, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """控制台格式（人可读 + trace_id）"""
    def format(self, record):
        trace = get_trace_id()
        ts = datetime.now().strftime("%H:%M:%S")
        return f"{ts} [{trace[:8]}] {record.levelname:<5} {record.getMessage()}"


def get_logger(name: str = "data_analysis_agent") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    # 控制台：简洁可读
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(ConsoleFormatter())
    logger.addHandler(console)

    # 文件：结构化 JSON
    log_file = os.path.join(LOG_ROOT, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    return logger


logger = get_logger()
