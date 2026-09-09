"""
Intent 意图分类 Schema

职责：
- 定义电商客服系统支持的所有意图类型
- 定义 Intent 分类结果的结构化模型
- 作为 Agent Router 的决策输入

设计理念：
- Intent 是 Agent 决策系统的核心数据单元
- 用户输入经过 Classifier 后，变成结构化的 IntentResult
- 后续所有路由、Flow 选择、Prompt 策略都基于 IntentResult
- 枚举化确保类型安全，confidence 确保决策质量

架构位置：
- schemas/ 层，被 agents/classifier.py 生成，被 router/ 消费
- 前端 types/intent.ts 需要与此文件保持一致

为什么企业项目需要这样设计：
1. 枚举化 intent：避免字符串拼写错误，支持 IDE 补全和静态检查
2. confidence 置信度：低置信度时可走 fallback / 人工确认流程
3. 可扩展：新增业务场景只需加一个枚举值 + 对应 Flow

扩展规划：
- Phase 3 (RAG): 增加 KNOWLEDGE_QUERY 意图，命中时走 RAG 检索
- Phase 4 (LangGraph): IntentResult 作为 Graph State 的初始节点输入
- Phase 5 (Memory): 结合历史对话做多轮意图追踪
"""

from enum import Enum
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """
    电商客服意图类型枚举

    定义系统能识别的所有用户意图。
    每个意图对应一个独立的 Flow Handler。

    命名规范：大写下划线（Python 枚举标准）
    值：小写下划线（JSON 传输 / 前端对齐）

    Values:
        REFUND: 退款/退货相关
            用户示例: "我要退款", "怎么申请退货", "退款多久到账"
            对应 Flow: flows/refund.py

        LOGISTICS_QUERY: 物流查询相关
            用户示例: "我的快递到哪了", "物流信息查询", "什么时候发货"
            对应 Flow: flows/logistics.py

        ORDER_QUERY: 订单查询相关
            用户示例: "查一下我的订单", "订单状态", "我买了什么"
            对应 Flow: flows/order.py

        COUPON_QUERY: 优惠券/促销相关
            用户示例: "有什么优惠", "优惠券怎么用", "满减活动"
            对应 Flow: flows/coupon.py

        PRODUCT_QUERY: 商品咨询相关
            用户示例: "这个商品有货吗", "尺码推荐", "商品参数"
            对应 Flow: flows/product.py

        GENERAL: 通用/闲聊/兜底
            用户示例: "你好", "谢谢", "在吗", 无法归类的输入
            对应 Flow: flows/general.py

    扩展规划：
    - Phase 3: KNOWLEDGE_QUERY = "knowledge_query" (知识库检索)
    - Phase 4: COMPLAINT = "complaint" (投诉处理)
    - Phase 5: MULTI_INTENT = "multi_intent" (复合意图)
    """
    REFUND = "refund"
    LOGISTICS_QUERY = "logistics_query"
    ORDER_QUERY = "order_query"
    COUPON_QUERY = "coupon_query"
    PRODUCT_QUERY = "product_query"
    KNOWLEDGE_QUERY = "knowledge_query"
    TICKET = "ticket"
    HUMAN_TRANSFER = "human_transfer"
    GENERAL = "general"


# Intent 类型的中文描述映射
# 用于日志打印、调试输出、前端展示
INTENT_DESCRIPTIONS: dict[IntentType, str] = {
    IntentType.REFUND: "退款/退货",
    IntentType.LOGISTICS_QUERY: "物流查询",
    IntentType.ORDER_QUERY: "订单查询",
    IntentType.COUPON_QUERY: "优惠券/促销",
    IntentType.PRODUCT_QUERY: "商品咨询",
    IntentType.TICKET: "创建工单/售后",
    IntentType.HUMAN_TRANSFER: "转人工客服",
    IntentType.GENERAL: "通用/闲聊",
}


class IntentResult(BaseModel):
    """
    Intent 分类结果

    由 agents/classifier.py 生成，作为 Router 的决策输入。

    Attributes:
        intent: 识别出的意图类型
        confidence: 置信度 (0.0 ~ 1.0)
            - >= 0.8: 高置信，直接路由到对应 Flow
            - 0.5 ~ 0.8: 中置信，可考虑确认或走通用 Flow
            - < 0.5: 低置信，走 GENERAL 兜底
        raw_input: 用户原始输入文本（保留用于后续 RAG / Memory）

    扩展规划：
    - Phase 4: 增加 sub_intent 字段（细分意图）
    - Phase 5: 增加 intent_history 字段（多轮意图追踪）
    """
    intent: IntentType = Field(
        ...,
        description="识别出的意图类型"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="分类置信度，0.0 到 1.0"
    )
    raw_input: str = Field(
        ...,
        description="用户原始输入文本"
    )


# 置信度阈值常量
# 集中管理，避免硬编码散落在各处
CONFIDENCE_HIGH: float = 0.8
CONFIDENCE_LOW: float = 0.5

# Phase 8 Stage 3: independent Knowledge Agent intent.
INTENT_DESCRIPTIONS[IntentType.KNOWLEDGE_QUERY] = "知识库问答"
