"""
Few-shot 示例库：用于 NL2SQL Agent 的 Prompt 注入。
每条示例包含：中文问题场景 + 对应的 SQL 语句。
Agent 会根据用户问题动态选择最相似的 3-5 条示例注入 Prompt。
"""

FEW_SHOT_EXAMPLES = [
    {
        "scenario": "查询某个区域各品类的销售额汇总",
        "question": "华东区各品类的销售额是多少？",
        "keywords": ["区域", "品类", "销售额", "汇总", "地区"],
        "sql": """
SELECT Category, SUM(Sales) AS TotalSales
FROM {table_name}
WHERE Region = 'East'
GROUP BY Category
ORDER BY TotalSales DESC
""",
    },
    {
        "scenario": "查询某个品类下各子品类的销售情况",
        "question": "家具品类下面各个子品类的销售额和利润？",
        "keywords": ["子品类", "品类", "利润", "细分"],
        "sql": """
SELECT SubCategory, SUM(Sales) AS TotalSales, SUM(Profit) AS TotalProfit
FROM {table_name}
WHERE Category = 'Furniture'
GROUP BY SubCategory
ORDER BY TotalSales DESC
""",
    },
    {
        "scenario": "按月份查看销售额趋势",
        "question": "2023年每个月的销售额趋势是怎样的？",
        "keywords": ["月份", "趋势", "时间", "按时间"],
        "sql": """
SELECT strftime('%Y-%m', OrderDate) AS Month, SUM(Sales) AS TotalSales
FROM {table_name}
WHERE strftime('%Y', OrderDate) = '2023'
GROUP BY Month
ORDER BY Month
""",
    },
    {
        "scenario": "查询TOP N的客户或产品",
        "question": "销售额最高的10个客户是哪些？",
        "keywords": ["TOP", "最高", "排名", "前", "前十"],
        "sql": """
SELECT CustomerName, SUM(Sales) AS TotalSales, COUNT(DISTINCT OrderID) AS OrderCount
FROM {table_name}
GROUP BY CustomerName
ORDER BY TotalSales DESC
LIMIT 10
""",
    },
    {
        "scenario": "对比不同地区的利润和折扣",
        "question": "各个区域的平均折扣率和总利润对比？",
        "keywords": ["对比", "利润", "折扣", "区域", "地区"],
        "sql": """
SELECT Region, AVG(Discount) AS AvgDiscount, SUM(Profit) AS TotalProfit,
       SUM(Sales) AS TotalSales
FROM {table_name}
GROUP BY Region
ORDER BY TotalProfit DESC
""",
    },
    {
        "scenario": "查询同比下降情况",
        "question": "办公用品品类今年的销售额同比去年下降了吗？",
        "keywords": ["同比", "下降", "对比", "去年", "今年"],
        "sql": """
SELECT
    strftime('%Y', OrderDate) AS Year,
    SUM(CASE WHEN Category = 'Office Supplies' THEN Sales ELSE 0 END) AS OfficeSales
FROM {table_name}
WHERE strftime('%Y', OrderDate) IN ('2022', '2023')
GROUP BY Year
ORDER BY Year
""",
    },
    {
        "scenario": "查询某个时间段的订单数量",
        "question": "2023年Q4华东区有多少个订单？",
        "keywords": ["订单", "数量", "季度", "Q4"],
        "sql": """
SELECT COUNT(DISTINCT OrderID) AS OrderCount, SUM(Sales) AS TotalSales
FROM {table_name}
WHERE Region = 'East'
  AND OrderDate >= '2023-10-01'
  AND OrderDate < '2024-01-01'
""",
    },
    {
        "scenario": "多维度分组分析",
        "question": "按区域和品类两个维度看销售额和利润情况？",
        "keywords": ["多维", "分组", "交叉", "维度"],
        "sql": """
SELECT Region, Category, SUM(Sales) AS TotalSales, SUM(Profit) AS TotalProfit,
       COUNT(DISTINCT OrderID) AS OrderCount
FROM {table_name}
GROUP BY Region, Category
ORDER BY Region, TotalSales DESC
""",
    },
]


def get_all_examples() -> list[dict]:
    """获取所有 Few-shot 示例"""
    return FEW_SHOT_EXAMPLES


def match_examples(question: str, top_k: int = 5) -> list[dict]:
    """
    根据用户问题关键词，动态匹配最相似的 Few-shot 示例。
    简单实现：计算关键词命中数，取 top_k。
    """
    scored = []
    for ex in FEW_SHOT_EXAMPLES:
        score = sum(1 for kw in ex["keywords"] if kw in question)
        scored.append((score, ex))

    # 按匹配度降序，取 top_k
    scored.sort(key=lambda x: x[0], reverse=True)
    return [ex for score, ex in scored[:top_k] if score > 0] or FEW_SHOT_EXAMPLES[:3]
