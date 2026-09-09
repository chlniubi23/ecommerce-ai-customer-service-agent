"""
Condition Engine - 条件决策引擎

职责：
- 解析 Workflow State
- 分析 Intent/Memory/Slot/Tool/RAG 状态
- 生成下一步决策（Workflow/Branch/Node）
- 提供决策理由和置信度

设计原则：
- State-driven：所有决策基于 GraphState
- Rule-based：决策规则声明式定义
- Traceable：决策过程完全可追踪
- Extensible：规则可配置可扩展

决策维度：
1. Intent Analysis：意图置信度、意图类型
2. Slot Analysis：Slot 完整性、缺失 Slot
3. Tool Analysis：工具可用性、工具结果
4. RAG Analysis：RAG 相关性、RAG 可用性
5. Memory Analysis：历史上下文、会话状态
6. Workflow Analysis：当前 Workflow 状态
"""

import logging
from dataclasses import dataclass
from typing import Optional
GraphState = dict  # legacy alias; LangGraph experiment layer (app.graph/app.state) removed
from app.workflow.models import WorkflowType, WorkflowStatus, BranchType
from app.workflow.registry import workflow_registry

logger = logging.getLogger(__name__)


@dataclass
class Decision:
    """
    决策结果

    记录 Condition Engine 的决策输出。
    """
    selected_workflow: Optional[WorkflowType]  # 选中的工作流
    selected_branch: str                       # 选中的分支
    next_node: str                             # 下一个节点
    decision_reason: str                       # 决策理由
    decision_confidence: float                 # 决策置信度 [0.0, 1.0]
    decision_metadata: dict                    # 决策元数据

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "selected_workflow": self.selected_workflow.value if self.selected_workflow else None,
            "selected_branch": self.selected_branch,
            "next_node": self.next_node,
            "decision_reason": self.decision_reason,
            "decision_confidence": self.decision_confidence,
            "decision_metadata": self.decision_metadata,
        }


