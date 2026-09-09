"""
InterruptManager - Flow 中断与恢复管理器

职责：
- 检测用户在 FSM 等待状态时是否切换了意图（Intent 抢占）
- 挂起当前 Flow，切换到新 Flow
- 新 Flow 完成后，提示用户恢复被挂起的 Flow
- 管理 Flow 恢复时的状态回填

设计理念：
- 仅当 Session 处于 WAIT_* 状态时，才启用中断检测
- 中断检测需要先调用 Classifier 判断用户输入是否属于新意图
- 高优先级意图（如退款、物流、投诉）可以抢占当前 Flow
- 低优先级意图（如闲聊）不触发中断，继续当前 Flow

架构位置：
- agent/interrupt/ 层
- 被 agents/agent.py 在 session resume 分支中调用

使用方式：
    decision = await interrupt_manager.check(session, user_input)
    if decision.should_interrupt:
        session.suspend_current_flow()
        # 进入新 Flow
    elif decision.should_resume:
        session.resume_suspended_flow()
        # 恢复旧 Flow
"""

import re
import logging
from dataclasses import dataclass
from app.agents.classifier import classify_intent
from app.schemas.intent import IntentResult, IntentType, CONFIDENCE_HIGH

logger = logging.getLogger(__name__)


# 可以抢占当前 Flow 的高优先级意图
HIGH_PRIORITY_INTENTS = {
    IntentType.REFUND,
    IntentType.LOGISTICS_QUERY,
    IntentType.ORDER_QUERY,
    IntentType.PRODUCT_QUERY,
}

# 用户表达"继续"的关键词
RESUME_KEYWORDS = {
    "继续", "好的继续", "回到之前", "继续退款", "继续上一个",
    "刚才的", "回到刚才", "是的", "是", "对", "嗯继续",
    "继续处理", "接着来",
}


@dataclass
class InterruptDecision:
    """
    中断决策结果

    Attributes:
        should_interrupt: 是否应该中断当前 Flow
        should_resume: 是否应该恢复被挂起的 Flow
        new_intent_result: 新意图分类结果（中断时有值）
        resume_prompt: 恢复提示语（新 Flow 完成后提示用户）
    """
    should_interrupt: bool = False
    should_resume: bool = False
    new_intent_result: IntentResult | None = None
    resume_prompt: str = ""


class InterruptManager:
    """Flow 中断/恢复管理器"""

    async def check(
        self,
        session,
        user_input: str,
    ) -> InterruptDecision:
        """
        检测当前用户输入是否触发 Flow 中断或恢复

        逻辑：
        1. 如果用户输入匹配恢复关键词 + 有挂起的 Flow → 恢复
        2. 短输入或纯数字/ID → 大概率是 slot 填充值，不中断
        3. 对用户输入做意图分类
        4. 如果新意图 != 当前 Flow 且是高优先级 → 中断
        5. 否则 → 不中断，继续当前 FSM

        Args:
            session: 当前会话
            user_input: 用户输入

        Returns:
            InterruptDecision
        """
        current_flow = session.current_flow

        # 1. 检测恢复关键词
        if session.has_suspended_flow():
            stripped = user_input.strip().lower()
            if stripped in RESUME_KEYWORDS:
                return InterruptDecision(should_resume=True)

        # 2. 快速过滤：短文本/纯数字/纯ID → 不做中断检测（大概率是 slot 值）
        stripped = user_input.strip()
        if len(stripped) <= 20 and (stripped.isdigit() or re.match(r'^[A-Za-z0-9]+$', stripped)):
            logger.info(f"[InterruptManager] 输入疑似 Slot 值，跳过中断检测")
            return InterruptDecision()

        # 3. 意图分类
        intent_result = await classify_intent(user_input)
        new_intent = intent_result.intent.value

        logger.info(
            f"[InterruptManager] 当前 flow={current_flow}, "
            f"新意图={new_intent} (conf={intent_result.confidence:.2f})"
        )

        # 3. 判断是否需要中断
        # 条件：新意图 != 当前 Flow + 高置信度 + 高优先级
        if (
            new_intent != current_flow
            and intent_result.confidence >= CONFIDENCE_HIGH
            and intent_result.intent in HIGH_PRIORITY_INTENTS
        ):
            # 构建恢复提示
            flow_name_cn = {
                "refund": "退款",
                "logistics_query": "物流查询",
                "order_query": "订单查询",
                "product_query": "商品咨询",
            }
            suspended_name = flow_name_cn.get(current_flow, current_flow)
            resume_prompt = f"您之前的{suspended_name}流程还没完成，需要继续吗？"

            logger.info(
                f"[InterruptManager] 触发中断: {current_flow} → {new_intent}"
            )
            return InterruptDecision(
                should_interrupt=True,
                new_intent_result=intent_result,
                resume_prompt=resume_prompt,
            )

        # 4. 不中断
        logger.info(f"[InterruptManager] 不中断，继续 {current_flow}")
        return InterruptDecision()


# 全局单例
interrupt_manager = InterruptManager()
