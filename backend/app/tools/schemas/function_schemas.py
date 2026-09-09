"""
OpenAI Function Calling Schemas

为所有 Tool 定义标准化的 OpenAI Function Calling Schema。
每个 Schema 包含 name、description、parameters。

用途：
1. LLM Function Calling（Tool Selection）
2. 参数校验
3. Tool Registry metadata
4. 前端 Debug Panel 展示
"""

from typing import Any

# ========== 所有 Tool 的 Schema 定义 ==========

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "query_order": {
        "name": "query_order",
        "description": "查询订单详细信息，包括商品名称、价格、下单时间、订单状态",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "订单号（纯数字，如 123456）",
                },
            },
            "required": ["order_id"],
        },
    },
    "query_logistics": {
        "name": "query_logistics",
        "description": "查询订单物流信息，包括物流状态、当前位置、预计送达时间、快递公司",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "订单号（纯数字，如 123456）",
                },
            },
            "required": ["order_id"],
        },
    },
    "logistics_query": {
        "name": "logistics_query",
        "description": "Query shipment status, carrier, tracking number and logistics timeline from the business database.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Order id, for example ORD100001.",
                },
            },
            "required": ["order_id"],
        },
    },
    "query_refund": {
        "name": "query_refund",
        "description": "查询退款状态或创建退款申请，返回退款进度、到账时间、审核状态",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "订单号（纯数字，如 123456）",
                },
                "reason": {
                    "type": "string",
                    "description": "退款原因（可选，如：质量问题、不想要了）",
                },
            },
            "required": ["order_id"],
        },
    },
    "refund_apply": {
        "name": "refund_apply",
        "description": "Create a refund request or query the existing refund state from the business database.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Order id, for example ORD100001.",
                },
                "reason": {
                    "type": "string",
                    "description": "Refund reason.",
                },
            },
            "required": ["order_id"],
        },
    },
    "create_ticket": {
        "name": "create_ticket",
        "description": "创建客服工单，用于记录用户问题并分配给客服人员跟进处理",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "问题描述",
                },
                "category": {
                    "type": "string",
                    "description": "工单分类（如：售后、物流、投诉）",
                    "enum": ["售后", "物流", "投诉", "咨询", "其他"],
                },
            },
            "required": ["description"],
        },
    },
    "complaint_create": {
        "name": "complaint_create",
        "description": "Create a complaint record in the business database for Complaint Agent workflows.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Complaint content.",
                },
                "complaint_type": {
                    "type": "string",
                    "description": "Complaint type, such as logistics, refund, service or product_quality.",
                },
                "order_id": {
                    "type": "string",
                    "description": "Related order id.",
                },
                "user_id": {
                    "type": "string",
                    "description": "Related user id.",
                },
            },
            "required": ["content"],
        },
    },
    "transfer_human": {
        "name": "transfer_human",
        "description": "转接人工客服，查询当前排队人数和预计等待时间",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "转人工原因（可选）",
                },
            },
            "required": [],
        },
    },
    "query_inventory": {
        "name": "query_inventory",
        "description": "查询商品库存信息，包括是否有货、剩余数量、商品规格",
        "parameters": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "商品名称或关键词（如：耳机、充电宝）",
                },
            },
            "required": ["product_name"],
        },
    },
    "knowledge_search": {
        "name": "knowledge_search",
        "description": "Search enterprise knowledge base documents, policies, SOPs, FAQ and product documentation through RAG retrieval.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Knowledge question or search query.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum chunks to retrieve.",
                },
                "min_score": {
                    "type": "number",
                    "description": "Minimum similarity score.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional knowledge category.",
                    "enum": ["policy", "product", "faq", "sop", "logistics", "refund", "complaint", "membership", "other"],
                },
            },
            "required": ["query"],
        },
    },
}


def get_tool_schema(tool_name: str) -> dict | None:
    """获取单个 Tool 的 Schema"""
    return TOOL_SCHEMAS.get(tool_name)


def get_all_schemas() -> dict[str, dict]:
    """获取所有 Schema"""
    return TOOL_SCHEMAS.copy()


def get_openai_functions(tool_names: list[str] | None = None) -> list[dict]:
    """
    获取 OpenAI Function Calling 格式的 functions 列表

    Args:
        tool_names: 指定的工具名列表，None 表示全部

    Returns:
        OpenAI functions 格式的列表
    """
    if tool_names is None:
        tool_names = list(TOOL_SCHEMAS.keys())

    functions = []
    for name in tool_names:
        schema = TOOL_SCHEMAS.get(name)
        if schema:
            functions.append({
                "type": "function",
                "function": schema,
            })
    return functions
