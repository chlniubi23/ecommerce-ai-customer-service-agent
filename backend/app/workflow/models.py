"""
Workflow Models - 工作流核心数据模型

定义 Conditional Workflow System 的核心数据结构。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional


class WorkflowType(str, Enum):
    """工作流类型"""
    REFUND = "refund"                    # 退款流程
    LOGISTICS = "logistics"               # 物流查询流程
    PRODUCT = "product"                   # 商品咨询流程
    ORDER = "order"                       # 订单查询流程
    COUPON = "coupon"                     # 优惠券流程
    TICKET = "ticket"                     # 工单创建流程
    HUMAN_TRANSFER = "human_transfer"     # 人工客服转接流程
    COMPLAINT = "complaint"               # 投诉流程
    GENERAL = "general"                   # 通用闲聊流程


class WorkflowStatus(str, Enum):
    """工作流状态"""
    CREATED = "created"           # 已创建
    ACTIVE = "active"             # 活跃执行中
    INTERRUPTED = "interrupted"   # 已中断
    PENDING = "pending"           # 待执行
    RUNNING = "running"           # 执行中
    WAITING_SLOT = "waiting_slot" # 等待 Slot 填充
    WAITING_USER = "waiting_user" # 等待用户输入
    WAITING_TOOL = "waiting_tool" # 等待外部工具
    WAITING_HUMAN = "waiting_human" # 等待人工客服
    RESUMING = "resuming"         # 恢复中
    PAUSED = "paused"             # 暂停
    COMPLETED = "completed"       # 完成
    FAILED = "failed"             # 失败
    CANCELLED = "cancelled"       # 取消


class BranchType(str, Enum):
    """分支类型"""
    MAIN = "main"           # 主流程
    SUB = "sub"             # 子流程
    FALLBACK = "fallback"   # 回退流程
    RECOVERY = "recovery"   # 恢复流程


class InterruptReason(str, Enum):
    """Workflow 中断原因"""
    MISSING_SLOT = "missing_slot"
    WAITING_USER_INPUT = "waiting_user_input"
    WAITING_EXTERNAL_TOOL = "waiting_external_tool"
    WAITING_HUMAN_AGENT = "waiting_human_agent"
    TIMEOUT = "timeout"
    MANUAL_PAUSE = "manual_pause"
    BUSINESS_RULE_PAUSE = "business_rule_pause"


class CheckpointType(str, Enum):
    """Checkpoint 类型"""
    AUTO = "auto"
    MANUAL = "manual"
    RECOVERY = "recovery"


class ResumeType(str, Enum):
    """Workflow 恢复类型"""
    USER = "user"
    SYSTEM = "system"
    AUTO = "auto"
    HUMAN = "human"


class HandoffStatus(str, Enum):
    """人工转接状态"""
    REQUESTED = "requested"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class LifecycleAction(str, Enum):
    """生命周期动作"""
    CREATE = "create"
    ACTIVATE = "activate"
    INTERRUPT = "interrupt"
    RESUME = "resume"
    COMPLETE = "complete"
    CANCEL = "cancel"
    FAIL = "fail"


class TraceEventType(str, Enum):
    """Workflow Trace 事件类型"""
    DECISION = "decision"
    INTERRUPT = "interrupt"
    CHECKPOINT = "checkpoint"
    RESUME = "resume"
    HANDOFF = "handoff"
    RECOVERY = "recovery"
    LIFECYCLE = "lifecycle"
    AGENT_SELECTED = "agent_selected"
    AGENT_ROUTED = "agent_routed"
    AGENT_HANDOFF = "agent_handoff"
    AGENT_TRANSFER = "agent_transfer"
    AGENT_ESCALATION = "agent_escalation"
    AGENT_RECOVERY = "agent_recovery"
    SUPERVISOR_DECISION = "supervisor_decision"


class AgentType(str, Enum):
    """Multi-agent runtime agent types."""
    ROUTING = "routing"
    REFUND = "refund"
    LOGISTICS = "logistics"
    PRODUCT = "product"
    COMPLAINT = "complaint"
    SUPERVISOR = "supervisor"
    GENERAL = "general"


class AgentStatus(str, Enum):
    """Agent lifecycle status."""
    REGISTERED = "registered"
    ACTIVE = "active"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    DISABLED = "disabled"


class AgentRouteType(str, Enum):
    """Agent routing strategy type."""
    SINGLE = "single"
    MULTI = "multi"
    FALLBACK = "fallback"
    SUPERVISOR_ESCALATION = "supervisor_escalation"


class AgentHandoffType(str, Enum):
    """Agent collaboration transfer type."""
    HANDOFF = "handoff"
    TRANSFER = "transfer"
    DELEGATION = "delegation"
    ESCALATION = "escalation"


@dataclass
class WorkflowMetadata:
    """
    工作流元数据

    记录工作流的注册信息和配置。
    """
    workflow_type: WorkflowType
    name: str                           # 工作流名称
    description: str                    # 工作流描述
    version: str = "1.0.0"              # 版本号
    requires_slots: list[str] = field(default_factory=list)  # 必需的 Slots
    optional_slots: list[str] = field(default_factory=list)  # 可选的 Slots
    requires_tools: list[str] = field(default_factory=list)  # 必需的 Tools
    requires_rag: bool = False          # 是否需要 RAG
    priority: int = 0                   # 优先级（数字越大优先级越高）
    tags: list[str] = field(default_factory=list)  # 标签
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class AgentCapability:
    """Agent capability model used by routing, matching and governance."""
    capability_id: str
    name: str
    description: str
    intent_patterns: list[str] = field(default_factory=list)
    workflow_types: list[str] = field(default_factory=list)
    required_slots: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "name": self.name,
            "description": self.description,
            "intent_patterns": self.intent_patterns,
            "workflow_types": self.workflow_types,
            "required_slots": self.required_slots,
            "metadata": self.metadata,
        }


@dataclass
class AgentDefinition:
    """Registered agent identity and metadata."""
    agent_id: str
    agent_name: str
    agent_type: AgentType
    description: str
    capabilities: list[str] = field(default_factory=list)
    status: AgentStatus = AgentStatus.REGISTERED
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type.value,
            "description": self.description,
            "capabilities": self.capabilities,
            "status": self.status.value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class AgentRoute:
    """Agent routing result persisted for replay and restart recovery."""
    route_id: str
    workflow_id: str
    selected_agents: list[str]
    route_type: AgentRouteType
    routing_reason: str
    required_capabilities: list[str]
    workflow_state: dict[str, Any]
    context: dict[str, Any]
    confidence: float
    created_at: datetime
    current_agent: str = ""
    fallback_agent: str = ""
    supervisor_agent: str = ""
    valid: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "workflow_id": self.workflow_id,
            "selected_agents": self.selected_agents,
            "current_agent": self.current_agent,
            "fallback_agent": self.fallback_agent,
            "supervisor_agent": self.supervisor_agent,
            "route_type": self.route_type.value,
            "routing_reason": self.routing_reason,
            "required_capabilities": self.required_capabilities,
            "workflow_state": self.workflow_state,
            "context": self.context,
            "confidence": self.confidence,
            "valid": self.valid,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class AgentHandoff:
    """Agent-to-agent handoff preserving workflow context."""
    handoff_id: str
    workflow_id: str
    from_agent: str
    to_agent: str
    handoff_type: AgentHandoffType
    handoff_reason: str
    workflow_state: dict[str, Any]
    context_state: dict[str, Any]
    conversation_history: list[dict[str, Any]]
    decision_trace_reference: str
    checkpoint_reference: str
    handoff_time: datetime
    status: str = "completed"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "workflow_id": self.workflow_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "handoff_type": self.handoff_type.value,
            "handoff_reason": self.handoff_reason,
            "workflow_state": self.workflow_state,
            "context_state": self.context_state,
            "conversation_history": self.conversation_history,
            "decision_trace_reference": self.decision_trace_reference,
            "checkpoint_reference": self.checkpoint_reference,
            "handoff_time": self.handoff_time.isoformat(),
            "status": self.status,
            "metadata": self.metadata,
        }


@dataclass
class AgentGraphNode:
    """Agent graph node extending workflow graph with an agent layer."""
    node_id: str
    agent_id: str
    node_name: str
    workflow_node: str = ""
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "node_name": self.node_name,
            "workflow_node": self.workflow_node,
            "dependencies": self.dependencies,
            "metadata": self.metadata,
        }


@dataclass
class AgentGraphEdge:
    """Agent graph transition edge."""
    edge_id: str
    from_agent: str
    to_agent: str
    condition: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "condition": self.condition,
            "metadata": self.metadata,
        }


@dataclass
class AgentExecutionContext:
    """Restart-safe agent execution and collaboration state."""
    execution_id: str
    workflow_id: str
    current_agent: str
    next_agent: str
    agent_execution_path: list[str]
    collaboration_path: list[dict[str, Any]]
    workflow_state: dict[str, Any]
    context_state: dict[str, Any]
    checkpoint_reference: str = ""
    status: str = "active"
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "current_agent": self.current_agent,
            "next_agent": self.next_agent,
            "agent_execution_path": self.agent_execution_path,
            "collaboration_path": self.collaboration_path,
            "workflow_state": self.workflow_state,
            "context_state": self.context_state,
            "checkpoint_reference": self.checkpoint_reference,
            "status": self.status,
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class WorkflowBranch:
    """
    工作流分支

    表示工作流的一个执行分支。
    """
    branch_id: str                      # 分支 ID
    branch_type: BranchType             # 分支类型
    branch_name: str                    # 分支名称
    parent_branch: Optional[str] = None # 父分支 ID
    next_nodes: list[str] = field(default_factory=list)  # 下一步可执行节点
    condition: Optional[Callable] = None  # 分支条件函数
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowContext:
    """
    工作流上下文

    记录工作流执行期间的上下文信息。
    """
    workflow_id: str                    # 工作流实例 ID
    workflow_type: WorkflowType         # 工作流类型
    status: WorkflowStatus              # 当前状态
    current_branch: str                 # 当前分支
    current_node: str                   # 当前节点
    visited_nodes: list[str] = field(default_factory=list)  # 已访问节点
    collected_slots: dict[str, Any] = field(default_factory=dict)  # 已收集 Slots
    tool_results: dict[str, Any] = field(default_factory=dict)  # 工具执行结果
    rag_context: Optional[str] = None   # RAG 检索上下文
    error: Optional[str] = None         # 错误信息
    started_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


@dataclass
class WorkflowDefinition:
    """
    工作流定义

    完整的工作流注册信息。
    """
    metadata: WorkflowMetadata          # 元数据
    branches: list[WorkflowBranch] = field(default_factory=list)  # 分支列表
    entry_node: str = "intent_node"     # 入口节点
    exit_nodes: list[str] = field(default_factory=lambda: ["response_node"])  # 出口节点

    def __post_init__(self):
        """初始化时自动添加主分支"""
        if not self.branches:
            main_branch = WorkflowBranch(
                branch_id="main",
                branch_type=BranchType.MAIN,
                branch_name="Main Branch",
                next_nodes=[self.entry_node],
            )
            self.branches.append(main_branch)


@dataclass
class WorkflowInterrupt:
    """统一 Workflow 中断模型"""
    workflow_id: str
    branch_id: str
    workflow_type: WorkflowType
    current_node: str
    workflow_state: dict[str, Any]
    interrupt_reason: InterruptReason
    interrupt_time: datetime
    checkpoint_reference: str
    interrupt_id: str = ""
    status: WorkflowStatus = WorkflowStatus.INTERRUPTED
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "interrupt_id": self.interrupt_id,
            "workflow_id": self.workflow_id,
            "branch_id": self.branch_id,
            "workflow_type": self.workflow_type.value,
            "current_node": self.current_node,
            "workflow_state": self.workflow_state,
            "interrupt_reason": self.interrupt_reason.value,
            "interrupt_time": self.interrupt_time.isoformat(),
            "checkpoint_reference": self.checkpoint_reference,
            "status": self.status.value,
            "metadata": self.metadata,
        }


@dataclass
class WorkflowCheckpoint:
    """Workflow 检查点模型"""
    checkpoint_id: str
    workflow_id: str
    branch_id: str
    current_node: str
    workflow_status: WorkflowStatus
    state_snapshot: dict[str, Any]
    slot_state: dict[str, Any]
    memory_context: Any
    workflow_context: dict[str, Any]
    decision_trace_reference: str
    timestamp: datetime
    branch_state: dict[str, Any] = field(default_factory=dict)
    trace_state: dict[str, Any] = field(default_factory=dict)
    checkpoint_type: CheckpointType = CheckpointType.AUTO
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "workflow_id": self.workflow_id,
            "branch_id": self.branch_id,
            "current_node": self.current_node,
            "workflow_status": self.workflow_status.value,
            "state_snapshot": self.state_snapshot,
            "slot_state": self.slot_state,
            "branch_state": self.branch_state,
            "memory_context": self.memory_context,
            "workflow_context": self.workflow_context,
            "decision_trace_reference": self.decision_trace_reference,
            "trace_state": self.trace_state,
            "timestamp": self.timestamp.isoformat(),
            "checkpoint_type": self.checkpoint_type.value,
            "version": self.version,
            "metadata": self.metadata,
        }


@dataclass
class WorkflowResume:
    """Workflow 恢复模型"""
    resume_id: str
    workflow_id: str
    branch_id: str
    checkpoint_reference: str
    resume_type: ResumeType
    workflow_state: dict[str, Any]
    branch_state: dict[str, Any]
    slot_state: dict[str, Any]
    context_state: dict[str, Any]
    trace_state: dict[str, Any]
    resume_time: datetime
    valid: bool = True
    validation_errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resume_id": self.resume_id,
            "workflow_id": self.workflow_id,
            "branch_id": self.branch_id,
            "checkpoint_reference": self.checkpoint_reference,
            "resume_type": self.resume_type.value,
            "workflow_state": self.workflow_state,
            "branch_state": self.branch_state,
            "slot_state": self.slot_state,
            "context_state": self.context_state,
            "trace_state": self.trace_state,
            "resume_time": self.resume_time.isoformat(),
            "valid": self.valid,
            "validation_errors": self.validation_errors,
            "metadata": self.metadata,
        }


@dataclass
class HumanHandoff:
    """AI 与人工客服协同模型"""
    handoff_id: str
    workflow_id: str
    handoff_reason: str
    handoff_time: datetime
    handoff_status: HandoffStatus
    assigned_agent: str = ""
    resume_time: Optional[datetime] = None
    branch_id: str = "main"
    workflow_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "workflow_id": self.workflow_id,
            "branch_id": self.branch_id,
            "handoff_reason": self.handoff_reason,
            "handoff_time": self.handoff_time.isoformat(),
            "handoff_status": self.handoff_status.value,
            "assigned_agent": self.assigned_agent,
            "resume_time": self.resume_time.isoformat() if self.resume_time else None,
            "workflow_state": self.workflow_state,
            "metadata": self.metadata,
        }


@dataclass
class WorkflowRecovery:
    """Workflow 恢复记录模型"""
    recovery_id: str
    workflow_id: str
    checkpoint_reference: str
    recovery_reason: str
    recovered_state: dict[str, Any]
    created_at: datetime
    status: str = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovery_id": self.recovery_id,
            "workflow_id": self.workflow_id,
            "checkpoint_reference": self.checkpoint_reference,
            "recovery_reason": self.recovery_reason,
            "recovered_state": self.recovered_state,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "metadata": self.metadata,
        }


@dataclass
class LifecycleTransition:
    """Workflow 生命周期状态转换记录"""
    transition_id: str
    workflow_id: str
    action: LifecycleAction
    from_status: WorkflowStatus
    to_status: WorkflowStatus
    timestamp: datetime
    actor: str = "system"
    reason: str = ""
    valid: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "workflow_id": self.workflow_id,
            "action": self.action.value,
            "from_status": self.from_status.value,
            "to_status": self.to_status.value,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "reason": self.reason,
            "valid": self.valid,
            "metadata": self.metadata,
        }


@dataclass
class WorkflowPersistenceRecord:
    """Repository 持久化记录"""
    record_id: str
    record_type: str
    workflow_id: str
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "workflow_id": self.workflow_id,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }
