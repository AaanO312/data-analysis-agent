"""通用数据分析 Agent — Streamlit 前端（纯展示层，通过 HTTP 调后端）"""
import streamlit as st
import requests
import pandas as pd
import plotly.io as pio
import os

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="通用数据分析 Agent", page_icon="", layout="wide")
st.title(" 通用数据分析 Agent")
st.caption("上传 CSV → 自然语言提问 → AI 自动查数据、画图、给洞察。后端 FastAPI + LangGraph 驱动。")

# ==================== Session 初始化 ====================
if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = None

if "data_loaded" not in st.session_state:
    st.session_state["data_loaded"] = False

if "table_name" not in st.session_state:
    st.session_state["table_name"] = ""

if "columns" not in st.session_state:
    st.session_state["columns"] = []

if "data_dict" not in st.session_state:
    st.session_state["data_dict"] = ""

if "messages" not in st.session_state:
    st.session_state["messages"] = []


def render_chart(chart_json: str):
    """渲染 Plotly 交互式图表"""
    if chart_json:
        try:
            fig = pio.from_json(chart_json)
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.warning("图表渲染失败")


# ==================== 侧边栏：上传区 ====================
with st.sidebar:
    st.header(" 数据上传")

    uploaded_file = st.file_uploader("上传 CSV 文件", type=["csv"])
    use_sample = st.button("  使用示例数据", use_container_width=True)

    if uploaded_file:
        with st.spinner(" 上传并解析中..."):
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "text/csv")}
                resp = requests.post(f"{BACKEND_URL}/upload", files=files, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state["thread_id"] = data["thread_id"]
                    st.session_state["data_loaded"] = True
                    st.session_state["table_name"] = data["table_name"]
                    st.session_state["columns"] = data["columns"]
                    st.session_state["data_dict"] = data["data_dict"]
                    st.session_state["messages"] = []
                    st.success(f"✅ 加载完成！{len(data['columns'])} 列, {data['row_count']} 行")
                else:
                    st.error(f"上传失败: {resp.text}")
            except requests.exceptions.ConnectionError:
                st.error(" 无法连接后端，请先启动 FastAPI: uvicorn backend.main:app --reload")

    if use_sample:
        sample_path = os.path.join(os.path.dirname(__file__), "..", "sample_data", "superstore_sales.csv")
        if os.path.exists(sample_path):
            with st.spinner(" 上传示例数据中..."):
                try:
                    with open(sample_path, "rb") as f:
                        files = {"file": ("superstore_sales.csv", f.read(), "text/csv")}
                        resp = requests.post(f"{BACKEND_URL}/upload", files=files, timeout=30)
                        if resp.status_code == 200:
                            data = resp.json()
                            st.session_state["thread_id"] = data["thread_id"]
                            st.session_state["data_loaded"] = True
                            st.session_state["table_name"] = data["table_name"]
                            st.session_state["columns"] = data["columns"]
                            st.session_state["data_dict"] = data["data_dict"]
                            st.session_state["messages"] = []
                            st.success(f"✅ 示例数据加载完成！{data['row_count']} 条记录")
                        else:
                            st.error(f"加载失败: {resp.text}")
                except requests.exceptions.ConnectionError:
                    st.error(" 无法连接后端，请先启动 FastAPI")
        else:
            st.error("示例数据文件不存在")

    # 数据字典展示
    if st.session_state["data_loaded"]:
        st.divider()
        st.subheader(" 数据字典")
        with st.expander("查看字段信息", expanded=False):
            st.text(st.session_state["data_dict"][:2000])
        st.caption(f"表名: `{st.session_state['table_name']}`")
        st.caption(f"列: {', '.join(st.session_state['columns'][:10])}"
                   f"{'...' if len(st.session_state['columns']) > 10 else ''}")

    st.divider()
    if st.button(" 清空对话"):
        st.session_state["messages"] = []
        st.rerun()

    # 后端状态（先 fetch 再渲染，避免 expander 折叠时不执行）
    backend_online = False
    metrics_data = None
    try:
        h = requests.get(f"{BACKEND_URL}/health", timeout=3)
        backend_online = h.status_code == 200
        if backend_online:
            metrics_data = requests.get(f"{BACKEND_URL}/metrics", timeout=3).json()
    except Exception:
        pass

    with st.expander(" 后端状态", expanded=False):
        if backend_online and metrics_data:
            st.success("在线")
            c = metrics_data["chat"]
            l = metrics_data["llm"]
            col1, col2 = st.columns(2)
            col1.metric("请求", c["total"])
            col2.metric("耗时", f"{c['avg_duration_ms']:.0f}ms")
            col1, col2 = st.columns(2)
            col1.metric("LLM", l["calls"])
            col2.metric("错误率", f"{l['error_rate']*100:.1f}%")
            st.caption(f"[API 文档]({BACKEND_URL}/docs)")
        elif backend_online:
            st.success("在线")
        else:
            st.error("离线")


# ==================== 主区域：对话 ====================
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and isinstance(msg.get("content"), dict):
            c = msg["content"]
            if c.get("sql_text"):
                with st.expander(" 生成的 SQL", expanded=False):
                    st.code(c["sql_text"], language="sql")
            if c.get("data_table"):
                st.dataframe(pd.DataFrame(c["data_table"]), use_container_width=True)
            if c.get("chart_json"):
                render_chart(c["chart_json"])
            if c.get("insight"):
                st.markdown("###  洞察与建议")
                st.info(c["insight"])
        else:
            st.markdown(msg["content"])

# 输入框
if st.session_state["data_loaded"]:
    question = st.chat_input("  输入你的问题，如'华东区哪个品类销售额最高？'")
else:
    question = st.chat_input(" 请先上传数据文件或加载示例数据")

if question and st.session_state["data_loaded"]:
    st.session_state["messages"].append({"role": "user", "content": question})

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner(" AI 分析中…"):
            try:
                payload = {"question": question, "thread_id": st.session_state["thread_id"]}
                resp = requests.post(f"{BACKEND_URL}/chat", json=payload, timeout=120)

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("sql_text"):
                        with st.expander(" 生成的 SQL", expanded=False):
                            st.code(data["sql_text"], language="sql")
                    if data.get("data_table"):
                        st.dataframe(pd.DataFrame(data["data_table"]), use_container_width=True)
                    if data.get("chart_json"):
                        render_chart(data["chart_json"])
                    if data.get("insight"):
                        st.markdown("###  洞察与建议")
                        st.info(data["insight"])
                    st.caption("✅ 分析完成")

                    st.session_state["messages"].append({
                        "role": "assistant",
                        "content": {
                            "sql_text": data.get("sql_text", ""),
                            "data_table": data.get("data_table", []),
                            "chart_json": data.get("chart_json", ""),
                            "insight": data.get("insight", ""),
                        },
                    })
                else:
                    err = resp.json().get("detail", resp.text) if resp.text else "未知错误"
                    st.error(f"请求失败 ({resp.status_code}): {err}")

            except requests.exceptions.ConnectionError:
                st.error(" 无法连接后端")
            except requests.exceptions.Timeout:
                st.error(" 请求超时")
            except Exception as e:
                st.error(f"请求异常: {type(e).__name__}: {e}")
