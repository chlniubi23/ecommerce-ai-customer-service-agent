"""
Slot Filling Workflow - Slot 填充工作流

职责：
- 自动识别缺失 Slot
- 动态生成追问策略
- Slot 补全后自动恢复原工作流
- 支持多轮 Slot 填充

设计原则：
- Context-aware：基于上下文生成追问
- Resumable：补全后无缝恢复原工作流
- Traceable：Slot 填充过程可追踪
- User-friendly：人格化追问，避免机械式提问
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional
GraphState = dict  # legacy alias; LangGraph experiment layer (app.graph/app.state) removed
from app.workflow.models import WorkflowType
from app.workflow.registry import workflow_registry

logger = logging.getLogger(__name__)


@dataclass
class SlotRequirement:
    """
    Slot 需求定义

    定义 Slot 的类型和验证规则。
    """
    name: str                           # Slot 名称
    description: str                    # Slot 描述
    required: bool = True               # 是否必需
    slot_type: str = "string"           # Slot 类型
    validation_fn: Optional[Any] = None # 验证函数
    default_value: Optional[Any] = None # 默认值
    prompt_template: Optional[str] = None  # 追问模板


@dataclass
class SlotFillingContext:
    """
    Slot 填充上下文

    记录 Slot 填充过程的状态。
    """
    workflow_type: WorkflowType         # 工作流类型
    required_slots: list[str]           # 必需 Slots
    optional_slots: list[str]           # 可选 Slots
    collected_slots: dict[str, Any]     # 已收集 Slots
    missing_slots: list[str]            # 缺失 Slots
    current_asking: Optional[str] = None  # 当前正在询问的 Slot
    retry_count: int = 0                # 重试次数
    max_retries: int = 3                # 最大重试次数

    def is_complete(self) -> bool:
        """是否完成"""
        return len(self.missing_slots) == 0

    def get_next_missing_slot(self) -> Optional[str]:
        """获取下一个缺失的 Slot"""
        return self.missing_slots[0] if self.missing_slots else None

    def mark_collected(self, slot_name: str, value: Any) -> None:
        """标记 Slot 已收集"""
        self.collected_slots[slot_name] = value
        if slot_name in self.missing_slots:
            self.missing_slots.remove(slot_name)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "workflow_type": self.workflow_type.value,
            "required_slots": self.required_slots,
            "optional_slots": self.optional_slots,
            "collected_slots": self.collected_slots,
            "missing_slots": self.missing_slots,
            "current_asking": self.current_asking,
            "retry_count": self.retry_count,
            "is_complete": self.is_complete(),
        }


class SlotFillingWorkflow:
    """
    Slot 填充工作流

    管理 Slot 的识别、追问和填充。
    """

    def __init__(self):
        self.registry = workflow_registry
        # Slot 填充上下文（按 session_id 存储）
        self._contexts: dict[str, SlotFillingContext] = {}

    def analyze_slots(self, state: GraphState) -> SlotFillingContext:
        """
        分析 Slot 状态

        识别必需 Slots、可选 Slots 和缺失 Slots。

        Args:
            state: Graph 状态

        Returns:
            SlotFillingContext: Slot 填充上下文
        """
        # 获取当前工作流类型
        current_intent = state.get("current_intent", "")
        workflow_type = self.registry.find_by_intent(current_intent)
        if not workflow_type:
            workflow_type = WorkflowType.GENERAL

        # 获取工作流元数据
        workflow_def = self.registry.get(workflow_type)
        if not workflow_def:
            return SlotFillingContext(
                workflow_type=workflow_type,
                required_slots=[],
                optional_slots=[],
                collected_slots={},
                missing_slots=[],
            )

        metadata = workflow_def.metadata
        required_slots = metadata.requires_slots
        optional_slots = metadata.optional_slots
        collected_slots = state.get("collected_slots", {})

        # 计算缺失 Slots
        missing_slots = [
            slot for slot in required_slots
            if slot not in collected_slots or not collected_slots[slot]
        ]

        context = SlotFillingContext(
            workflow_type=workflow_type,
            required_slots=required_slots,
            optional_slots=optional_slots,
            collected_slots=collected_slots,
            missing_slots=missing_slots,
        )

        # 存储上下文
        session_id = state.get("session_id")
        if session_id:
            self._contexts[session_id] = context

        logger.info(
            f"[SlotFillingWorkflow] Slot 分析: workflow={workflow_type.value}, "
            f"required={required_slots}, missing={missing_slots}"
        )

        return context

    def generate_slot_prompt(self, slot_name: str, context: SlotFillingContext) -> str:
        """
        生成 Slot 追问提示

        Args:
            slot_name: Slot 名称
            context: Slot 填充上下文

        Returns:
            追问提示
        """
        # 预定义的 Slot 追问模板
        slot_prompts = {
            "order_id": "请提供您的订单号，我来帮您查询。",
            "product_id": "请告诉我商品编号或商品名称。",
            "refund_reason": "请简单说明一下您申请退款的原因。",
            "issue_description": "请详细描述您遇到的问题。",
            "complaint_reason": "请告诉我您投诉的具体原因。",
        }

        # 使用预定义模板或生成通用提示
        prompt = slot_prompts.get(slot_name, f"请提供 {slot_name}。")

        # 添加重试提示
        if context.retry_count > 0:
            prompt = f"抱歉，我没能识别到有效的信息。{prompt}"

        return prompt

    def validate_slot_value(
        self,
        slot_name: str,
        value: Any,
        workflow_type: WorkflowType,
    ) -> tuple[bool, Optional[str]]:
        """
        验证 Slot 值

        Args:
            slot_name: Slot 名称
            value: Slot 值
            workflow_type: 工作流类型

        Returns:
            (是否有效, 错误信息)
        """
        # 基本验证：非空
        if not value or (isinstance(value, str) and not value.strip()):
            return False, f"{slot_name} 不能为空"

        # TODO: 添加特定 Slot 的验证规则
        # 例如：订单号格式验证、商品 ID 格式验证等

        return True, None

    def fill_slot(
        self,
        slot_name: str,
        value: Any,
        session_id: str,
    ) -> tuple[bool, Optional[str]]:
        """
        填充 Slot

        Args:
            slot_name: Slot 名称
            value: Slot 值
            session_id: 会话 ID

        Returns:
            (是否成功, 错误信息)
        """
        context = self._contexts.get(session_id)
        if not context:
            return False, "Slot filling context not found"

        # 验证 Slot 值
        is_valid, error = self.validate_slot_value(slot_name, value, context.workflow_type)
        if not is_valid:
            context.retry_count += 1
            return False, error

        # 标记已收集
        context.mark_collected(slot_name, value)
        context.retry_count = 0

        logger.info(
            f"[SlotFillingWorkflow] Slot 已填充: {slot_name}={value} "
            f"(remaining={len(context.missing_slots)})"
        )

        return True, None

    def should_continue_asking(self, session_id: str) -> bool:
        """
        是否应该继续追问

        Args:
            session_id: 会话 ID

        Returns:
            是否继续追问
        """
        context = self._contexts.get(session_id)
        if not context:
            return False

        # 如果已完成或超过最大重试次数，不再追问
        if context.is_complete() or context.retry_count >= context.max_retries:
            return False

        return True

    def get_next_slot_to_ask(self, session_id: str) -> Optional[str]:
        """
        获取下一个需要询问的 Slot

        Args:
            session_id: 会话 ID

        Returns:
            Slot 名称
        """
        context = self._contexts.get(session_id)
        if not context:
            return None

        return context.get_next_missing_slot()

    def create_slot_response(self, state: GraphState) -> dict:
        """
        创建 Slot 追问响应

        Args:
            state: Graph 状态

        Returns:
            响应状态更新
        """
        session_id = state.get("session_id")
        context = self._contexts.get(session_id) if session_id else None

        if not context:
            # 没有上下文，分析创建
            context = self.analyze_slots(state)

        # 获取下一个需要询问的 Slot
        next_slot = context.get_next_missing_slot()
        if not next_slot:
            # 所有 Slot 已收集完
            return {
                "slots_ready": True,
                "waiting_for": "",
                "slot_prompt": "",
            }

        # 生成追问提示
        slot_prompt = self.generate_slot_prompt(next_slot, context)
        context.current_asking = next_slot

        return {
            "slots_ready": False,
            "waiting_for": next_slot,
            "slot_prompt": slot_prompt,
            "workflow_status": "waiting_slot",
        }

    def get_context(self, session_id: str) -> Optional[SlotFillingContext]:
        """
        获取 Slot 填充上下文

        Args:
            session_id: 会话 ID

        Returns:
            SlotFillingContext: Slot 填充上下文
        """
        return self._contexts.get(session_id)

    def clear_context(self, session_id: str) -> None:
        """
        清除 Slot 填充上下文

        Args:
            session_id: 会话 ID
        """
        if session_id in self._contexts:
            del self._contexts[session_id]
            logger.info(f"[SlotFillingWorkflow] 清除 Slot 填充上下文: {session_id}")

    def get_stats(self) -> dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        total_contexts = len(self._contexts)
        complete_contexts = len([c for c in self._contexts.values() if c.is_complete()])
        incomplete_contexts = total_contexts - complete_contexts

        return {
            "total_contexts": total_contexts,
            "complete_contexts": complete_contexts,
            "incomplete_contexts": incomplete_contexts,
        }


# 全局单例
slot_filling_workflow = SlotFillingWorkflow()
