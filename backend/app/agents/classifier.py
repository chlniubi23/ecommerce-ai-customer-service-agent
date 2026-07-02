"""
Intent Classifier - 意图分类器

职责：
- 接收用户原始输入
- 调用 LLM 做语义级意图分类
- 返回结构化的 IntentResult

设计理念：
- 使用 LLM 做分类，而非 keyword matching
  → 语义理解能力强，"不想要了能退吗" 也能识别为 refund
- 强制 LLM 输出 JSON，确保结果可解析
- JSON 解析失败时 fallback 到 GENERAL，Agent 不会崩溃
- Prompt 从 prompts/router.py 引入，不写死在本文件

架构位置：
- agents/ 层，Agent 决策链的第一个环节
- 被 agents/agent.py 调用
- 调用 services/llm.py 底层 LLM 服务（复用同一个 OpenAI 客户端）

数据流：
  用户输入 → classifier.classify() → IntentResult → router → flow

为什么企业项目需要这样设计：
1. 分类器独立模块：可单独替换（换模型、换规则引擎）不影响其他层
2. 容错设计：LLM 输出不稳定时不会导致系统崩溃
3. 日志追踪：记录每次分类结果，方便监控分类质量

扩展规划：
- Phase 3: 支持多模型 ensemble（多个模型投票提升准确率）
- Phase 4: 结合对话历史做多轮意图追踪
- Phase 5: 分类结果持久化，用于分析用户意图分布
"""

import json
import logging
from openai import AsyncOpenAI
from app.core.config import get_settings
from app.prompts.router import ROUTER_SYSTEM_PROMPT
from app.schemas.intent import IntentType, IntentResult, CONFIDENCE_LOW
from app.agents.complaint_intent import (
    is_explicit_create_request,
    is_followup_request,
    user_visible_input as _user_visible_input,
)

logger = logging.getLogger(__name__)

# 复用全局配置和 OpenAI 客户端
settings = get_settings()
client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)


async def classify_intent(user_input: str) -> IntentResult:
    """
    对用户输入进行意图分类

    调用 LLM，使用 Router Prompt 指导其输出结构化 JSON。
    解析 JSON 得到 intent 和 confidence。

    Args:
        user_input: 用户原始输入文本

    Returns:
        IntentResult: 包含 intent 类型、置信度和原始输入

    容错策略：
    - LLM 返回非 JSON → fallback GENERAL, confidence=0.3
    - intent 值不在枚举中 → fallback GENERAL, confidence=0.3
    - API 调用异常 → fallback GENERAL, confidence=0.0
    """
    visible_input = _user_visible_input(user_input)
    # 路由规则用完整文本（前端把'本轮任务'和订单号写在系统上下文里）；
    # 知识库规则用可见文本，避免系统上下文里的业务词误判。
    rule_intent = _classify_business_intent_by_rule(user_input) or _classify_knowledge_intent_by_rule(visible_input)
    if rule_intent:
        return IntentResult(
            intent=rule_intent,
            confidence=0.92,
            raw_input=user_input,
        )

    try:
        logger.info(f"开始意图分类，输入: {visible_input[:50]}...")

        # 调用 LLM 做分类
        # temperature=0.1: 分类任务需要确定性输出，降低随机性
        # max_tokens=100: 分类结果很短，限制输出长度避免浪费
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": visible_input},
            ],
            temperature=0.1,
            max_tokens=100,
        )

        raw_output = response.choices[0].message.content or ""
        logger.debug(f"LLM 分类原始输出: {raw_output}")

        # 解析 JSON 输出
        result = _parse_classifier_output(raw_output, visible_input)

        logger.info(
            f"意图分类完成: intent={result.intent.value}, "
            f"confidence={result.confidence:.2f}"
        )
        return result

    except Exception as e:
        # API 调用失败，走兜底
        logger.error(f"意图分类异常: {str(e)}", exc_info=True)
        return IntentResult(
            intent=IntentType.GENERAL,
            confidence=0.0,
            raw_input=visible_input,
        )


