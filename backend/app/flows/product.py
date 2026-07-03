"""
商品咨询 Flow Handler

职责：
- 处理 PRODUCT_QUERY 意图
- 使用商品专用 Prompt 调用 LLM
- 调用 ProductTool 查询商品参数

架构：
  用户输入 → ToolRouter → ProductTool → Tool Result
  → Tool Result 注入 Prompt → LLM → AI 回复
"""

import logging
import re
from app.flows.base import BaseFlow, FlowResult
from app.schemas.intent import IntentResult
from app.models.message import Message, MessageRole
from app.prompts.product import PRODUCT_PROMPT
from app.services.llm import call_llm
from app.tools.tool_router import select_tool
from app.tools.executors.tool_executor import tool_executor

logger = logging.getLogger(__name__)

# 触发个性化推荐的提示词：用户在征求"推荐/买什么/值得入手"类建议时，
# 结合真实购买历史给推荐，而不是只查单个商品参数。
_RECOMMEND_HINTS = (
    "推荐", "推荐几", "有什么值得", "值得入手", "值得买", "买什么", "买点什么",
    "适合我", "根据我", "结合我", "还能买", "再买", "有没有推荐", "给点建议",
)


def _extract_user_id(text: str) -> str | None:
    match = re.search(r'\b(USR[A-Za-z0-9_\-]{4,40})\b', text)
    return match.group(1) if match else None


class ProductFlow(BaseFlow):
    """商品咨询处理器（含基于历史的个性化推荐）"""

    @staticmethod
    def _ensure_recommend_tool():
        from app.tools.tool_registry import tool_registry, init_tools
        if tool_registry.get("recommend_products") is None:
            init_tools()
        return tool_registry.get("recommend_products")

    async def handle(self, intent_result: IntentResult, history: list[dict], slots: dict | None = None) -> FlowResult:
        logger.info(f"ProductFlow 处理: {intent_result.raw_input[:50]}")

        tool_calls = []
        user_message = intent_result.raw_input
        user_id = (slots or {}).get("user_id") or _extract_user_id(intent_result.raw_input)

        # 推荐类问题 + 已登录用户：调用 recommend_products，基于真实购买历史个性化推荐。
        if user_id and any(hint in intent_result.raw_input for hint in _RECOMMEND_HINTS):
            tool = self._ensure_recommend_tool()
            if tool:
                exec_result = await tool_executor.execute(tool, user_id=user_id)
                tool_calls.append(exec_result.to_trace_dict())
                if exec_result.success:
                    user_message = f"{intent_result.raw_input}\n\n{exec_result.to_context_string()}"
                    logger.info("ProductFlow: 个性化推荐工具调用成功")
        else:
            plan = await select_tool(
                intent=intent_result.intent.value,
                user_input=intent_result.raw_input,
                history=history,
            )
            if plan.should_call and plan.tool:
                exec_result = await tool_executor.execute(plan.tool, **plan.params)
                tool_calls.append(exec_result.to_trace_dict())
                if exec_result.success:
                    user_message = f"{intent_result.raw_input}\n\n{exec_result.to_context_string()}"
                    logger.info("ProductFlow: 工具调用成功，注入上下文")
            else:
                logger.info(f"ProductFlow: 未调用工具 - {plan.reason}")

        content = await call_llm(
            system_prompt=PRODUCT_PROMPT,
            user_message=user_message,
            history=history,
        )

        return FlowResult(
            message=Message(role=MessageRole.ASSISTANT, content=content),
            tool_calls=tool_calls,
        )
