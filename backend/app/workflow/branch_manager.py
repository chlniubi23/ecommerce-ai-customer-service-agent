"""
Workflow Branch Management - 工作流分支管理

职责：
- 管理工作流分支生命周期
- 支持主流程、子流程、分支流程
- 分支状态管理
- 分支执行轨迹追踪

设计原则：
- Independent Lifecycle：每个分支独立生命周期
- State Isolation：每个分支独立状态管理
- Traceable：每个分支独立执行轨迹
- Composable：支持分支嵌套和组合
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from app.workflow.models import (
    WorkflowType,
    WorkflowStatus,
    BranchType,
    WorkflowBranch,
    WorkflowContext,
)

logger = logging.getLogger(__name__)


@dataclass
class BranchExecution:
    """
    分支执行记录

    记录分支的执行过程和状态。
    """
    execution_id: str                          # 执行 ID
    branch: WorkflowBranch                     # 分支定义
    context: WorkflowContext                   # 执行上下文
    parent_execution: Optional[str] = None     # 父执行 ID
    child_executions: list[str] = field(default_factory=list)  # 子执行 ID 列表
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def is_active(self) -> bool:
        """是否活跃"""
        return self.context.status in [
            WorkflowStatus.ACTIVE,
            WorkflowStatus.INTERRUPTED,
            WorkflowStatus.RUNNING,
            WorkflowStatus.WAITING_SLOT,
            WorkflowStatus.WAITING_USER,
            WorkflowStatus.WAITING_TOOL,
            WorkflowStatus.WAITING_HUMAN,
            WorkflowStatus.RESUMING,
            WorkflowStatus.PAUSED,
        ]

    def is_completed(self) -> bool:
        """是否完成"""
        return self.context.status == WorkflowStatus.COMPLETED

    def is_failed(self) -> bool:
        """是否失败"""
        return self.context.status == WorkflowStatus.FAILED

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "execution_id": self.execution_id,
            "branch_id": self.branch.branch_id,
            "branch_type": self.branch.branch_type.value,
            "branch_name": self.branch.branch_name,
            "status": self.context.status.value,
            "current_node": self.context.current_node,
            "visited_nodes": self.context.visited_nodes,
            "parent_execution": self.parent_execution,
            "child_executions": self.child_executions,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class BranchManager:
    """
    分支管理器

    管理工作流分支的创建、执行和生命周期。
    """

    def __init__(self):
        self._executions: dict[str, BranchExecution] = {}
        self._active_executions: dict[str, str] = {}  # session_id -> execution_id
        self._workflow_execution_index: dict[str, str] = {}  # workflow_id -> execution_id

    def create_branch(
        self,
        branch: WorkflowBranch,
        workflow_type: WorkflowType,
        session_id: str,
        parent_execution_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> BranchExecution:
        """
        创建分支执行

        Args:
            branch: 分支定义
            workflow_type: 工作流类型
            session_id: 会话 ID
            parent_execution_id: 父执行 ID

        Returns:
            BranchExecution: 分支执行记录
        """
        execution_id = self._generate_execution_id()

        # 创建执行上下文
        context = WorkflowContext(
            workflow_id=workflow_id or execution_id,
            workflow_type=workflow_type,
            status=WorkflowStatus.PENDING,
            current_branch=branch.branch_id,
            current_node="START",
        )

        # 创建执行记录
        execution = BranchExecution(
            execution_id=execution_id,
            branch=branch,
            context=context,
            parent_execution=parent_execution_id,
        )

        # 存储执行记录
        self._executions[execution_id] = execution

        # 如果有父执行，添加到父执行的子执行列表
        if parent_execution_id:
            parent = self._executions.get(parent_execution_id)
            if parent:
                parent.child_executions.append(execution_id)

        # 设置为活跃执行
        self._active_executions[session_id] = execution_id
        self._workflow_execution_index[context.workflow_id] = execution_id

        logger.info(
            f"[BranchManager] 创建分支执行: {execution_id} "
            f"(type={branch.branch_type.value}, workflow={workflow_type.value})"
        )

        return execution

    def get_execution(self, execution_id: str) -> Optional[BranchExecution]:
        """
        获取执行记录

        Args:
            execution_id: 执行 ID 或 Workflow ID

        Returns:
            BranchExecution: 执行记录
        """
        execution = self._executions.get(execution_id)
        if execution:
            return execution
        mapped_execution_id = self._workflow_execution_index.get(execution_id)
        if mapped_execution_id:
            return self._executions.get(mapped_execution_id)
        return None

    def bind_workflow(self, workflow_id: str, execution_id: str) -> bool:
        """
        将逻辑 workflow_id 绑定到 BranchExecution。

        Stage 5 的 Interrupt/Checkpoint/Resume 管理器以 workflow_id 聚合状态；
        BranchManager 仍以 execution_id 管理分支执行。该索引让两套 ID 可以稳定协作。
        """
        execution = self._executions.get(execution_id)
        if not execution:
            return False
        execution.context.workflow_id = workflow_id
        self._workflow_execution_index[workflow_id] = execution_id
        return True

    def get_active_execution(self, session_id: str) -> Optional[BranchExecution]:
        """
        获取活跃执行

        Args:
            session_id: 会话 ID

        Returns:
            BranchExecution: 活跃执行记录
        """
        execution_id = self._active_executions.get(session_id)
        if execution_id:
            return self._executions.get(execution_id)
        return None

    def start_execution(self, execution_id: str) -> bool:
        """
        启动执行

        Args:
            execution_id: 执行 ID

        Returns:
            是否成功
        """
        execution = self.get_execution(execution_id)
        if not execution:
            return False

        execution.context.status = WorkflowStatus.RUNNING
        execution.started_at = datetime.now()

        logger.info(f"[BranchManager] 启动执行: {execution_id}")
        return True

    def update_execution_state(
        self,
        execution_id: str,
        current_node: str,
        status: Optional[WorkflowStatus] = None,
        **state_updates,
    ) -> bool:
        """
        更新执行状态

        Args:
            execution_id: 执行 ID
            current_node: 当前节点
            status: 状态
            **state_updates: 其他状态更新

        Returns:
            是否成功
        """
        execution = self.get_execution(execution_id)
        if not execution:
            return False

        # 更新当前节点
        execution.context.current_node = current_node
        if current_node not in execution.context.visited_nodes:
            execution.context.visited_nodes.append(current_node)

        # 更新状态
        if status:
            execution.context.status = status

        # 更新其他字段
        if "collected_slots" in state_updates:
            execution.context.collected_slots.update(state_updates["collected_slots"])
        if "tool_results" in state_updates:
            execution.context.tool_results.update(state_updates["tool_results"])
        if "rag_context" in state_updates:
            execution.context.rag_context = state_updates["rag_context"]
        if "error" in state_updates:
            execution.context.error = state_updates["error"]
            execution.error = state_updates["error"]

        execution.context.updated_at = datetime.now()

        logger.debug(
            f"[BranchManager] 更新执行状态: {execution_id} "
            f"(node={current_node}, status={execution.context.status.value})"
        )

        return True

    def complete_execution(self, execution_id: str, error: Optional[str] = None) -> bool:
        """
        完成执行

        Args:
            execution_id: 执行 ID
            error: 错误信息

        Returns:
            是否成功
        """
        execution = self.get_execution(execution_id)
        if not execution:
            return False

        execution.context.status = WorkflowStatus.FAILED if error else WorkflowStatus.COMPLETED
        execution.context.completed_at = datetime.now()
        execution.completed_at = datetime.now()
        if error:
            execution.error = error
            execution.context.error = error

        logger.info(
            f"[BranchManager] 完成执行: {execution_id} "
            f"(status={execution.context.status.value})"
        )

        return True

    def pause_execution(self, execution_id: str) -> bool:
        """
        暂停执行

        Args:
            execution_id: 执行 ID

        Returns:
            是否成功
        """
        execution = self.get_execution(execution_id)
        if not execution:
            return False

        execution.context.status = WorkflowStatus.PAUSED
        execution.context.updated_at = datetime.now()

        logger.info(f"[BranchManager] 暂停执行: {execution_id}")
        return True

    def resume_execution(self, execution_id: str) -> bool:
        """
        恢复执行

        Args:
            execution_id: 执行 ID

        Returns:
            是否成功
        """
        execution = self.get_execution(execution_id)
        if not execution:
            return False

        if execution.context.status != WorkflowStatus.PAUSED:
            logger.warning(f"[BranchManager] 执行 {execution_id} 未暂停，无法恢复")
            return False

        execution.context.status = WorkflowStatus.RUNNING
        execution.context.updated_at = datetime.now()

        logger.info(f"[BranchManager] 恢复执行: {execution_id}")
        return True

    def switch_branch(
        self,
        execution_id: str,
        new_branch: WorkflowBranch,
    ) -> Optional[BranchExecution]:
        """
        切换分支

        创建新的子分支执行。

        Args:
            execution_id: 当前执行 ID
            new_branch: 新分支定义

        Returns:
            BranchExecution: 新分支执行记录
        """
        current_execution = self.get_execution(execution_id)
        if not current_execution:
            return None

        # 创建子分支
        new_execution_id = self._generate_execution_id()
        context = WorkflowContext(
            workflow_id=new_execution_id,
            workflow_type=current_execution.context.workflow_type,
            status=WorkflowStatus.RUNNING,
            current_branch=new_branch.branch_id,
            current_node="START",
            collected_slots=dict(current_execution.context.collected_slots),  # 继承 Slots
        )

        new_execution = BranchExecution(
            execution_id=new_execution_id,
            branch=new_branch,
            context=context,
            parent_execution=execution_id,
        )

        # 存储执行记录
        self._executions[new_execution_id] = new_execution
        self._workflow_execution_index[context.workflow_id] = new_execution_id
        current_execution.child_executions.append(new_execution_id)

        logger.info(
            f"[BranchManager] 切换分支: {execution_id} -> {new_execution_id} "
            f"(branch={new_branch.branch_name})"
        )

        return new_execution

    def get_execution_tree(self, execution_id: str) -> dict:
        """
        获取执行树

        返回执行及其所有子执行的树形结构。

        Args:
            execution_id: 执行 ID

        Returns:
            执行树
        """
        execution = self.get_execution(execution_id)
        if not execution:
            return {}

        tree = execution.to_dict()
        tree["children"] = [
            self.get_execution_tree(child_id)
            for child_id in execution.child_executions
        ]

        return tree

    def get_stats(self) -> dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        total_executions = len(self._executions)
        active_executions = len([e for e in self._executions.values() if e.is_active()])
        completed_executions = len([e for e in self._executions.values() if e.is_completed()])
        failed_executions = len([e for e in self._executions.values() if e.is_failed()])

        # 按分支类型统计
        branch_type_counts = {}
        for execution in self._executions.values():
            branch_type = execution.branch.branch_type.value
            branch_type_counts[branch_type] = branch_type_counts.get(branch_type, 0) + 1

        return {
            "total_executions": total_executions,
            "active_executions": active_executions,
            "completed_executions": completed_executions,
            "failed_executions": failed_executions,
            "branch_type_distribution": branch_type_counts,
        }

    def _generate_execution_id(self) -> str:
        """生成执行 ID"""
        return f"exec_{uuid.uuid4().hex[:12]}"


# 全局单例
branch_manager = BranchManager()