def _parse_classifier_output(raw_output: str, user_input: str) -> IntentResult:
    """
    解析 LLM 的分类输出

    尝试从 LLM 返回的文本中提取 JSON，
    解析 intent 和 confidence 字段。

    Args:
        raw_output: LLM 返回的原始文本
        user_input: 用户原始输入（用于填充 raw_input 字段）

    Returns:
        IntentResult: 解析后的分类结果

    容错逻辑：
    1. 尝试直接 json.loads
    2. 如果失败，尝试提取 {} 包裹的内容再解析
    3. 如果仍失败，返回 GENERAL fallback
    """
    try:
        # 尝试直接解析
        data = json.loads(raw_output.strip())
    except json.JSONDecodeError:
        # 尝试提取 JSON 片段（LLM 可能包裹了 markdown ```json ... ```）
        try:
            start = raw_output.index("{")
            end = raw_output.rindex("}") + 1
            data = json.loads(raw_output[start:end])
        except (ValueError, json.JSONDecodeError):
            logger.warning(f"无法解析分类输出: {raw_output}")
            return IntentResult(
                intent=IntentType.GENERAL,
                confidence=CONFIDENCE_LOW * 0.6,
                raw_input=user_input,
            )

    # 验证 intent 字段
    intent_str = data.get("intent", "general")
    try:
        intent = IntentType(intent_str)
    except ValueError:
        logger.warning(f"未知 intent 值: {intent_str}，fallback to GENERAL")
        intent = IntentType.GENERAL

    # 验证 confidence 字段
    confidence = data.get("confidence", 0.5)
    if not isinstance(confidence, (int, float)):
        confidence = 0.5
    confidence = max(0.0, min(1.0, float(confidence)))

    return IntentResult(
        intent=intent,
        confidence=confidence,
        raw_input=user_input,
    )


def _classify_business_intent_by_rule(user_input: str) -> IntentType | None:
    """Route explicit assistant business instructions before LLM classification.

    路由指令（本轮任务/Agent 名）由前端写在 [系统补充上下文] 中，属于可信指令，
    必须基于完整文本匹配；只有"用户是否明确要创建投诉"才用可见文本，避免误建。
    """
    text = user_input.strip().lower()
    if not text:
        return None
    visible_input = _user_visible_input(user_input)

    if "本轮任务：物流查询" in user_input or "logisticsagent" in text or "logistics_query" in text:
      return IntentType.LOGISTICS_QUERY
    if "本轮任务：订单查询" in user_input or "orderagent" in text or "query_order" in text:
      return IntentType.ORDER_QUERY
    if "本轮任务：退款/售后" in user_input or "refundagent" in text or "refund_apply" in text:
      return IntentType.REFUND
    # 注意：投诉只在"用户明确要创建"或"跟进已有投诉"时进入 TICKET。
    # 系统上下文里的'本轮任务：投诉/升级'不再单独触发创建，避免误建（查询/总结类）。
    # 跟进（带编号的只读请求）必须先于知识库规则命中，由 TicketFlow 读真实投诉记录。
    if is_followup_request(visible_input) or is_explicit_create_request(visible_input):
      return IntentType.TICKET
    if "本轮任务：转人工" in user_input or "humantransferagent" in text or "transfer_human" in text:
      return IntentType.HUMAN_TRANSFER

    return None


def _classify_knowledge_intent_by_rule(user_input: str) -> IntentType | None:
    """Route enterprise knowledge questions before LLM classification."""
    text = user_input.strip().lower()
    if not text:
        return None

    blocked_business_actions = [
        "订单查询", "查订单", "订单状态", "物流查询", "快递到哪", "退款申请",
        "我要退款", "申请退款", "投诉提交", "我要投诉", "库存查询", "还有库存",
        "有没有货", "order", "tracking", "refund apply",
    ]
    if any(keyword in text for keyword in blocked_business_actions):
        return None

    knowledge_domain_terms = [
        "退款", "退货", "投诉", "会员", "优惠券", "物流赔付", "配送时效", "客服处理", "平台",
        "thinkbook", "macbook", "iphone", "ipad", "airpods", "sony", "rog", "xiaomi",
    ]
    knowledge_question_terms = [
        "规则", "政策", "制度", "规范", "说明", "条件", "faq", "常见问题", "参数", "配置",
        "怎么领取", "如何领取", "领取方式", "怎么使用", "使用规则", "有哪些", "是什么", "介绍",
        "支持扩展内存", "屏幕尺寸",
    ]
    if any(term in text for term in knowledge_domain_terms) and any(term in text for term in knowledge_question_terms):
        return IntentType.KNOWLEDGE_QUERY

    knowledge_keywords = [
        "规则", "政策", "制度", "规范", "sop", "faq", "常见问题", "平台帮助",
        "帮助中心", "说明", "条款", "条件", "七天无理由", "退货条件", "退款规则",
        "配送时效", "配送规则", "投诉升级规则", "会员等级", "会员规则", "优惠券规则",
        "客服处理规范", "售后政策", "平台规则", "参数介绍", "支持扩展内存",
        "thinkbook", "macbook air",
    ]
    if any(keyword in text for keyword in knowledge_keywords):
        return IntentType.KNOWLEDGE_QUERY
    return None
