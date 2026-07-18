import pandas as pd
import numpy as np
import json
import io
import base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from utils.logger import logger


# ==================== 中文字体设置 ====================

def _setup_chinese_font():
    """设置中文字体，fallback 到可用字体"""
    chinese_fonts = ["SimHei", "Microsoft YaHei", "WenQuanYi Micro Hei",
                     "Noto Sans CJK SC", "Source Han Sans SC", "PingFang SC"]
    available = {f.name for f in fm.fontManager.ttflist}

    for font in chinese_fonts:
        if font in available:
            plt.rcParams["font.sans-serif"] = [font, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            logger.info(f"[Viz] 使用中文字体: {font}")
            return font

    plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    logger.warning("[Viz] 未找到中文字体，图表中文可能显示为方块。")
    return "DejaVu Sans"


_setup_chinese_font()


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


# ==================== 图表生成 ====================

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

    # 饼图仅限：2~4行 + 单数值列 + 数值看起来像占比（列名含 pct/percent/占比/比例，或值在0~100之间）
    if len(category_cols) >= 1 and len(numeric_cols) == 1 and 2 <= len(df) <= 4:
        val_col = numeric_cols[0]
        col_lower = val_col.lower()
        is_pct_col = any(kw in col_lower for kw in ["pct", "percent", "占比", "比例", "share", "ratio", "%"])
        vals = df[val_col].dropna()
        looks_like_pct = is_pct_col or (vals.max() <= 100 and vals.min() >= 0)
        if looks_like_pct:
            return "pie"

    # 默认柱状图（对比/排名/单行，最通用）
    return "bar"


def generate_chart_base64(rows: list[dict], columns: list[str],
                          chart_type: str = None, title: str = "") -> str:
    """根据数据生成图表，返回 base64 编码字符串"""
    if not rows:
        logger.warning("[Viz] 无数据，跳过图表生成")
        return ""

    df = pd.DataFrame(rows, columns=columns)
    logger.info(f"[Viz] 生成图表: {len(df)}行, 类型={chart_type or 'auto'}")

    if chart_type is None:
        chart_type = choose_chart_type(rows, columns)

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    category_cols = [c for c in columns if c not in numeric_cols]

    # 紧凑尺寸，适配屏幕
    fig, ax = plt.subplots(figsize=(7, 3.5))

    try:
        if chart_type == "line":
            _draw_line(ax, df, category_cols, numeric_cols, title)
        elif chart_type == "pie":
            _draw_pie(ax, df, category_cols, numeric_cols, title)
        elif chart_type == "scatter":
            _draw_scatter(ax, df, numeric_cols, title)
        else:
            _draw_bar(ax, df, category_cols, numeric_cols, title)

        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode("utf-8")
        buf.close()
        plt.close(fig)

        logger.info(f"[Viz] 图表生成成功: {chart_type}, base64长度={len(img_base64)}")
        return img_base64

    except Exception as e:
        logger.error(f"[Viz] 图表生成失败: {e}")
        plt.close(fig)
        return ""


def _draw_bar(ax, df, category_cols, numeric_cols, title):
    if category_cols:
        labels = df[category_cols[0]].astype(str).values
    else:
        labels = df.index.astype(str).values
    x = np.arange(len(labels))
    width = 0.8 / max(len(numeric_cols[:3]), 1)
    for i, col in enumerate(numeric_cols[:3]):
        ax.bar(x + i * width, df[col].values, width, label=col)
    ax.set_xticks(x + width * (len(numeric_cols[:3]) - 1) / 2)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
    ax.set_title(title or "数据对比", fontsize=14, fontweight="bold")
    ax.legend(loc="best")
    ax.grid(axis="y", alpha=0.3)


def _draw_line(ax, df, category_cols, numeric_cols, title):
    if category_cols:
        x = df[category_cols[0]].astype(str).values
    else:
        x = np.arange(len(df))
    for col in numeric_cols[:3]:
        ax.plot(x, df[col].values, marker="o", linewidth=2, label=col, markersize=5)
    ax.set_title(title or "趋势分析", fontsize=14, fontweight="bold")
    ax.legend(loc="best")
    ax.grid(alpha=0.3)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=9)


def _draw_pie(ax, df, category_cols, numeric_cols, title):
    if category_cols:
        labels = df[category_cols[0]].astype(str).values
    else:
        labels = [str(i) for i in range(len(df))]
    values = df[numeric_cols[0]].values if numeric_cols else np.ones(len(df))
    values = np.maximum(values, 0)
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct="%1.1f%%",
        startangle=90, pctdistance=0.75
    )
    for t in autotexts:
        t.set_fontsize(9)
    ax.set_title(title or "占比分布", fontsize=14, fontweight="bold")


def _draw_scatter(ax, df, numeric_cols, title):
    if len(numeric_cols) >= 2:
        ax.scatter(df[numeric_cols[0]].values, df[numeric_cols[1]].values,
                   alpha=0.6, s=50)
        ax.set_xlabel(numeric_cols[0])
        ax.set_ylabel(numeric_cols[1])
    ax.set_title(title or "相关性散点图", fontsize=14, fontweight="bold")
    ax.grid(alpha=0.3)
