import sqlite3
import pandas as pd
import json
from backend.utils.logger import logger


# 全局内存数据库连接（会话级别）
_connections: dict[str, sqlite3.Connection] = {}


def get_connection(thread_id: str) -> sqlite3.Connection:
    """获取或创建会话对应的 SQLite 内存连接"""
    if thread_id not in _connections:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _connections[thread_id] = conn
        logger.info(f"[DB] 创建新的 SQLite 内存连接，thread_id={thread_id}")
    return _connections[thread_id]


def csv_to_sqlite(csv_path: str, thread_id: str, table_name: str = None) -> tuple[str, list[str], int]:
    """
    将 CSV 文件导入 SQLite 内存库。
    返回：(table_name, columns, row_count)
    """
    logger.info(f"[DB] 开始导入 CSV → SQLite: {csv_path}")

    # 读取 CSV（自动处理编码）
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, encoding="gbk")
    except Exception:
        df = pd.read_csv(csv_path, encoding="latin-1")

    # 自动确定表名
    if not table_name:
        import os
        table_name = os.path.splitext(os.path.basename(csv_path))[0]
        table_name = table_name.replace(" ", "_").replace("-", "_").lower()

    # 清理列名：去空格、特殊字符
    df.columns = [col.strip().replace(" ", "_").replace("-", "_") for col in df.columns]

    conn = get_connection(thread_id)

    # 删除旧表（如果存在）
    conn.execute(f"DROP TABLE IF EXISTS \"{table_name}\"")

    # 写入 SQLite
    df.to_sql(table_name, conn, index=False, if_exists="replace")

    columns = list(df.columns)
    row_count = len(df)

    logger.info(f"[DB] 导入完成: 表名={table_name}, 列数={len(columns)}, 行数={row_count}")
    logger.info(f"[DB] 列名: {columns}")

    return table_name, columns, row_count


def execute_sql(sql: str, thread_id: str) -> tuple[list, list[str]]:
    """
    执行 SQL 查询，返回 (行数据列表, 列名列表)。
    行数据为 dict 列表。
    """
    conn = get_connection(thread_id)
    logger.info(f"[DB] 执行 SQL:\n{sql}")

    cursor = conn.execute(sql)
    columns = [desc[0] for desc in cursor.description] if cursor.description else []
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    logger.info(f"[DB] 查询返回 {len(rows)} 行, {len(columns)} 列")
    return rows, columns


def explain_sql(sql: str, thread_id: str) -> str:
    """用 EXPLAIN 检查 SQL 语法，返回错误信息或空字符串"""
    conn = get_connection(thread_id)
    try:
        conn.execute(f"EXPLAIN {sql}")
        return ""
    except Exception as e:
        return str(e)


def get_table_info(thread_id: str, table_name: str) -> str:
    """获取表结构信息（CREATE TABLE 语句）"""
    conn = get_connection(thread_id)
    cursor = conn.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'")
    row = cursor.fetchone()
    return row[0] if row else ""