class ConditionEngine:
    """
    条件决策引擎

    根据 GraphState 动态决定工作流执行路径。
    """

    def __init__(self):
        self.high_confidence_threshold = 0.85
        self.medium_confidence_threshold = 0.60

    def decide_workflow(self, state: GraphState) -> Decision:
        """
        决策工作流选择

        根据当前状态决定应该执行哪个工作流。

        Args:
            state: Graph 工作流状态

        Returns:
            Decision: 决策结果
        """
        # 1. 分析意图
        intent_analysis = self._analyze_intent(state)

        # 2. 分析 Slot 状态
        slot_analysis = self._analyze_slots(state)

        # 3. 分析 RAG 可用性
        rag_analysis = self._analyze_rag(state)

        # 4. 分析工具状态
        tool_analysis = self._analyze_tool(state)

        # 5. 综合决策
        decision = self._make_workflow_decision(
            state=state,
            intent_analysis=intent_analysis,
            slot_analysis=slot_analysis,
            rag_analysis=rag_analysis,
            tool_analysis=tool_analysis,
        )

        logger.info(
            f"[ConditionEngine] 工作流决策: {decision.selected_workflow.value if decision.selected_workflow else 'None'} "
            f"→ {decision.next_node} (confidence={decision.decision_confidence:.2f}, reason={decision.decision_reason})"
        )

        return decision

    def decide_next_node(self, state: GraphState, current_node: str) -> Decision:
        """
        决策下一个执行节点

        根据当前节点和状态决定下一步执行哪个节点。

        Args:
            state: Graph 工作流状态
            current_node: 当前节点名称

        Returns:
            Decision: 决策结果
        """
        # 根据当前节点动态路由
        if current_node == "router_node":
            return self._decide_after_router(state)
        elif current_node == "rag_node":
            return self._decide_after_rag(state)
        elif current_node == "slot_node":
            return self._decide_after_slot(state)
        elif current_node == "tool_node":
            return self._decide_after_tool(state)
        else:
            # 默认：进入 response_node
            return Decision(
                selected_workflow=None,
                selected_branch="main",
                next_node="response_node",
                decision_reason=f"Default routing after {current_node}",
                decision_confidence=1.0,
                decision_metadata={"current_node": current_node},
            )

    def _analyze_intent(self, state: GraphState) -> dict:
        """分析意图状态"""
        current_intent = state.get("current_intent", "")
        intent_confidence = state.get("intent_confidence", 0.0)

        # 查找对应的工作流
        workflow_type = workflow_registry.find_by_intent(current_intent)

        return {
            "intent": current_intent,
            "confidence": intent_confidence,
            "workflow_type": workflow_type,
            "is_high_confidence": intent_confidence >= self.high_confidence_threshold,
            "is_medium_confidence": intent_confidence >= self.medium_confidence_threshold,
        }

    def _analyze_slots(self, state: GraphState) -> dict:
        """分析 Slot 状态"""
        slots_ready = state.get("slots_ready", True)
        collected_slots = state.get("collected_slots", {})
        waiting_for = state.get("waiting_for", "")
        has_fsm = state.get("has_fsm", False)

        return {
            "slots_ready": slots_ready,
            "has_fsm": has_fsm,
            "collected_slots": collected_slots,
            "waiting_for": waiting_for,
            "needs_slot_filling": has_fsm and not slots_ready,
        }

    def _analyze_rag(self, state: GraphState) -> dict:
        """分析 RAG 状态"""
        rag_eligible = state.get("rag_eligible", False)
        rag_used = state.get("rag_used", False)
        rag_chunks = state.get("rag_chunks", 0)

        return {
            "rag_eligible": rag_eligible,
            "rag_used": rag_used,
            "rag_chunks": rag_chunks,
            "has_rag_context": rag_chunks > 0,
        }

    def _analyze_tool(self, state: GraphState) -> dict:
        """分析工具状态"""
        tool_success = state.get("tool_success", False)
        tool_result = state.get("tool_result", {})
        tool_error = state.get("tool_error", "")
        selected_tool = state.get("selected_tool", "")

        return {
            "tool_success": tool_success,
            "tool_result": tool_result,
            "tool_error": tool_error,
            "selected_tool": selected_tool,
            "has_tool_result": bool(tool_result),
        }

    def _make_workflow_decision(
        self,
        state: GraphState,
        intent_analysis: dict,
        slot_analysis: dict,
        rag_analysis: dict,
        tool_analysis: dict,
    ) -> Decision:
        """
        综合决策工作流选择

        决策逻辑：
        1. 高置信度意图 + 工作流已注册 → 选择对应工作流
        2. 低置信度意图 → 降级到 GENERAL
        3. 未注册工作流 → 降级到 GENERAL
        """
        workflow_type = intent_analysis["workflow_type"]
        confidence = intent_analysis["confidence"]
        is_high_confidence = intent_analysis["is_high_confidence"]

        # 决策 1：高置信度且工作流已注册
        if is_high_confidence and workflow_type and workflow_registry.is_registered(workflow_type):
            return Decision(
                selected_workflow=workflow_type,
                selected_branch="main",
                next_node="router_node",
                decision_reason=f"High confidence intent ({confidence:.2f}) matched to registered workflow",
                decision_confidence=confidence,
                decision_metadata={
                    "intent": intent_analysis["intent"],
                    "workflow_registered": True,
                },
            )

        # 决策 2：低置信度 → 降级到 GENERAL
        if not is_high_confidence:
            return Decision(
                selected_workflow=WorkflowType.GENERAL,
                selected_branch="main",
                next_node="router_node",
                decision_reason=f"Low confidence intent ({confidence:.2f}), downgrade to GENERAL",
                decision_confidence=confidence,
                decision_metadata={
                    "intent": intent_analysis["intent"],
                    "downgraded": True,
                    "original_workflow": workflow_type.value if workflow_type else None,
                },
            )

        # 决策 3：工作流未注册 → 降级到 GENERAL
        return Decision(
            selected_workflow=WorkflowType.GENERAL,
            selected_branch="fallback",
            next_node="router_node",
            decision_reason=f"Workflow not registered for intent {intent_analysis['intent']}, fallback to GENERAL",
            decision_confidence=0.5,
            decision_metadata={
                "intent": intent_analysis["intent"],
                "workflow_registered": False,
            },
        )

    def _decide_after_router(self, state: GraphState) -> Decision:
        """
        Router 节点后的决策

        决策逻辑：
        1. Slot 未就绪 → slot_node（填充 Slot）
        2. RAG 候选 → rag_node（检索知识库）
        3. 默认 → tool_node（执行工具）
        """
        slot_analysis = self._analyze_slots(state)
        rag_analysis = self._analyze_rag(state)

        # 决策 1：Slot 未就绪
        if slot_analysis["needs_slot_filling"]:
            return Decision(
                selected_workflow=None,
                selected_branch="slot_filling",
                next_node="slot_node",
                decision_reason=f"Slots not ready, waiting for: {slot_analysis['waiting_for']}",
                decision_confidence=1.0,
                decision_metadata=slot_analysis,
            )

        # 决策 2：RAG 候选
        if rag_analysis["rag_eligible"]:
            return Decision(
                selected_workflow=None,
                selected_branch="rag_retrieval",
                next_node="rag_node",
                decision_reason="RAG eligible, attempting knowledge retrieval",
                decision_confidence=0.8,
                decision_metadata=rag_analysis,
            )

        # 决策 3：默认执行工具
        return Decision(
            selected_workflow=None,
            selected_branch="tool_execution",
            next_node="tool_node",
            decision_reason="Slots ready, executing tool",
            decision_confidence=1.0,
            decision_metadata={
                "slots_ready": slot_analysis["slots_ready"],
                "collected_slots": slot_analysis["collected_slots"],
            },
        )

    def _decide_after_rag(self, state: GraphState) -> Decision:
        """
        RAG 节点后的决策

        决策逻辑：
        1. RAG 命中 → response_node（直接回复）
        2. RAG 未命中 → tool_node（回退到工具）
        """
        rag_analysis = self._analyze_rag(state)

        # 决策 1：RAG 命中
        if rag_analysis["rag_used"] and rag_analysis["has_rag_context"]:
            return Decision(
                selected_workflow=None,
                selected_branch="rag_success",
                next_node="response_node",
                decision_reason=f"RAG hit with {rag_analysis['rag_chunks']} chunks, direct response",
                decision_confidence=0.9,
                decision_metadata=rag_analysis,
            )

        # 决策 2：RAG 未命中，回退到工具
        return Decision(
            selected_workflow=None,
            selected_branch="rag_fallback",
            next_node="tool_node",
            decision_reason="RAG miss, fallback to tool execution",
            decision_confidence=0.7,
            decision_metadata=rag_analysis,
        )

    def _decide_after_slot(self, state: GraphState) -> Decision:
        """
        Slot 节点后的决策

        决策逻辑：
        1. Slot 已就绪 → 返回原工作流（tool_node）
        2. Slot 仍未就绪 → 继续追问（slot_response_node）
        """
        slot_analysis = self._analyze_slots(state)

        # 决策 1：Slot 已就绪
        if slot_analysis["slots_ready"]:
            return Decision(
                selected_workflow=None,
                selected_branch="slot_complete",
                next_node="tool_node",
                decision_reason="Slots filled, resume workflow",
                decision_confidence=1.0,
                decision_metadata=slot_analysis,
            )

        # 决策 2：Slot 仍未就绪
        return Decision(
            selected_workflow=None,
            selected_branch="slot_waiting",
            next_node="slot_response_node",
            decision_reason=f"Still waiting for slot: {slot_analysis['waiting_for']}",
            decision_confidence=1.0,
            decision_metadata=slot_analysis,
        )

    def _decide_after_tool(self, state: GraphState) -> Decision:
        """
        Tool 节点后的决策

        决策逻辑：
        1. 工具成功 → response_node（生成回复）
        2. 工具失败 → response_node（错误处理回复）
        """
        tool_analysis = self._analyze_tool(state)

        # 所有情况都进入 response_node（成功或失败都需要回复）
        if tool_analysis["tool_success"]:
            return Decision(
                selected_workflow=None,
                selected_branch="tool_success",
                next_node="response_node",
                decision_reason="Tool execution succeeded, generating response",
                decision_confidence=1.0,
                decision_metadata=tool_analysis,
            )
        else:
            return Decision(
                selected_workflow=None,
                selected_branch="tool_failure",
                next_node="response_node",
                decision_reason=f"Tool execution failed: {tool_analysis['tool_error']}, generating error response",
                decision_confidence=0.8,
                decision_metadata=tool_analysis,
            )


# 全局单例
condition_engine = ConditionEngine()
