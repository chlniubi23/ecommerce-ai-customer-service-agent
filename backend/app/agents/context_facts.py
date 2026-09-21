"""前端页面快照事实解析（多来源信息整合 - 兜底来源）

职责：
- 从完整用户消息（含前端注入的 [系统补充上下文] 段）解析结构化事实行
- 供协调器 LLM 综合输入与 enhanced_flow 的页面快照兜底使用

PII 边界（红线）：
- 解析出的事实仅进入本轮 LLM 上下文，不得新增日志打印或持久化；
- 任何解析异常都不得中断主流程（返回空 dict）。

事实行格式来自前端 buildContextPrompt（保持前缀匹配，不重新发明解析）：
- 当前订单：{order_id} / 订单 {status} / 支付 {status} / 配送 {status} / 金额 {amount}
- 当前订单商品：...
- 当前商品：...
- 物流：{carrier} / {tracking_no} / {status} / {location}
- 物流轨迹：{timeline...}
- 退款：{refund_id} / {audit_status} / {refund_status}
- 当前投诉：...
"""

from __future__ import annotations

SYSTEM_CONTEXT_MARKER = "[系统补充上下文"

# 事实类别 → 行前缀（与前端 buildContextPrompt 的行格式一一对应）
FRONTEND_FACT_PREFIXES: dict[str, str] = {
    "order": "当前订单：",
    "order_items": "当前订单商品：",
    "product": "当前商品：",
    "logistics": "物流：",
    "logistics_timeline": "物流轨迹：",
    "refund": "退款：",
    "complaint": "当前投诉：",
}

# 契约维度 → 可用作兜底的事实类别（enhanced_flow 完整性契约使用）
DIMENSION_FACT_KEYS: dict[str, list[str]] = {
    "logistics": ["logistics", "logistics_timeline"],
    "order_status": ["order"],
    "refund": ["refund"],
    "complaint": ["complaint"],
}


def extract_context_facts(full_message: str) -> dict[str, str]:
    """从完整消息的 [系统补充上下文] 段解析结构化事实行。

    Returns:
        dict: {事实类别: 完整行文本}；解析不到或异常返回空 dict。
    """
    try:
        if not full_message or SYSTEM_CONTEXT_MARKER not in full_message:
            return {}
        section = full_message.split(SYSTEM_CONTEXT_MARKER, 1)[1]
        facts: dict[str, str] = {}
        for raw_line in section.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            for key, prefix in FRONTEND_FACT_PREFIXES.items():
                if line.startswith(prefix) and key not in facts:
                    facts[key] = line
        return facts
    except Exception:
        return {}


def format_snapshot_section(facts: dict[str, str]) -> list[str]:
    """构建注入 LLM 综合输入的快照段（协调器 A1 使用）。"""
    lines: list[str] = []
    for key in FRONTEND_FACT_PREFIXES:
        if key in facts:
            lines.append(facts[key])
    return lines


def snapshot_lines_for_dimensions(facts: dict[str, str], dimensions: list[str]) -> list[str]:
    """按契约维度取快照兜底行（enhanced_flow A3 使用）。"""
    lines: list[str] = []
    seen: set[str] = set()
    for dimension in dimensions:
        for key in DIMENSION_FACT_KEYS.get(dimension, []):
            fact = facts.get(key)
            if fact and key not in seen:
                seen.add(key)
                lines.append(f"[页面快照补充] {fact}（来源：用户当前页面）")
    return lines
