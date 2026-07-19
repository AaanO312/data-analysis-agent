import pandas as pd
import numpy as np
import json
import plotly.graph_objects as go
import plotly.express as px
from utils.logger import logger


# ==================== 数据分析 ====================

def analyze_data(rows: list[dict], columns: list[str]) -> dict:
    """
    对查询结果做自动数据分析。
    返回：summary, top_n, trend, anomaly, correlation
    """
    if not rows:
        return {"summary": "查询结果为空", "top_n": "", "trend": "", "anomaly": "", "correlation": ""}

    df = pd.DataFrame(rows, columns=columns)
    logger.info(f"[DataTools] 分析数据: {len(df)} 行, {len(columns)} 列")

    result = {}

    # 1. 基本统计摘要
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    summary_parts = []
    for col in numeric_cols:
        summary_parts.append(
            f"{col}: 总和={df[col].sum():.2f}, 均值={df[col].mean():.2f}, "
            f"最大值={df[col].max():.2f}, 最小值={df[col].min():.2f}"
        )
    result["summary"] = "\n".join(summary_parts) if summary_parts else "无数值列"

    # 2. TOP N
    if numeric_cols and len(df) > 1:
        sort_col = numeric_cols[0]
        top_df = df.nlargest(min(5, len(df)), sort_col)
        label_cols = [c for c in columns if c not in numeric_cols]
        if label_cols:
            top_items = top_df[[label_cols[0], sort_col]].to_dict("records")
        else:
            top_items = top_df[[sort_col]].to_dict("records")
        result["top_n"] = json.dumps(top_items, ensure_ascii=False, default=str)
    else:
        result["top_n"] = ""

    # 3. 趋势检测
    date_col = _find_date_column(df)
    if date_col and numeric_cols:
        df_sorted = df.sort_values(date_col)
        trend_parts = []
        for nc in numeric_cols[:2]:
            values = df_sorted[nc].values
            if len(values) >= 2:
                change = values[-1] - values[0]
                pct = (change / values[0] * 100) if values[0] != 0 else 0
                direction = "上升" if change > 0 else "下降"
                trend_parts.append(f"{nc}: 从 {values[0]:.2f} 到 {values[-1]:.2f}, {direction} {abs(pct):.1f}%")
        result["trend"] = "\n".join(trend_parts) if trend_parts else ""
    else:
        result["trend"] = ""

    # 4. 异常值检测（Z-score）
    if numeric_cols and len(df) >= 3:
        anomaly_parts = []
        for col in numeric_cols[:3]:
            mean_val = df[col].mean()
            std_val = df[col].std()
            if std_val and std_val > 0:
                z_scores = np.abs((df[col] - mean_val) / std_val)
                outliers = df[z_scores > 2.5]
                if len(outliers) > 0:
                    anomaly_parts.append(f"{col}: 检测到 {len(outliers)} 个异常值 (Z-score > 2.5)")
        result["anomaly"] = "\n".join(anomaly_parts) if anomaly_parts else "未检测到明显异常值"
    else:
        result["anomaly"] = "数据量不足，无法做异常检测"

    # 5. 相关性分析
    if len(numeric_cols) >= 2:
        corr_matrix = df[numeric_cols].corr()
        corr_parts = []
        for i in range(len(numeric_cols)):
            for j in range(i + 1, len(numeric_cols)):
                r = corr_matrix.iloc[i, j]
                if not np.isnan(r):
                    corr_parts.append(f"{numeric_cols[i]} vs {numeric_cols[j]}: r={r:.3f}")
        result["correlation"] = "\n".join(corr_parts[:5]) if corr_parts else ""
    else:
        result["correlation"] = "数值列不足，无法做相关性分析"

    logger.info(f"[DataTools] 分析完成: summary={len(result['summary'])}chars")
    return result


def compute_percentage(rows: list[dict], value_col: str) -> list[dict]:
    """计算占比"""
    df = pd.DataFrame(rows)
    if value_col in df.columns:
        total = df[value_col].sum()
        if total > 0:
            df["Percentage"] = (df[value_col] / total * 100).round(2)
    return df.to_dict("records")


