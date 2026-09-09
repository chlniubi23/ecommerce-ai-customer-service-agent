"""Metadata helpers for knowledge document loaders."""

from __future__ import annotations

from pathlib import Path


def infer_knowledge_category(file_path: str, file_name: str = "") -> str:
    """Infer enterprise knowledge category from path and file name."""
    text = " ".join([str(file_path), file_name]).replace("\\", "/").lower()
    mapping = {
        "refund": ["refund", "return", "退款", "退货", "售后"],
        "logistics": ["logistics", "shipping", "delivery", "shipment", "物流", "配送", "发货", "签收"],
        "complaint": ["complaint", "ticket", "投诉", "升级", "主管"],
        "membership": ["membership", "member", "会员", "积分", "成长值"],
        "coupon": ["coupon", "discount", "promotion", "优惠券", "满减", "折扣"],
        "product": ["product", "sku", "商品", "参数", "macbook", "thinkbook", "iphone", "ipad", "airpods", "sony", "rog", "xiaomi"],
        "faq": ["faq", "问答", "常见问题"],
        "sop": ["sop", "客服", "规范", "流程"],
        "policy": ["policy", "agreement", "privacy", "规则", "政策", "协议", "隐私"],
        "operation": ["operation", "campaign", "pricing", "inventory", "运营", "活动", "价格", "库存"],
    }
    for category, keywords in mapping.items():
        if any(keyword in text for keyword in keywords):
            return category
    parts = [part.lower() for part in Path(file_path).parts]
    for part in reversed(parts):
        if part in mapping:
            return part
    return "other"

