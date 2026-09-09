"""
Decision Trace System - 决策追踪系统

职责：
- 记录所有 Workflow 决策过程
- 追踪决策链路
- 支持决策回溯和审计
- 提供决策分析能力

设计原则：
- Complete Traceability：所有决策完整记录
- Immutable：决策记录不可变
- Queryable：支持灵活查询
- Performance：低开销记录
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from app.workflow.condition_engine import Decision
from app.workflow.models import TraceEventType

logger = logging.getLogger(__name__)


@dataclass
class DecisionTrace:
    """
    决策追踪记录

    记录单次决策的完整信息。
    """
    decision_id: str                           # 决策 ID
    decision_time: datetime                    # 决策时间
    workflow_state: dict[str, Any]             # 决策时的工作流状态快照
    selected_workflow: Optional[str]           # 选中的工作流
    selected_branch: str                       # 选中的分支
    next_node: str                             # 下一个节点
    decision_reason: str                       # 决策理由
    decision_confidence: float                 # 决策置信度
    decision_metadata: dict[str, Any]          # 决策元数据
    session_id: Optional[str] = None           # 会话 ID
    user_input: Optional[str] = None           # 用户输入
    current_intent: Optional[str] = None       # 当前意图

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "decision_id": self.decision_id,
            "decision_time": self.decision_time.isoformat(),
            "workflow_state": self.workflow_state,
            "selected_workflow": self.selected_workflow,
            "selected_branch": self.selected_branch,
            "next_node": self.next_node,
            "decision_reason": self.decision_reason,
            "decision_confidence": self.decision_confidence,
            "decision_metadata": self.decision_metadata,
            "session_id": self.session_id,
            "user_input": self.user_input,
            "current_intent": self.current_intent,
        }


@dataclass
class DecisionPath:
    """
    决策路径

    记录一个完整会话的决策链。
    """
    path_id: str                               # 路径 ID
    session_id: str                            # 会话 ID
    decisions: list[DecisionTrace] = field(default_factory=list)  # 决策链
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    def add_decision(self, trace: DecisionTrace) -> None:
        """添加决策"""
        self.decisions.append(trace)

    def get_decision_count(self) -> int:
        """获取决策数量"""
        return len(self.decisions)

    def get_last_decision(self) -> Optional[DecisionTrace]:
        """获取最后一次决策"""
        return self.decisions[-1] if self.decisions else None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "path_id": self.path_id,
            "session_id": self.session_id,
            "decisions": [d.to_dict() for d in self.decisions],
            "decision_count": self.get_decision_count(),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class WorkflowTraceEvent:
    """Workflow 生命周期事件追踪记录"""
    event_id: str
    event_type: TraceEventType
    workflow_id: str
    branch_id: str
    node: str
    reason: str
    timestamp: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
    trace_reference: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    actor: str = "system"
    source: str = "decision_tracer"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "workflow_id": self.workflow_id,
            "branch_id": self.branch_id,
            "node": self.node,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "session_id": self.session_id,
            "trace_reference": self.trace_reference,
            "metadata": self.metadata,
            "actor": self.actor,
            "source": self.source,
        }


class DecisionTracer:
    """
    决策追踪器

    管理决策记录的创建、存储和查询。
    """

    def __init__(self):
        # 内存存储（生产环境应替换为持久化存储）
        self._traces: dict[str, DecisionTrace] = {}
        self._paths: dict[str, DecisionPath] = {}
        self._session_paths: dict[str, str] = {}  # session_id -> path_id
        self._events: dict[str, WorkflowTraceEvent] = {}
        self._events_by_workflow: dict[str, list[str]] = {}

    def trace_decision(
        self,
        decision: Decision,
        state: dict[str, Any],
        session_id: Optional[str] = None,
        user_input: Optional[str] = None,
        current_intent: Optional[str] = None,
    ) -> DecisionTrace:
        """
        记录决策

        Args:
            decision: 决策结果
            state: 决策时的状态快照
            session_id: 会话 ID
            user_input: 用户输入
            current_intent: 当前意图

        Returns:
            DecisionTrace: 决策追踪记录
        """
        # 创建决策追踪记录
        trace = DecisionTrace(
            decision_id=self._generate_decision_id(),
            decision_time=datetime.now(),
            workflow_state=self._snapshot_state(state),
            selected_workflow=decision.selected_workflow.value if decision.selected_workflow else None,
            selected_branch=decision.selected_branch,
            next_node=decision.next_node,
            decision_reason=decision.decision_reason,
            decision_confidence=decision.decision_confidence,
            decision_metadata=decision.decision_metadata,
            session_id=session_id,
            user_input=user_input,
            current_intent=current_intent,
        )

        # 存储决策
        self._traces[trace.decision_id] = trace

        # 添加到决策路径
        if session_id:
            self._add_to_path(session_id, trace)

        logger.debug(
            f"[DecisionTracer] 记录决策: {trace.decision_id} "
            f"(workflow={trace.selected_workflow}, node={trace.next_node}, confidence={trace.decision_confidence:.2f})"
        )

        return trace

    def get_trace(self, decision_id: str) -> Optional[DecisionTrace]:
        """
        获取决策追踪记录

        Args:
            decision_id: 决策 ID

        Returns:
            DecisionTrace: 决策追踪记录
        """
        return self._traces.get(decision_id)

    def get_path(self, session_id: str) -> Optional[DecisionPath]:
        """
        获取会话的决策路径

        Args:
            session_id: 会话 ID

        Returns:
            DecisionPath: 决策路径
        """
        path_id = self._session_paths.get(session_id)
        if path_id:
            return self._paths.get(path_id)
        return None

    def get_recent_decisions(self, limit: int = 10) -> list[DecisionTrace]:
        """
        获取最近的决策

        Args:
            limit: 返回数量限制

        Returns:
            决策列表
        """
        sorted_traces = sorted(
            self._traces.values(),
            key=lambda t: t.decision_time,
            reverse=True,
        )
        return sorted_traces[:limit]

    def get_decisions_by_workflow(self, workflow_type: str) -> list[DecisionTrace]:
        """
        获取特定工作流的所有决策

        Args:
            workflow_type: 工作流类型

        Returns:
            决策列表
        """
        return [
            trace for trace in self._traces.values()
            if trace.selected_workflow == workflow_type
        ]

    def get_stats(self) -> dict:
        """
        获取决策统计信息

        Returns:
            统计信息字典
        """
        total_decisions = len(self._traces)
        total_paths = len(self._paths)

        # 按工作流统计
        workflow_counts = {}
        for trace in self._traces.values():
            workflow = trace.selected_workflow or "unknown"
            workflow_counts[workflow] = workflow_counts.get(workflow, 0) + 1

        # 按分支统计
        branch_counts = {}
        for trace in self._traces.values():
            branch = trace.selected_branch
            branch_counts[branch] = branch_counts.get(branch, 0) + 1

        # 平均置信度
        avg_confidence = (
            sum(t.decision_confidence for t in self._traces.values()) / total_decisions
            if total_decisions > 0 else 0.0
        )

        return {
            "total_decisions": total_decisions,
            "total_paths": total_paths,
            "total_events": len(self._events),
            "workflow_distribution": workflow_counts,
            "branch_distribution": branch_counts,
            "average_confidence": round(avg_confidence, 2),
        }

    def trace_event(
        self,
        *,
        event_type: TraceEventType,
        workflow_id: str,
        branch_id: str = "main",
        node: str = "",
        reason: str = "",
        payload: dict[str, Any] | None = None,
        session_id: Optional[str] = None,
        trace_reference: Optional[str] = None,
        metadata: dict[str, Any] | None = None,
        actor: str = "system",
        source: str = "decision_tracer",
    ) -> WorkflowTraceEvent:
        """
        记录 Workflow 生命周期事件。

        Stage 5 新增事件类型：
        INTERRUPT / CHECKPOINT / RESUME / HANDOFF / RECOVERY / LIFECYCLE
        """
        event = WorkflowTraceEvent(
            event_id=self._generate_event_id(event_type),
            event_type=event_type,
            workflow_id=workflow_id,
            branch_id=branch_id,
            node=node,
            reason=reason,
            timestamp=datetime.now(),
            payload=payload or {},
            session_id=session_id,
            trace_reference=trace_reference,
            metadata=metadata or {},
            actor=actor,
            source=source,
        )
        self._events[event.event_id] = event
        self._events_by_workflow.setdefault(workflow_id, []).append(event.event_id)
        self._persist_event(event)
        logger.debug(
            f"[DecisionTracer] event={event_type.value} workflow={workflow_id} "
            f"node={node} reason={reason}"
        )
        return event

    def get_event(self, event_id: str) -> Optional[WorkflowTraceEvent]:
        return self._events.get(event_id)

    def get_timeline(self, workflow_id: str) -> list[WorkflowTraceEvent]:
        """获取 workflow 的完整事件时间线"""
        ids = self._events_by_workflow.get(workflow_id, [])
        events = [self._events[eid] for eid in ids if eid in self._events]
        if not events:
            events = self._load_events_from_repository(workflow_id)
        return sorted(events, key=lambda e: e.timestamp)

    def get_interrupt_timeline(self, workflow_id: str) -> list[WorkflowTraceEvent]:
        """获取中断/恢复/人工转接相关时间线"""
        interested = {
            TraceEventType.INTERRUPT,
            TraceEventType.CHECKPOINT,
            TraceEventType.RESUME,
            TraceEventType.HANDOFF,
            TraceEventType.RECOVERY,
        }
        return [e for e in self.get_timeline(workflow_id) if e.event_type in interested]

    def replay_workflow(self, workflow_id: str) -> dict[str, Any]:
        """生成 Workflow Replay 视图"""
        timeline = self.get_timeline(workflow_id)
        return {
            "workflow_id": workflow_id,
            "event_count": len(timeline),
            "events": [event.to_dict() for event in timeline],
            "interrupt_timeline": [
                event.to_dict() for event in self.get_interrupt_timeline(workflow_id)
            ],
        }

    def _generate_decision_id(self) -> str:
        """生成决策 ID"""
        return f"decision_{uuid.uuid4().hex[:12]}"

    def _generate_event_id(self, event_type: TraceEventType) -> str:
        """生成事件 ID"""
        return f"{event_type.value}_{uuid.uuid4().hex[:12]}"

    def restore_workflow_events(self, workflow_id: str) -> list[WorkflowTraceEvent]:
        """从 Repository 恢复 workflow trace events 到内存索引。"""
        return self._load_events_from_repository(workflow_id, hydrate=True)

    def query_events(
        self,
        workflow_id: str | None = None,
        event_type: TraceEventType | str | None = None,
    ) -> list[WorkflowTraceEvent]:
        """查询持久化 Trace Event。"""
        filters = {}
        if event_type:
            filters["event_type"] = event_type.value if hasattr(event_type, "value") else event_type
        events: list[WorkflowTraceEvent] = []
        try:
            from app.workflow.repository import workflow_repository
            records = workflow_repository.query(
                record_type="trace",
                workflow_id=workflow_id,
                filters=filters or None,
            )
        except Exception as exc:
            logger.warning(f"[DecisionTracer] trace query failed: {exc}")
            records = []
        for record in records:
            event = self._event_from_payload(record.get("payload", {}))
            if event:
                events.append(event)
        return sorted(events, key=lambda e: e.timestamp)

    def _snapshot_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        创建状态快照

        只记录关键字段，避免存储过大。
        """
        key_fields = [
            "current_intent",
            "intent_confidence",
            "slots_ready",
            "collected_slots",
            "workflow_status",
            "current_node",
            "rag_eligible",
            "rag_used",
            "tool_success",
            "selected_agent",
        ]

        return {
            key: state.get(key)
            for key in key_fields
            if key in state
        }

    def _persist_event(self, event: WorkflowTraceEvent) -> None:
        """持久化 Workflow Trace Event。"""
        try:
            from app.workflow.repository import workflow_repository
            workflow_repository.save(
                "trace",
                event.event_id,
                event.workflow_id,
                event,
                metadata={
                    "event_type": event.event_type.value,
                    "branch_id": event.branch_id,
                    "actor": event.actor,
                    "source": event.source,
                    **event.metadata,
                },
                preserve_created_at=False,
            )
        except Exception as exc:
            logger.warning(f"[DecisionTracer] trace persistence failed: {exc}")

    def _load_events_from_repository(
        self,
        workflow_id: str,
        hydrate: bool = True,
    ) -> list[WorkflowTraceEvent]:
        try:
            from app.workflow.repository import workflow_repository
            records = workflow_repository.query(record_type="trace", workflow_id=workflow_id)
        except Exception as exc:
            logger.warning(f"[DecisionTracer] trace load failed: {exc}")
            return []
        events: list[WorkflowTraceEvent] = []
        for record in records:
            event = self._event_from_payload(record.get("payload", {}))
            if not event:
                continue
            events.append(event)
            if hydrate:
                self._events[event.event_id] = event
                workflow_events = self._events_by_workflow.setdefault(workflow_id, [])
                if event.event_id not in workflow_events:
                    workflow_events.append(event.event_id)
        return events

    def _event_from_payload(self, payload: dict[str, Any]) -> Optional[WorkflowTraceEvent]:
        if not payload:
            return None
        try:
            return WorkflowTraceEvent(
                event_id=payload["event_id"],
                event_type=TraceEventType(payload["event_type"]),
                workflow_id=payload["workflow_id"],
                branch_id=payload.get("branch_id", "main"),
                node=payload.get("node", ""),
                reason=payload.get("reason", ""),
                timestamp=datetime.fromisoformat(payload["timestamp"]),
                payload=payload.get("payload", {}),
                session_id=payload.get("session_id"),
                trace_reference=payload.get("trace_reference"),
                metadata=payload.get("metadata", {}),
                actor=payload.get("actor", "system"),
                source=payload.get("source", "decision_tracer"),
            )
        except Exception as exc:
            logger.warning(f"[DecisionTracer] invalid trace payload: {exc}")
            return None

    def _add_to_path(self, session_id: str, trace: DecisionTrace) -> None:
        """
        将决策添加到路径

        Args:
            session_id: 会话 ID
            trace: 决策追踪记录
        """
        # 获取或创建路径
        path_id = self._session_paths.get(session_id)
        if not path_id:
            path_id = f"path_{uuid.uuid4().hex[:12]}"
            path = DecisionPath(
                path_id=path_id,
                session_id=session_id,
            )
            self._paths[path_id] = path
            self._session_paths[session_id] = path_id
        else:
            path = self._paths[path_id]

        # 添加决策
        path.add_decision(trace)

    def complete_path(self, session_id: str) -> None:
        """
        标记路径完成

        Args:
            session_id: 会话 ID
        """
        path = self.get_path(session_id)
        if path:
            path.completed_at = datetime.now()
            logger.info(
                f"[DecisionTracer] 路径完成: {path.path_id} "
                f"(session={session_id}, decisions={path.get_decision_count()})"
            )

    def clear_old_traces(self, days: int = 7) -> int:
        """
        清理旧的决策记录

        Args:
            days: 保留天数

        Returns:
            清理数量
        """
        cutoff = datetime.now().timestamp() - (days * 86400)
        old_ids = [
            trace_id for trace_id, trace in self._traces.items()
            if trace.decision_time.timestamp() < cutoff
        ]

        for trace_id in old_ids:
            del self._traces[trace_id]

        logger.info(f"[DecisionTracer] 清理了 {len(old_ids)} 条旧决策记录")
        return len(old_ids)


# 全局单例
decision_tracer = DecisionTracer()
