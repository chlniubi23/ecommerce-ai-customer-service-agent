"""
转人工客服 Flow Handler

职责：
- 处理 HUMAN_TRANSFER 意图
- 调用 HumanTransferTool 发起转人工请求
- 用自然语言告知用户转接状态

架构：
  用户输入 → ToolRouter → HumanTransferTool → Tool Result
  → Tool Result 注入 Prompt → LLM → AI 回复
"""

import logging
import re
from app.flows.base import BaseFlow, FlowResult
from app.schemas.intent import IntentResult
from app.models.message import Message, MessageRole
from app.services.llm import call_llm
from app.tools.tool_router import select_tool
from app.tools.executors.tool_executor import tool_executor

logger = logging.getLogger(__name__)


def _extract_user_id(text: str) -> str | None:
    """从输入（含前端注入的"当前登录用户：USRxxx"上下文）中提取用户 ID，
    用于把转人工排队记录关联到具体用户。"""
    match = re.search(r'\b(USR[A-Za-z0-9_\-]{4,40})\b', text)
    return match.group(1) if match else None

HUMAN_TRANSFER_PROMPT = """你是电商平台的智能客服。

用户请求转接人工客服。

回复要求：
1. 如果工具已成功发起转接，告知用户正在排队等待
2. 告知预计等待时间
3. 语气礼貌友好
4. 不要输出 JSON，只输出自然语言回复
5. 可以询问用户是否还有其他问题需要在等待期间解答
"""


class HumanTransferFlow(BaseFlow):
    """转人工客服处理器"""

    async def handle(self, intent_result: IntentResult, history: list[dict], slots: dict | None = None) -> FlowResult:
        logger.info(f"HumanTransferFlow 处理: {intent_result.raw_input[:50]}")

        tool_calls = []
        user_message = intent_result.raw_input
        user_id = _extract_user_id(intent_result.raw_input)

        # 直接调用 transfer_human 工具（把用户真正加入人工队列）
        plan = await select_tool(
            intent="human_transfer",
            user_input=intent_result.raw_input,
            history=history,
        )

        if plan.should_call and plan.tool:
            params = {**plan.params}
            params.setdefault("reason", intent_result.raw_input[:100])
            if user_id:
                params.setdefault("user_id", user_id)
            exec_result = await tool_executor.execute(plan.tool, **params)
            tool_calls.append(exec_result.to_trace_dict())
            if exec_result.success:
                user_message = f"{intent_result.raw_input}\n\n{exec_result.to_context_string()}"
                logger.info("HumanTransferFlow: 转人工成功")
        else:
            # 即使 ToolRouter 没选中，也直接调用 transfer_human
            from app.tools.tool_registry import tool_registry
            tool = tool_registry.get("transfer_human")
            if tool:
                exec_result = await tool_executor.execute(
                    tool, reason=intent_result.raw_input[:100], user_id=user_id
                )
                tool_calls.append(exec_result.to_trace_dict())
                if exec_result.success:
                    user_message = f"{intent_result.raw_input}\n\n{exec_result.to_context_string()}"

        content = await call_llm(
            system_prompt=HUMAN_TRANSFER_PROMPT,
            user_message=user_message,
            history=history,
        )

        return FlowResult(
            message=Message(role=MessageRole.ASSISTANT, content=content),
            tool_calls=tool_calls,
        )