def _find_date_column(df: pd.DataFrame) -> str:
    """自动识别日期列"""
    for col in df.columns:
        col_lower = col.lower()
        if any(kw in col_lower for kw in ["date", "日期", "时间", "month", "year", "day"]):
            return col
    for col in df.columns:
        if df[col].dtype == object:
            try:
                pd.to_datetime(df[col])
                return col
            except (ValueError, TypeError):
                pass
    return ""


# ==================== 图表生成（Plotly 交互式） ====================

# 配色方案（专业商务风格）
COLORS = ["#5470C6", "#91CC75", "#FAC858", "#EE6666", "#73C0DE", "#3BA272", "#FC8452", "#9A60B4"]


def choose_chart_type(rows: list[dict], columns: list[str]) -> str:
    """根据数据特征自动选择图表类型: bar（默认/对比）| line（趋势）| pie（占比，严格限制）| scatter"""
    if not rows or not columns:
        return "bar"

    df = pd.DataFrame(rows, columns=columns)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    category_cols = [c for c in columns if c not in numeric_cols]

    # 日期检测（列名含日期关键词）
    date_kw = ["date", "日期", "时间", "month", "year", "day", "月", "年", "日", "quarter", "qtr"]
    has_date = any(any(kw in c.lower() for kw in date_kw) for c in columns)

    # 时间序列 → 折线图
    if has_date and len(df) > 1:
        return "line"

    # 散点图：2+数值列，无类别，≥3行
    if len(numeric_cols) >= 2 and len(category_cols) == 0 and len(df) >= 3:
        return "scatter"

    # 饼图仅限：2~4行 + 单数值列 + 数值看起来像占比
    if len(category_cols) >= 1 and len(numeric_cols) == 1 and 2 <= len(df) <= 4:
        val_col = numeric_cols[0]
        col_lower = val_col.lower()
        is_pct_col = any(kw in col_lower for kw in ["pct", "percent", "占比", "比例", "share", "ratio", "%"])
        vals = df[val_col].dropna()
        looks_like_pct = is_pct_col or (vals.max() <= 100 and vals.min() >= 0)
        if looks_like_pct:
            return "pie"

    # 默认柱状图
    return "bar"


def generate_chart_json(rows: list[dict], columns: list[str],
                        chart_type: str = None, title: str = "") -> str:
    """
    根据数据生成 Plotly 交互式图表，返回 figure JSON 字符串。
    前端用 plotly.io.from_json() 反序列化后渲染。
    """
    if not rows:
        logger.warning("[Viz] 无数据，跳过图表生成")
        return ""

    df = pd.DataFrame(rows, columns=columns)
    logger.info(f"[Viz] 生成图表: {len(df)}行, 类型={chart_type or 'auto'}")

    if chart_type is None:
        chart_type = choose_chart_type(rows, columns)

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    category_cols = [c for c in columns if c not in numeric_cols]

    try:
        if chart_type == "line":
            fig = _build_line(df, category_cols, numeric_cols, title)
        elif chart_type == "pie":
            fig = _build_pie(df, category_cols, numeric_cols, title)
        elif chart_type == "scatter":
            fig = _build_scatter(df, numeric_cols, title)
        else:
            fig = _build_bar(df, category_cols, numeric_cols, title)

        chart_json = fig.to_json()
        logger.info(f"[Viz] 图表生成成功: {chart_type}, JSON长度={len(chart_json)}")
        return chart_json

    except Exception as e:
        logger.error(f"[Viz] 图表生成失败: {e}")
        return ""


def _common_layout(fig: go.Figure, title: str) -> go.Figure:
    """应用统一的商务风格布局"""
    fig.update_layout(
        title=dict(text=title or "数据分析", font=dict(size=16, color="#333333")),
        plot_bgcolor="#FAFAFA",
        paper_bgcolor="#FFFFFF",
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1, font=dict(size=11),
        ),
        hovermode="x unified",
        font=dict(family="Microsoft YaHei, SimHei, PingFang SC, Noto Sans CJK SC, Arial, sans-serif"),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#E8E8E8", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="#E8E8E8", zeroline=False)
    return fig


