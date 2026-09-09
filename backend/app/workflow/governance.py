"""
Enterprise Workflow Governance - 企业级工作流治理

职责：
- Workflow 验证
- Branch 验证
- State 验证
- Transition 验证
- Decision 验证

设计原则：
- Fail-fast：尽早发现问题
- Policy-driven：基于策略的治理
- Auditable：所有验证可审计
- Extensible：验证规则可扩展
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional
GraphState = dict  # legacy alias; LangGraph experiment layer (app.graph/app.state) removed
from app.workflow.models import WorkflowType, WorkflowStatus, BranchType, AgentStatus

logger = logging.getLogger(__name__)


class ValidationLevel(str, Enum):
    """验证级别"""
    ERROR = "error"       # 错误：阻止执行
    WARNING = "warning"   # 警告：记录但继续
    INFO = "info"         # 信息：仅记录


@dataclass
class ValidationResult:
    """
    验证结果

    记录验证的结果。
    """
    rule_name: str                      # 规则名称
    level: ValidationLevel              # 验证级别
    passed: bool                        # 是否通过
    message: str                        # 验证消息
    metadata: dict[str, Any] = None     # 元数据

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "rule_name": self.rule_name,
            "level": self.level.value,
            "passed": self.passed,
            "message": self.message,
            "metadata": self.metadata,
        }


@dataclass
class ValidationRule:
    """
    验证规则

    定义一个验证规则。
    """
    name: str                           # 规则名称
    description: str                    # 规则描述
    level: ValidationLevel              # 验证级别
    validate_fn: Callable[[Any], ValidationResult]  # 验证函数
    enabled: bool = True                # 是否启用


class WorkflowValidator:
    """
    工作流验证器

    验证工作流的合法性。
    """

    def __init__(self):
        self._rules: list[ValidationRule] = []
        self._initialize_rules()

    def validate(self, workflow_type: WorkflowType, state: GraphState) -> list[ValidationResult]:
        """
        验证工作流

        Args:
            workflow_type: 工作流类型
            state: Graph 状态

        Returns:
            验证结果列表
        """
        results = []

        for rule in self._rules:
            if not rule.enabled:
                continue

            try:
                result = rule.validate_fn({"workflow_type": workflow_type, "state": state})
                results.append(result)

                if not result.passed and result.level == ValidationLevel.ERROR:
                    logger.error(
                        f"[WorkflowValidator] 验证失败: {rule.name} - {result.message}"
                    )
                elif not result.passed and result.level == ValidationLevel.WARNING:
                    logger.warning(
                        f"[WorkflowValidator] 验证警告: {rule.name} - {result.message}"
                    )
            except Exception as e:
                logger.error(f"[WorkflowValidator] 规则执行失败: {rule.name}, error={e}")
                results.append(ValidationResult(
                    rule_name=rule.name,
                    level=ValidationLevel.ERROR,
                    passed=False,
                    message=f"Rule execution failed: {e}",
                ))

        return results

    def has_errors(self, results: list[ValidationResult]) -> bool:
        """
        检查是否有错误

        Args:
            results: 验证结果列表

        Returns:
            是否有错误
        """
        return any(
            not r.passed and r.level == ValidationLevel.ERROR
            for r in results
        )

    def _initialize_rules(self) -> None:
        """初始化验证规则"""
        # 规则 1：工作流必须注册
        self._rules.append(ValidationRule(
            name="workflow_registered",
            description="Workflow must be registered",
            level=ValidationLevel.ERROR,
            validate_fn=self._validate_workflow_registered,
        ))

        # 规则 2：意图必须存在
        self._rules.append(ValidationRule(
            name="intent_exists",
            description="Intent must exist in state",
            level=ValidationLevel.WARNING,
            validate_fn=self._validate_intent_exists,
        ))

        # 规则 3：置信度必须合理
        self._rules.append(ValidationRule(
            name="confidence_valid",
            description="Intent confidence must be between 0 and 1",
            level=ValidationLevel.WARNING,
            validate_fn=self._validate_confidence,
        ))

    def _validate_workflow_registered(self, context: dict) -> ValidationResult:
        """验证工作流是否注册"""
        workflow_type = context["workflow_type"]
        from app.workflow.registry import workflow_registry

        is_registered = workflow_registry.is_registered(workflow_type)

        return ValidationResult(
            rule_name="workflow_registered",
            level=ValidationLevel.ERROR,
            passed=is_registered,
            message=f"Workflow {workflow_type.value} is {'registered' if is_registered else 'not registered'}",
            metadata={"workflow_type": workflow_type.value},
        )

    def _validate_intent_exists(self, context: dict) -> ValidationResult:
        """验证意图是否存在"""
        state = context["state"]
        current_intent = state.get("current_intent", "")

        passed = bool(current_intent)

        return ValidationResult(
            rule_name="intent_exists",
            level=ValidationLevel.WARNING,
            passed=passed,
            message=f"Intent {'exists' if passed else 'missing'} in state",
            metadata={"intent": current_intent},
        )

    def _validate_confidence(self, context: dict) -> ValidationResult:
        """验证置信度"""
        state = context["state"]
        confidence = state.get("intent_confidence", 0.0)

        passed = 0.0 <= confidence <= 1.0

        return ValidationResult(
            rule_name="confidence_valid",
            level=ValidationLevel.WARNING,
            passed=passed,
            message=f"Confidence {confidence} is {'valid' if passed else 'invalid'}",
            metadata={"confidence": confidence},
        )


class StateValidator:
    """
    状态验证器

    验证状态的合法性。
    """

    def validate(self, state: GraphState) -> list[ValidationResult]:
        """
        验证状态

        Args:
            state: Graph 状态

        Returns:
            验证结果列表
        """
        results = []

        # 验证 1：session_id 必须存在
        session_id = state.get("session_id", "")
        results.append(ValidationResult(
            rule_name="session_id_exists",
            level=ValidationLevel.ERROR,
            passed=bool(session_id),
            message=f"Session ID {'exists' if session_id else 'missing'}",
            metadata={"session_id": session_id},
        ))

        # 验证 2：workflow_status 必须有效
        workflow_status = state.get("workflow_status", "")
        valid_statuses = [s.value for s in WorkflowStatus]
        status_valid = workflow_status in valid_statuses if workflow_status else False
        results.append(ValidationResult(
            rule_name="workflow_status_valid",
            level=ValidationLevel.WARNING,
            passed=status_valid or not workflow_status,
            message=f"Workflow status {'valid' if status_valid else 'invalid or missing'}",
            metadata={"status": workflow_status},
        ))

        # 验证 3：collected_slots 必须是字典
        collected_slots = state.get("collected_slots")
        slots_valid = isinstance(collected_slots, dict) if collected_slots is not None else True
        results.append(ValidationResult(
            rule_name="collected_slots_type",
            level=ValidationLevel.ERROR,
            passed=slots_valid,
            message=f"Collected slots type {'valid' if slots_valid else 'invalid'}",
            metadata={"type": type(collected_slots).__name__ if collected_slots else "None"},
        ))

        return results


class TransitionValidator:
    """
    状态转换验证器

    验证状态转换的合法性。
    """

    # 合法的状态转换
    VALID_TRANSITIONS = {
        WorkflowStatus.CREATED: [WorkflowStatus.ACTIVE, WorkflowStatus.CANCELLED],
        WorkflowStatus.ACTIVE: [
            WorkflowStatus.INTERRUPTED,
            WorkflowStatus.WAITING_USER,
            WorkflowStatus.WAITING_TOOL,
            WorkflowStatus.WAITING_HUMAN,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        ],
        WorkflowStatus.INTERRUPTED: [WorkflowStatus.RESUMING, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED],
        WorkflowStatus.RESUMING: [WorkflowStatus.ACTIVE, WorkflowStatus.RUNNING, WorkflowStatus.FAILED],
        WorkflowStatus.WAITING_TOOL: [WorkflowStatus.RESUMING, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED],
        WorkflowStatus.WAITING_HUMAN: [WorkflowStatus.RESUMING, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED],
        WorkflowStatus.PENDING: [WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED],
        WorkflowStatus.RUNNING: [
            WorkflowStatus.INTERRUPTED,
            WorkflowStatus.WAITING_SLOT,
            WorkflowStatus.WAITING_USER,
            WorkflowStatus.WAITING_TOOL,
            WorkflowStatus.WAITING_HUMAN,
            WorkflowStatus.PAUSED,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
        ],
        WorkflowStatus.WAITING_SLOT: [WorkflowStatus.RUNNING, WorkflowStatus.RESUMING, WorkflowStatus.FAILED],
        WorkflowStatus.WAITING_USER: [WorkflowStatus.RUNNING, WorkflowStatus.RESUMING, WorkflowStatus.CANCELLED],
        WorkflowStatus.PAUSED: [WorkflowStatus.RUNNING, WorkflowStatus.RESUMING, WorkflowStatus.CANCELLED],
        WorkflowStatus.COMPLETED: [],  # 终态
        WorkflowStatus.FAILED: [],     # 终态
        WorkflowStatus.CANCELLED: [],  # 终态
    }

    def validate_transition(
        self,
        from_status: WorkflowStatus,
        to_status: WorkflowStatus,
    ) -> ValidationResult:
        """
        验证状态转换

        Args:
            from_status: 源状态
            to_status: 目标状态

        Returns:
            ValidationResult: 验证结果
        """
        valid_next = self.VALID_TRANSITIONS.get(from_status, [])
        passed = to_status in valid_next

        return ValidationResult(
            rule_name="state_transition",
            level=ValidationLevel.ERROR,
            passed=passed,
            message=f"Transition {from_status.value} -> {to_status.value} is {'valid' if passed else 'invalid'}",
            metadata={
                "from_status": from_status.value,
                "to_status": to_status.value,
                "valid_next": [s.value for s in valid_next],
            },
        )


class DecisionValidator:
    """
    决策验证器

    验证决策的合法性。
    """

    def validate_decision(
        self,
        selected_workflow: Optional[WorkflowType],
        next_node: str,
        confidence: float,
    ) -> list[ValidationResult]:
        """
        验证决策

        Args:
            selected_workflow: 选中的工作流
            next_node: 下一个节点
            confidence: 置信度

        Returns:
            验证结果列表
        """
        results = []

        # 验证 1：置信度范围
        confidence_valid = 0.0 <= confidence <= 1.0
        results.append(ValidationResult(
            rule_name="decision_confidence_valid",
            level=ValidationLevel.WARNING,
            passed=confidence_valid,
            message=f"Decision confidence {confidence} is {'valid' if confidence_valid else 'invalid'}",
            metadata={"confidence": confidence},
        ))

        # 验证 2：下一个节点不为空
        node_valid = bool(next_node)
        results.append(ValidationResult(
            rule_name="next_node_exists",
            level=ValidationLevel.ERROR,
            passed=node_valid,
            message=f"Next node {'exists' if node_valid else 'missing'}",
            metadata={"next_node": next_node},
        ))

        # 验证 3：低置信度决策应该降级到 GENERAL
        if selected_workflow and confidence < 0.85 and selected_workflow != WorkflowType.GENERAL:
            results.append(ValidationResult(
                rule_name="low_confidence_downgrade",
                level=ValidationLevel.WARNING,
                passed=False,
                message=f"Low confidence ({confidence}) workflow should downgrade to GENERAL",
                metadata={
                    "workflow": selected_workflow.value,
                    "confidence": confidence,
                },
            ))

        return results


class WorkflowGovernance:
    """
    工作流治理

    统一的工作流治理入口。
    """

    def __init__(self):
        self.workflow_validator = WorkflowValidator()
        self.state_validator = StateValidator()
        self.transition_validator = TransitionValidator()
        self.decision_validator = DecisionValidator()

    def validate_workflow(
        self,
        workflow_type: WorkflowType,
        state: GraphState,
    ) -> tuple[bool, list[ValidationResult]]:
        """
        验证工作流

        Args:
            workflow_type: 工作流类型
            state: Graph 状态

        Returns:
            (是否通过, 验证结果列表)
        """
        results = self.workflow_validator.validate(workflow_type, state)
        passed = not self.workflow_validator.has_errors(results)

        return passed, results

    def validate_state(self, state: GraphState) -> tuple[bool, list[ValidationResult]]:
        """
        验证状态

        Args:
            state: Graph 状态

        Returns:
            (是否通过, 验证结果列表)
        """
        results = self.state_validator.validate(state)
        has_errors = any(not r.passed and r.level == ValidationLevel.ERROR for r in results)

        return not has_errors, results

    def validate_agent_availability(self, agent: Any) -> tuple[bool, list[ValidationResult]]:
        """Validate that an agent exists and is available for routing."""
        payload = agent.to_dict() if hasattr(agent, "to_dict") else (agent or {})
        status = payload.get("status", "")
        results = [
            ValidationResult(
                rule_name="agent_exists",
                level=ValidationLevel.ERROR,
                passed=bool(payload.get("agent_id")),
                message="Agent exists" if payload.get("agent_id") else "Agent missing",
            ),
            ValidationResult(
                rule_name="agent_available",
                level=ValidationLevel.ERROR,
                passed=status in (AgentStatus.ACTIVE.value, AgentStatus.REGISTERED.value),
                message=f"Agent status {status} is routable",
                metadata={"status": status},
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_capability(self, capability: Any) -> tuple[bool, list[ValidationResult]]:
        """Validate capability model consistency."""
        payload = capability.to_dict() if hasattr(capability, "to_dict") else (capability or {})
        results = [
            ValidationResult(
                rule_name="capability_has_id",
                level=ValidationLevel.ERROR,
                passed=bool(payload.get("capability_id")),
                message="Capability ID exists",
            ),
            ValidationResult(
                rule_name="capability_has_name",
                level=ValidationLevel.ERROR,
                passed=bool(payload.get("name")),
                message="Capability name exists",
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_agent_route(self, route: Any, registry: Any) -> tuple[bool, list[ValidationResult]]:
        """Validate multi-agent routing decision."""
        payload = route.to_dict() if hasattr(route, "to_dict") else route
        selected_agents = payload.get("selected_agents", [])
        results = [
            ValidationResult(
                rule_name="agent_route_has_workflow",
                level=ValidationLevel.ERROR,
                passed=bool(payload.get("workflow_id")),
                message="Route workflow ID exists",
            ),
            ValidationResult(
                rule_name="agent_route_has_agent",
                level=ValidationLevel.ERROR,
                passed=bool(selected_agents),
                message="Route selected at least one agent",
            ),
        ]
        for agent_id in selected_agents:
            agent = registry.get_agent(agent_id)
            passed, availability = self.validate_agent_availability(agent)
            results.extend(availability)
            if not passed:
                break
        for capability_id in payload.get("required_capabilities", []):
            capability = registry.get_capability(capability_id)
            passed, capability_results = self.validate_capability(capability)
            results.extend(capability_results)
            if not passed:
                break
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_agent_handoff(self, handoff: Any, registry: Any) -> tuple[bool, list[ValidationResult]]:
        """Validate agent-to-agent handoff preserves workflow context."""
        payload = handoff.to_dict() if hasattr(handoff, "to_dict") else handoff
        results = [
            ValidationResult(
                rule_name="handoff_same_workflow",
                level=ValidationLevel.ERROR,
                passed=bool(payload.get("workflow_id")),
                message="Handoff workflow ID exists",
            ),
            ValidationResult(
                rule_name="handoff_from_agent_exists",
                level=ValidationLevel.ERROR,
                passed=bool(registry.get_agent(payload.get("from_agent", ""))),
                message="Source agent exists",
            ),
            ValidationResult(
                rule_name="handoff_to_agent_exists",
                level=ValidationLevel.ERROR,
                passed=bool(registry.get_agent(payload.get("to_agent", ""))),
                message="Target agent exists",
            ),
            ValidationResult(
                rule_name="handoff_preserves_state",
                level=ValidationLevel.ERROR,
                passed=isinstance(payload.get("workflow_state"), dict) and bool(payload.get("workflow_state")),
                message="Workflow state preserved",
            ),
            ValidationResult(
                rule_name="handoff_preserves_context",
                level=ValidationLevel.ERROR,
                passed=isinstance(payload.get("context_state"), dict),
                message="Context state preserved",
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_supervisor_decision(self, decision: dict[str, Any]) -> tuple[bool, list[ValidationResult]]:
        """Validate supervisor decision event."""
        results = [
            ValidationResult(
                rule_name="supervisor_decision_has_id",
                level=ValidationLevel.ERROR,
                passed=bool(decision.get("decision_id")),
                message="Supervisor decision ID exists",
            ),
            ValidationResult(
                rule_name="supervisor_decision_has_workflow",
                level=ValidationLevel.ERROR,
                passed=bool(decision.get("workflow_id")),
                message="Supervisor decision workflow ID exists",
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_business_domain_operation(self, operation: dict[str, Any]) -> tuple[bool, list[ValidationResult]]:
        """Validate Phase 7 business-domain access constraints."""
        results = [
            ValidationResult(
                rule_name="business_domain_has_workflow",
                level=ValidationLevel.ERROR,
                passed=bool(operation.get("workflow_id")),
                message="Business domain operation has workflow_id",
                metadata={"workflow_id": operation.get("workflow_id", "")},
            ),
            ValidationResult(
                rule_name="business_domain_access_path",
                level=ValidationLevel.ERROR,
                passed=operation.get("access_path") == "business_domain_layer",
                message="Business data access goes through BusinessDomainLayer",
                metadata={"access_path": operation.get("access_path", "")},
            ),
            ValidationResult(
                rule_name="business_domain_traceability",
                level=ValidationLevel.WARNING,
                passed=operation.get("trace_enabled", True) is True,
                message="Business domain traceability is enabled",
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_product_knowledge_operation(self, operation: dict[str, Any]) -> tuple[bool, list[ValidationResult]]:
        """Validate Phase 7 Stage 2.1 product-knowledge access constraints."""
        results = [
            ValidationResult(
                rule_name="product_knowledge_access_path",
                level=ValidationLevel.ERROR,
                passed=operation.get("access_path") == "product_knowledge_layer",
                message="Product knowledge access goes through ProductKnowledgeLayer",
                metadata={"access_path": operation.get("access_path", "")},
            ),
            ValidationResult(
                rule_name="product_knowledge_domain_dependency",
                level=ValidationLevel.ERROR,
                passed=operation.get("business_domain_layer") is True,
                message="Product Knowledge Layer depends on Business Domain Layer",
            ),
            ValidationResult(
                rule_name="product_agent_no_direct_model",
                level=ValidationLevel.ERROR,
                passed=operation.get("agent_direct_model_access") is not True,
                message="Product Agent does not directly maintain product models",
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_product_search_operation(self, operation: dict[str, Any]) -> tuple[bool, list[ValidationResult]]:
        """Validate Phase 7 Stage 2.2 product-search access constraints."""
        results = [
            ValidationResult(
                rule_name="product_search_access_path",
                level=ValidationLevel.ERROR,
                passed=operation.get("access_path") == "product_search_engine",
                message="Product search access goes through ProductSearchLayer",
                metadata={"access_path": operation.get("access_path", "")},
            ),
            ValidationResult(
                rule_name="product_search_knowledge_dependency",
                level=ValidationLevel.ERROR,
                passed=operation.get("product_knowledge_layer") is True,
                message="Product Search Engine depends on Product Knowledge Layer",
            ),
            ValidationResult(
                rule_name="product_search_agent_boundary",
                level=ValidationLevel.ERROR,
                passed=operation.get("agent_direct_search_logic") is not True,
                message="Product Agent does not directly execute search logic",
            ),
            ValidationResult(
                rule_name="product_search_traceability",
                level=ValidationLevel.WARNING,
                passed=operation.get("trace_enabled", True) is True,
                message="Product search traceability is enabled",
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_product_recommendation_operation(self, operation: dict[str, Any]) -> tuple[bool, list[ValidationResult]]:
        """Validate Phase 7 Stage 2.3 product-recommendation access constraints."""
        results = [
            ValidationResult(
                rule_name="product_recommendation_access_path",
                level=ValidationLevel.ERROR,
                passed=operation.get("access_path") == "product_recommendation_engine",
                message="Product recommendation access goes through ProductRecommendationLayer",
                metadata={"access_path": operation.get("access_path", "")},
            ),
            ValidationResult(
                rule_name="product_recommendation_knowledge_dependency",
                level=ValidationLevel.ERROR,
                passed=operation.get("product_knowledge_layer") is True,
                message="Product Recommendation Engine depends on Product Knowledge Layer",
            ),
            ValidationResult(
                rule_name="product_recommendation_search_dependency",
                level=ValidationLevel.ERROR,
                passed=operation.get("product_search_engine") is True,
                message="Product Recommendation Engine depends on Product Search Engine",
            ),
            ValidationResult(
                rule_name="product_recommendation_agent_boundary",
                level=ValidationLevel.ERROR,
                passed=operation.get("agent_direct_recommendation_logic") is not True,
                message="Product Agent does not directly execute recommendation logic",
            ),
            ValidationResult(
                rule_name="product_recommendation_traceability",
                level=ValidationLevel.WARNING,
                passed=operation.get("trace_enabled", True) is True,
                message="Product recommendation traceability is enabled",
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_product_comparison_operation(self, operation: dict[str, Any]) -> tuple[bool, list[ValidationResult]]:
        """Validate Phase 7 Stage 2.4 product-comparison access constraints."""
        results = [
            ValidationResult(
                rule_name="product_comparison_access_path",
                level=ValidationLevel.ERROR,
                passed=operation.get("access_path") == "product_comparison_engine",
                message="Product comparison access goes through ProductComparisonLayer",
                metadata={"access_path": operation.get("access_path", "")},
            ),
            ValidationResult(
                rule_name="product_comparison_knowledge_dependency",
                level=ValidationLevel.ERROR,
                passed=operation.get("product_knowledge_layer") is True,
                message="Product Comparison Engine depends on Product Knowledge Layer",
            ),
            ValidationResult(
                rule_name="product_comparison_search_dependency",
                level=ValidationLevel.ERROR,
                passed=operation.get("product_search_engine") is True,
                message="Product Comparison Engine depends on Product Search Engine",
            ),
            ValidationResult(
                rule_name="product_comparison_recommendation_dependency",
                level=ValidationLevel.ERROR,
                passed=operation.get("product_recommendation_engine") is True,
                message="Product Comparison Engine depends on Product Recommendation Engine",
            ),
            ValidationResult(
                rule_name="product_comparison_agent_boundary",
                level=ValidationLevel.ERROR,
                passed=operation.get("agent_direct_comparison_logic") is not True,
                message="Product Agent does not directly execute comparison logic",
            ),
            ValidationResult(
                rule_name="product_comparison_traceability",
                level=ValidationLevel.WARNING,
                passed=operation.get("trace_enabled", True) is True,
                message="Product comparison traceability is enabled",
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_product_consultation_operation(self, operation: dict[str, Any]) -> tuple[bool, list[ValidationResult]]:
        """Validate Phase 7 Stage 2.5 product-consultation access constraints."""
        results = [
            ValidationResult(
                rule_name="product_consultation_access_path",
                level=ValidationLevel.ERROR,
                passed=operation.get("access_path") == "product_consultation_workflow",
                message="Product consultation access goes through ProductConsultationLayer",
                metadata={"access_path": operation.get("access_path", "")},
            ),
            ValidationResult(
                rule_name="product_consultation_knowledge_dependency",
                level=ValidationLevel.ERROR,
                passed=operation.get("product_knowledge_layer") is True,
                message="Product Consultation Workflow depends on Product Knowledge Layer",
            ),
            ValidationResult(
                rule_name="product_consultation_search_dependency",
                level=ValidationLevel.ERROR,
                passed=operation.get("product_search_engine") is True,
                message="Product Consultation Workflow depends on Product Search Engine",
            ),
            ValidationResult(
                rule_name="product_consultation_recommendation_dependency",
                level=ValidationLevel.ERROR,
                passed=operation.get("product_recommendation_engine") is True,
                message="Product Consultation Workflow depends on Product Recommendation Engine",
            ),
            ValidationResult(
                rule_name="product_consultation_comparison_dependency",
                level=ValidationLevel.ERROR,
                passed=operation.get("product_comparison_engine") is True,
                message="Product Consultation Workflow depends on Product Comparison Engine",
            ),
            ValidationResult(
                rule_name="product_consultation_agent_boundary",
                level=ValidationLevel.ERROR,
                passed=operation.get("agent_direct_consultation_logic") is not True,
                message="Product Agent does not directly execute consultation logic",
            ),
            ValidationResult(
                rule_name="product_consultation_traceability",
                level=ValidationLevel.WARNING,
                passed=operation.get("trace_enabled", True) is True,
                message="Product consultation traceability is enabled",
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_inventory_intelligence_operation(self, operation: dict[str, Any]) -> tuple[bool, list[ValidationResult]]:
        """Validate Phase 7 Stage 2.6 inventory-intelligence access constraints."""
        dependency_checks = [
            ("inventory_product_knowledge_dependency", "product_knowledge_layer", "Product Knowledge Layer"),
            ("inventory_product_search_dependency", "product_search_engine", "Product Search Engine"),
            ("inventory_product_recommendation_dependency", "product_recommendation_engine", "Product Recommendation Engine"),
            ("inventory_product_comparison_dependency", "product_comparison_engine", "Product Comparison Engine"),
            ("inventory_product_consultation_dependency", "product_consultation_workflow", "Product Consultation Workflow"),
        ]
        results = [
            ValidationResult(
                rule_name="inventory_intelligence_has_workflow",
                level=ValidationLevel.ERROR,
                passed=bool(operation.get("workflow_id")),
                message="Inventory Intelligence operation has workflow_id",
                metadata={"workflow_id": operation.get("workflow_id", "")},
            ),
            ValidationResult(
                rule_name="inventory_intelligence_access_path",
                level=ValidationLevel.ERROR,
                passed=operation.get("access_path") == "inventory_intelligence_layer",
                message="Inventory intelligence access goes through InventoryIntelligenceLayer",
                metadata={"access_path": operation.get("access_path", "")},
            ),
            *[
                ValidationResult(
                    rule_name=rule_name,
                    level=ValidationLevel.ERROR,
                    passed=operation.get(field_name) is True,
                    message=f"Inventory Intelligence depends on {label}",
                )
                for rule_name, field_name, label in dependency_checks
            ],
            ValidationResult(
                rule_name="inventory_intelligence_agent_boundary",
                level=ValidationLevel.ERROR,
                passed=operation.get("agent_direct_inventory_logic") is not True,
                message="Product Agent does not directly execute inventory intelligence logic",
            ),
            ValidationResult(
                rule_name="inventory_intelligence_traceability",
                level=ValidationLevel.WARNING,
                passed=operation.get("trace_enabled", True) is True,
                message="Inventory intelligence traceability is enabled",
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_logistics_agent_operation(self, operation: dict[str, Any]) -> tuple[bool, list[ValidationResult]]:
        """Validate Phase 7 Stage 3 logistics-agent access constraints."""
        dependency_checks = [
            ("logistics_business_domain_dependency", "business_domain_layer", "Business Domain Layer"),
            ("logistics_workflow_runtime_dependency", "workflow_runtime", "Workflow Runtime"),
            ("logistics_state_runtime_dependency", "state_runtime", "State Runtime"),
            ("logistics_persistence_runtime_dependency", "persistence_runtime", "Persistence Layer"),
            ("logistics_governance_runtime_dependency", "governance_runtime", "Governance Layer"),
            ("logistics_decision_trace_dependency", "decision_trace_runtime", "Decision Trace Layer"),
            ("logistics_interrupt_runtime_dependency", "interrupt_runtime", "Interrupt Runtime"),
            ("logistics_checkpoint_runtime_dependency", "checkpoint_runtime", "Checkpoint Runtime"),
            ("logistics_multi_agent_runtime_dependency", "multi_agent_runtime", "Multi-Agent Runtime"),
            ("logistics_supervisor_agent_dependency", "supervisor_agent", "Supervisor Agent"),
        ]
        results = [
            ValidationResult(
                rule_name="logistics_agent_has_workflow",
                level=ValidationLevel.ERROR,
                passed=bool(operation.get("workflow_id")),
                message="Logistics Agent operation has workflow_id",
                metadata={"workflow_id": operation.get("workflow_id", "")},
            ),
            ValidationResult(
                rule_name="logistics_agent_access_path",
                level=ValidationLevel.ERROR,
                passed=operation.get("access_path") == "logistics_agent",
                message="Logistics access goes through LogisticsAgent",
                metadata={"access_path": operation.get("access_path", "")},
            ),
            *[
                ValidationResult(
                    rule_name=rule_name,
                    level=ValidationLevel.ERROR,
                    passed=operation.get(field_name) is True,
                    message=f"Logistics Agent depends on {label}",
                )
                for rule_name, field_name, label in dependency_checks
            ],
            ValidationResult(
                rule_name="logistics_repository_boundary",
                level=ValidationLevel.ERROR,
                passed=operation.get("agent_direct_data_access") is not True,
                message="Logistics Agent does not bypass LogisticsRepository",
            ),
            ValidationResult(
                rule_name="logistics_agent_no_controller_dispatch",
                level=ValidationLevel.ERROR,
                passed=operation.get("controller_if_else_dispatch") is not True,
                message="Logistics Agent remains runtime-driven and graph-aware",
            ),
            ValidationResult(
                rule_name="logistics_traceability",
                level=ValidationLevel.WARNING,
                passed=operation.get("trace_enabled", True) is True,
                message="Logistics Agent traceability is enabled",
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_refund_agent_operation(self, operation: dict[str, Any]) -> tuple[bool, list[ValidationResult]]:
        """Validate Phase 7 Stage 4 refund-agent access constraints."""
        dependency_checks = [
            ("refund_business_domain_dependency", "business_domain_layer", "Business Domain Layer"),
            ("refund_workflow_runtime_dependency", "workflow_runtime", "Workflow Runtime"),
            ("refund_state_runtime_dependency", "state_runtime", "State Runtime"),
            ("refund_persistence_runtime_dependency", "persistence_runtime", "Persistence Layer"),
            ("refund_governance_runtime_dependency", "governance_runtime", "Governance Layer"),
            ("refund_decision_trace_dependency", "decision_trace_runtime", "Decision Trace Layer"),
            ("refund_interrupt_runtime_dependency", "interrupt_runtime", "Interrupt Runtime"),
            ("refund_checkpoint_runtime_dependency", "checkpoint_runtime", "Checkpoint Runtime"),
            ("refund_multi_agent_runtime_dependency", "multi_agent_runtime", "Multi-Agent Runtime"),
            ("refund_supervisor_agent_dependency", "supervisor_agent", "Supervisor Agent"),
        ]
        results = [
            ValidationResult(
                rule_name="refund_agent_has_workflow",
                level=ValidationLevel.ERROR,
                passed=bool(operation.get("workflow_id")),
                message="Refund Agent operation has workflow_id",
                metadata={"workflow_id": operation.get("workflow_id", "")},
            ),
            ValidationResult(
                rule_name="refund_agent_access_path",
                level=ValidationLevel.ERROR,
                passed=operation.get("access_path") == "refund_agent",
                message="After-sales access goes through RefundAgent",
                metadata={"access_path": operation.get("access_path", "")},
            ),
            *[
                ValidationResult(
                    rule_name=rule_name,
                    level=ValidationLevel.ERROR,
                    passed=operation.get(field_name) is True,
                    message=f"Refund Agent depends on {label}",
                )
                for rule_name, field_name, label in dependency_checks
            ],
            ValidationResult(
                rule_name="refund_repository_boundary",
                level=ValidationLevel.ERROR,
                passed=operation.get("agent_direct_data_access") is not True,
                message="Refund Agent does not bypass RefundRepository",
            ),
            ValidationResult(
                rule_name="refund_agent_no_controller_dispatch",
                level=ValidationLevel.ERROR,
                passed=operation.get("controller_if_else_dispatch") is not True,
                message="Refund Agent remains runtime-driven and graph-aware",
            ),
            ValidationResult(
                rule_name="refund_traceability",
                level=ValidationLevel.WARNING,
                passed=operation.get("trace_enabled", True) is True,
                message="Refund Agent traceability is enabled",
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_complaint_agent_operation(self, operation: dict[str, Any]) -> tuple[bool, list[ValidationResult]]:
        """Validate Phase 7 Stage 5 complaint-agent access constraints."""
        dependency_checks = [
            ("complaint_business_domain_dependency", "business_domain_layer", "Business Domain Layer"),
            ("complaint_workflow_runtime_dependency", "workflow_runtime", "Workflow Runtime"),
            ("complaint_state_runtime_dependency", "state_runtime", "State Runtime"),
            ("complaint_persistence_runtime_dependency", "persistence_runtime", "Persistence Layer"),
            ("complaint_governance_runtime_dependency", "governance_runtime", "Governance Layer"),
            ("complaint_decision_trace_dependency", "decision_trace_runtime", "Decision Trace Layer"),
            ("complaint_interrupt_runtime_dependency", "interrupt_runtime", "Interrupt Runtime"),
            ("complaint_checkpoint_runtime_dependency", "checkpoint_runtime", "Checkpoint Runtime"),
            ("complaint_multi_agent_runtime_dependency", "multi_agent_runtime", "Multi-Agent Runtime"),
            ("complaint_supervisor_agent_dependency", "supervisor_agent", "Supervisor Agent"),
        ]
        results = [
            ValidationResult(
                rule_name="complaint_agent_has_workflow",
                level=ValidationLevel.ERROR,
                passed=bool(operation.get("workflow_id")),
                message="Complaint Agent operation has workflow_id",
            ),
            ValidationResult(
                rule_name="complaint_agent_access_path",
                level=ValidationLevel.ERROR,
                passed=operation.get("access_path") == "complaint_agent",
                message="Complaint access goes through ComplaintAgent",
            ),
            *[
                ValidationResult(
                    rule_name=rule_name,
                    level=ValidationLevel.ERROR,
                    passed=operation.get(field_name) is True,
                    message=f"Complaint Agent depends on {label}",
                )
                for rule_name, field_name, label in dependency_checks
            ],
            ValidationResult(
                rule_name="complaint_repository_boundary",
                level=ValidationLevel.ERROR,
                passed=operation.get("agent_direct_data_access") is not True,
                message="Complaint Agent does not bypass ComplaintRepository",
            ),
            ValidationResult(
                rule_name="complaint_agent_no_controller_dispatch",
                level=ValidationLevel.ERROR,
                passed=operation.get("controller_if_else_dispatch") is not True,
                message="Complaint Agent remains runtime-driven and graph-aware",
            ),
            ValidationResult(
                rule_name="complaint_traceability",
                level=ValidationLevel.WARNING,
                passed=operation.get("trace_enabled", True) is True,
                message="Complaint Agent traceability is enabled",
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_transition(
        self,
        from_status: WorkflowStatus,
        to_status: WorkflowStatus,
    ) -> tuple[bool, ValidationResult]:
        """
        验证状态转换

        Args:
            from_status: 源状态
            to_status: 目标状态

        Returns:
            (是否通过, 验证结果)
        """
        result = self.transition_validator.validate_transition(from_status, to_status)
        return result.passed, result

    def validate_checkpoint(self, checkpoint: Any) -> tuple[bool, list[ValidationResult]]:
        """验证 Checkpoint 有效性"""
        payload = checkpoint.to_dict() if hasattr(checkpoint, "to_dict") else checkpoint
        results = [
            ValidationResult(
                rule_name="checkpoint_has_id",
                level=ValidationLevel.ERROR,
                passed=bool(payload.get("checkpoint_id")),
                message="Checkpoint ID exists" if payload.get("checkpoint_id") else "Checkpoint ID missing",
            ),
            ValidationResult(
                rule_name="checkpoint_has_state",
                level=ValidationLevel.ERROR,
                passed=isinstance(payload.get("state_snapshot"), dict) and bool(payload.get("state_snapshot")),
                message="Checkpoint state snapshot exists",
            ),
            ValidationResult(
                rule_name="checkpoint_has_node",
                level=ValidationLevel.ERROR,
                passed=bool(payload.get("current_node")),
                message="Checkpoint current node exists",
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_resume(self, resume: Any) -> tuple[bool, list[ValidationResult]]:
        """验证 Resume 有效性"""
        payload = resume.to_dict() if hasattr(resume, "to_dict") else resume
        results = [
            ValidationResult(
                rule_name="resume_has_checkpoint",
                level=ValidationLevel.ERROR,
                passed=bool(payload.get("checkpoint_reference")),
                message="Resume checkpoint reference exists",
            ),
            ValidationResult(
                rule_name="resume_has_workflow_state",
                level=ValidationLevel.ERROR,
                passed=isinstance(payload.get("workflow_state"), dict) and bool(payload.get("workflow_state")),
                message="Resume workflow state exists",
            ),
            ValidationResult(
                rule_name="resume_valid_flag",
                level=ValidationLevel.ERROR,
                passed=payload.get("valid", False) is True,
                message="Resume validity flag is true",
                metadata={"errors": payload.get("validation_errors", [])},
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_interrupt(self, interrupt: Any) -> tuple[bool, list[ValidationResult]]:
        """验证 Interrupt 有效性"""
        payload = interrupt.to_dict() if hasattr(interrupt, "to_dict") else interrupt
        results = [
            ValidationResult(
                rule_name="interrupt_has_reason",
                level=ValidationLevel.ERROR,
                passed=bool(payload.get("interrupt_reason")),
                message="Interrupt reason exists",
            ),
            ValidationResult(
                rule_name="interrupt_has_checkpoint",
                level=ValidationLevel.ERROR,
                passed=bool(payload.get("checkpoint_reference")),
                message="Interrupt checkpoint reference exists",
            ),
            ValidationResult(
                rule_name="interrupt_has_state",
                level=ValidationLevel.ERROR,
                passed=isinstance(payload.get("workflow_state"), dict),
                message="Interrupt state exists",
            ),
        ]
        return not any(not r.passed and r.level == ValidationLevel.ERROR for r in results), results

    def validate_lifecycle_transition(
        self,
        from_status: WorkflowStatus,
        to_status: WorkflowStatus,
    ) -> tuple[bool, ValidationResult]:
        """Stage 5 生命周期转换校验入口"""
        return self.validate_transition(from_status, to_status)

    def validate_decision(
        self,
        selected_workflow: Optional[WorkflowType],
        next_node: str,
        confidence: float,
    ) -> tuple[bool, list[ValidationResult]]:
        """
        验证决策

        Args:
            selected_workflow: 选中的工作流
            next_node: 下一个节点
            confidence: 置信度

        Returns:
            (是否通过, 验证结果列表)
        """
        results = self.decision_validator.validate_decision(
            selected_workflow, next_node, confidence
        )
        has_errors = any(not r.passed and r.level == ValidationLevel.ERROR for r in results)

        return not has_errors, results


# 全局单例
workflow_governance = WorkflowGovernance()
