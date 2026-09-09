"""Enterprise workflow system package."""

from app.workflow.agent_graph import AgentGraph, agent_graph
from app.workflow.agent_handoff import AgentHandoffManager, agent_handoff_manager
from app.workflow.agent_registry import AgentRegistry, agent_registry
from app.workflow.agent_router import AgentRouterEngine, agent_router_engine
from app.workflow.branch_manager import BranchExecution, BranchManager, branch_manager
from app.workflow.checkpoint_manager import WorkflowCheckpointManager, workflow_checkpoint_manager
from app.workflow.condition_engine import ConditionEngine, Decision, condition_engine
from app.workflow.conditional_edge import (
    ConditionalEdge,
    ConditionalEdgeRegistry,
    EdgeCondition,
    conditional_edge_registry,
    initialize_conditional_edges,
)
from app.workflow.governance import (
    ValidationLevel,
    ValidationResult,
    WorkflowGovernance,
    workflow_governance,
)
from app.workflow.handoff_manager import HumanHandoffManager, human_handoff_manager
from app.workflow.interrupt_manager import WorkflowInterruptManager, workflow_interrupt_manager
from app.workflow.lifecycle_manager import (
    LifecycleManager,
    LifecycleTransitionError,
    lifecycle_manager,
)
from app.workflow.models import (
    AgentCapability,
    AgentDefinition,
    AgentExecutionContext,
    AgentGraphEdge,
    AgentGraphNode,
    AgentHandoff,
    AgentHandoffType,
    AgentRoute,
    AgentRouteType,
    AgentStatus,
    AgentType,
    BranchType,
    CheckpointType,
    HandoffStatus,
    HumanHandoff,
    InterruptReason,
    LifecycleAction,
    LifecycleTransition,
    ResumeType,
    TraceEventType,
    WorkflowBranch,
    WorkflowCheckpoint,
    WorkflowContext,
    WorkflowDefinition,
    WorkflowInterrupt,
    WorkflowMetadata,
    WorkflowPersistenceRecord,
    WorkflowRecovery,
    WorkflowResume,
    WorkflowStatus,
    WorkflowType,
)
from app.workflow.recovery import RecoveryPoint, WorkflowRecoveryManager, workflow_recovery_manager
from app.workflow.recovery_manager import (
    WorkflowRecoveryStage5Manager,
    workflow_recovery_stage5_manager,
)
from app.workflow.registry import WorkflowRegistry, workflow_registry
from app.workflow.repository import WorkflowRepository, workflow_repository
from app.workflow.resume_manager import ResumeManager, resume_manager
from app.workflow.routing import (
    ConditionalWorkflowRouter,
    RoutingResult,
    conditional_workflow_router,
)
from app.workflow.slot_filling import SlotFillingContext, SlotFillingWorkflow, slot_filling_workflow
from app.workflow.supervisor_agent import SupervisorAgent, supervisor_agent
from app.workflow.decision_tracer import (
    DecisionPath,
    DecisionTrace,
    DecisionTracer,
    WorkflowTraceEvent,
    decision_tracer,
)

__all__ = [
    "AgentCapability",
    "AgentDefinition",
    "AgentExecutionContext",
    "AgentGraph",
    "AgentGraphEdge",
    "AgentGraphNode",
    "AgentHandoff",
    "AgentHandoffManager",
    "AgentHandoffType",
    "AgentRegistry",
    "AgentRoute",
    "AgentRouteType",
    "AgentRouterEngine",
    "AgentStatus",
    "AgentType",
    "BranchExecution",
    "BranchManager",
    "BranchType",
    "CheckpointType",
    "ConditionEngine",
    "ConditionalEdge",
    "ConditionalEdgeRegistry",
    "ConditionalWorkflowRouter",
    "Decision",
    "DecisionPath",
    "DecisionTrace",
    "DecisionTracer",
    "EdgeCondition",
    "HandoffStatus",
    "HumanHandoff",
    "HumanHandoffManager",
    "InterruptReason",
    "LifecycleAction",
    "LifecycleManager",
    "LifecycleTransition",
    "LifecycleTransitionError",
    "RecoveryPoint",
    "ResumeManager",
    "ResumeType",
    "RoutingResult",
    "SlotFillingContext",
    "SlotFillingWorkflow",
    "SupervisorAgent",
    "TraceEventType",
    "ValidationLevel",
    "ValidationResult",
    "WorkflowBranch",
    "WorkflowCheckpoint",
    "WorkflowCheckpointManager",
    "WorkflowContext",
    "WorkflowDefinition",
    "WorkflowGovernance",
    "WorkflowInterrupt",
    "WorkflowInterruptManager",
    "WorkflowMetadata",
    "WorkflowPersistenceRecord",
    "WorkflowRecovery",
    "WorkflowRecoveryManager",
    "WorkflowRecoveryStage5Manager",
    "WorkflowRegistry",
    "WorkflowRepository",
    "WorkflowResume",
    "WorkflowStatus",
    "WorkflowTraceEvent",
    "WorkflowType",
    "agent_graph",
    "agent_handoff_manager",
    "agent_registry",
    "agent_router_engine",
    "branch_manager",
    "condition_engine",
    "conditional_edge_registry",
    "conditional_workflow_router",
    "decision_tracer",
    "human_handoff_manager",
    "initialize_conditional_edges",
    "initialize_workflow_system",
    "lifecycle_manager",
    "resume_manager",
    "slot_filling_workflow",
    "supervisor_agent",
    "workflow_checkpoint_manager",
    "workflow_governance",
    "workflow_interrupt_manager",
    "workflow_recovery_manager",
    "workflow_recovery_stage5_manager",
    "workflow_registry",
    "workflow_repository",
]


def initialize_workflow_system() -> None:
    """Initialize graph, workflow, agent, domain and business runtime layers."""
    import logging

    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("Initializing Enterprise Workflow System...")
    logger.info("=" * 60)

    workflow_registry.initialize()
    initialize_conditional_edges()
    agent_registry.initialize_defaults()

    logger.info("Enterprise Workflow System initialized successfully")
    logger.info("=" * 60)