def _build_bar(df: pd.DataFrame, category_cols: list[str],
               numeric_cols: list[str], title: str) -> go.Figure:
    """柱状图 — 支持分组柱状图"""
    fig = go.Figure()

    if category_cols:
        labels = df[category_cols[0]].astype(str).tolist()
    else:
        labels = [str(i + 1) for i in range(len(df))]

    for i, col in enumerate(numeric_cols[:3]):
        color = COLORS[i % len(COLORS)]
        fig.add_trace(go.Bar(
            name=col, x=labels, y=df[col].tolist(),
            marker_color=color, text=[f"{v:,.2f}" for v in df[col]],
            textposition="outside", textfont=dict(size=10),
            hovertemplate=f"<b>{col}</b><br>%{{x}}: %{{y:,.2f}}<extra></extra>",
        ))

    fig.update_layout(barmode="group" if len(numeric_cols[:3]) > 1 else "stack")
    return _common_layout(fig, title or "数据对比")


def _build_line(df: pd.DataFrame, category_cols: list[str],
                numeric_cols: list[str], title: str) -> go.Figure:
    """折线图 — 支持多系列"""
    fig = go.Figure()

    if category_cols:
        x_vals = df[category_cols[0]].astype(str).tolist()
    else:
        x_vals = [str(i + 1) for i in range(len(df))]

    for i, col in enumerate(numeric_cols[:3]):
        color = COLORS[i % len(COLORS)]
        fig.add_trace(go.Scatter(
            name=col, x=x_vals, y=df[col].tolist(),
            mode="lines+markers", line=dict(color=color, width=2.5),
            marker=dict(size=7, color=color),
            hovertemplate=f"<b>{col}</b><br>%{{x}}: %{{y:,.2f}}<extra></extra>",
        ))

    return _common_layout(fig, title or "趋势分析")


def _build_pie(df: pd.DataFrame, category_cols: list[str],
               numeric_cols: list[str], title: str) -> go.Figure:
    """饼图 / 环形图"""
    if category_cols:
        labels = df[category_cols[0]].astype(str).tolist()
    else:
        labels = [str(i + 1) for i in range(len(df))]

    values = df[numeric_cols[0]].tolist() if numeric_cols else [1] * len(df)
    # 确保非负
    values = [max(v, 0) for v in values]

    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values,
        hole=0.35,  # 环形图，更现代
        marker=dict(colors=COLORS[:len(labels)]),
        textinfo="percent+label", textfont=dict(size=11),
        hovertemplate="<b>%{label}</b><br>数值: %{value:,.2f}<br>占比: %{percent}<extra></extra>",
    )])

    fig.update_layout(
        title=dict(text=title or "占比分布", font=dict(size=16, color="#333333")),
        margin=dict(l=20, r=20, t=50, b=20),
        font=dict(family="Microsoft YaHei, SimHei, PingFang SC, Noto Sans CJK SC, Arial, sans-serif"),
    )
    return fig


def _build_scatter(df: pd.DataFrame, numeric_cols: list[str], title: str) -> go.Figure:
    """散点图"""
    fig = go.Figure()

    if len(numeric_cols) >= 2:
        fig.add_trace(go.Scatter(
            x=df[numeric_cols[0]].tolist(), y=df[numeric_cols[1]].tolist(),
            mode="markers", marker=dict(size=10, color=COLORS[0], opacity=0.65, line=dict(width=1, color="#fff")),
            hovertemplate=f"<b>{numeric_cols[0]}</b>: %{{x:,.2f}}<br><b>{numeric_cols[1]}</b>: %{{y:,.2f}}<extra></extra>",
        ))
        fig.update_xaxes(title=numeric_cols[0])
        fig.update_yaxes(title=numeric_cols[1])
    else:
        fig.add_trace(go.Scatter(
            y=df[numeric_cols[0]].tolist() if numeric_cols else [],
            mode="markers", marker=dict(size=10, color=COLORS[0], opacity=0.65),
        ))

    return _common_layout(fig, title or "相关性散点图")
