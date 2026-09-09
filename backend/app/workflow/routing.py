"""
Conditional Workflow Routing - 条件工作流路由

职责：
- 动态工作流选择
- 基于条件的工作流路由
- 工作流优先级管理
- 路由决策追踪

设计原则：
- Condition-driven：由 Condition Engine 驱动
- Registry-based：通过 Registry 查找工作流
- Traceable：路由决策可追踪
- Extensible：新增工作流无需修改路由逻辑

路由策略：
1. Intent-based Routing：基于意图路由
2. Confidence-based Routing：基于置信度路由
3. State-based Routing：基于状态路由
4. Priority-based Routing：基于优先级路由
"""

import logging
from dataclasses import dataclass
from typing import Optional
GraphState = dict  # legacy alias; LangGraph experiment layer (app.graph/app.state) removed
from app.workflow.models import WorkflowType, WorkflowDefinition
from app.workflow.registry import workflow_registry
from app.workflow.condition_engine import condition_engine, Decision
from app.workflow.decision_tracer import decision_tracer

logger = logging.getLogger(__name__)


@dataclass
class RoutingResult:
    """
    路由结果

    记录工作流路由的结果。
    """
    workflow_type: WorkflowType         # 选中的工作流类型
    workflow_definition: WorkflowDefinition  # 工作流定义
    decision: Decision                  # 决策记录
    routing_strategy: str               # 路由策略
    metadata: dict                      # 元数据

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "workflow_type": self.workflow_type.value,
            "workflow_name": self.workflow_definition.metadata.name,
            "decision": self.decision.to_dict(),
            "routing_strategy": self.routing_strategy,
            "metadata": self.metadata,
        }


class ConditionalWorkflowRouter:
    """
    条件工作流路由器

    根据状态和条件动态选择工作流。
    """

    def __init__(self):
        self.condition_engine = condition_engine
        self.registry = workflow_registry
        self.tracer = decision_tracer

    def route(self, state: GraphState) -> RoutingResult:
        """
        路由到工作流

        根据当前状态和条件选择合适的工作流。

        Args:
            state: Graph 工作流状态

        Returns:
            RoutingResult: 路由结果
        """
        # 1. 使用 Condition Engine 做决策
        decision = self.condition_engine.decide_workflow(state)

        # 2. 获取工作流定义
        if decision.selected_workflow:
            workflow_definition = self.registry.get(decision.selected_workflow)
            if workflow_definition:
                routing_strategy = "intent_based"
            else:
                # 工作流未注册，降级到 GENERAL
                logger.warning(
                    f"工作流 {decision.selected_workflow.value} 未注册，降级到 GENERAL"
                )
                decision.selected_workflow = WorkflowType.GENERAL
                workflow_definition = self.registry.get(WorkflowType.GENERAL)
                routing_strategy = "fallback"
        else:
            # 无工作流选择，使用 GENERAL
            decision.selected_workflow = WorkflowType.GENERAL
            workflow_definition = self.registry.get(WorkflowType.GENERAL)
            routing_strategy = "default"

        if not workflow_definition:
            raise RuntimeError("GENERAL workflow not registered, router initialization failed")

        # 3. 追踪决策
        session_id = state.get("session_id")
        user_input = state.get("user_input")
        current_intent = state.get("current_intent")

        self.tracer.trace_decision(
            decision=decision,
            state=state,
            session_id=session_id,
            user_input=user_input,
            current_intent=current_intent,
        )

        # 4. 构建路由结果
        result = RoutingResult(
            workflow_type=decision.selected_workflow,
            workflow_definition=workflow_definition,
            decision=decision,
            routing_strategy=routing_strategy,
            metadata={
                "intent": current_intent,
                "confidence": state.get("intent_confidence", 0.0),
                "session_id": session_id,
            },
        )

        logger.info(
            f"[ConditionalRouter] 路由完成: {result.workflow_type.value} "
            f"(strategy={routing_strategy}, confidence={decision.decision_confidence:.2f})"
        )

        return result

    def route_by_intent(self, intent: str, confidence: float) -> Optional[WorkflowType]:
        """
        根据意图路由

        Args:
            intent: 意图
            confidence: 置信度

        Returns:
            工作流类型
        """
        # 低置信度降级到 GENERAL
        if confidence < 0.85:
            logger.info(
                f"[ConditionalRouter] 低置信度 ({confidence:.2f})，降级到 GENERAL"
            )
            return WorkflowType.GENERAL

        # 查找工作流
        workflow_type = self.registry.find_by_intent(intent)
        if not workflow_type:
            logger.warning(
                f"[ConditionalRouter] 意图 {intent} 未找到对应工作流，降级到 GENERAL"
            )
            return WorkflowType.GENERAL

        # 检查是否注册
        if not self.registry.is_registered(workflow_type):
            logger.warning(
                f"[ConditionalRouter] 工作流 {workflow_type.value} 未注册，降级到 GENERAL"
            )
            return WorkflowType.GENERAL

        return workflow_type

    def validate_workflow(self, workflow_type: WorkflowType, state: GraphState) -> bool:
        """
        验证工作流是否可执行

        检查工作流的前置条件是否满足。

        Args:
            workflow_type: 工作流类型
            state: Graph 状态

        Returns:
            是否可执行
        """
        workflow_def = self.registry.get(workflow_type)
        if not workflow_def:
            return False

        metadata = workflow_def.metadata

        # 检查必需的 Slots
        if metadata.requires_slots:
            collected_slots = state.get("collected_slots", {})
            missing_slots = [
                slot for slot in metadata.requires_slots
                if slot not in collected_slots
            ]
            if missing_slots:
                logger.warning(
                    f"[ConditionalRouter] 工作流 {workflow_type.value} 缺少必需 Slots: {missing_slots}"
                )
                return False

        # 检查必需的 Tools
        if metadata.requires_tools:
            # TODO: 检查 Tool 是否可用
            pass

        return True

    def get_available_workflows(self, state: GraphState) -> list[WorkflowType]:
        """
        获取当前状态下可用的工作流

        Args:
            state: Graph 状态

        Returns:
            可用的工作流类型列表
        """
        all_workflows = self.registry.list_all()
        available = []

        for workflow_type in all_workflows:
            if self.validate_workflow(workflow_type, state):
                available.append(workflow_type)

        return available

    def get_routing_stats(self) -> dict:
        """
        获取路由统计信息

        Returns:
            统计信息字典
        """
        decision_stats = self.tracer.get_stats()

        return {
            "total_routings": decision_stats["total_decisions"],
            "workflow_distribution": decision_stats["workflow_distribution"],
            "average_confidence": decision_stats["average_confidence"],
            "registered_workflows": len(self.registry.list_all()),
        }


# 全局单例
conditional_workflow_router = ConditionalWorkflowRouter()
