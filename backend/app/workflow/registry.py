"""
Workflow Registry - 工作流注册中心

职责：
- 工作流注册与发现
- 工作流元数据管理
- 工作流版本管理
- 工作流生命周期管理

设计原则：
- Single Source of Truth：所有工作流统一注册
- Decoupling：Condition Engine 只依赖 Registry，不依赖具体 Workflow
- Extensibility：新增工作流只需注册，无需修改核心逻辑
- Metadata-driven：工作流通过元数据声明能力
"""

import logging
from typing import Optional
from app.workflow.models import (
    WorkflowDefinition,
    WorkflowMetadata,
    WorkflowType,
)

logger = logging.getLogger(__name__)


class WorkflowRegistry:
    """
    工作流注册中心

    管理所有工作流的注册、查找和元数据。
    """

    def __init__(self):
        self._workflows: dict[WorkflowType, WorkflowDefinition] = {}
        self._initialized = False

    def register(self, definition: WorkflowDefinition) -> None:
        """
        注册工作流

        Args:
            definition: 工作流定义
        """
        workflow_type = definition.metadata.workflow_type

        if workflow_type in self._workflows:
            existing_version = self._workflows[workflow_type].metadata.version
            new_version = definition.metadata.version
            logger.warning(
                f"工作流 {workflow_type.value} 已注册（版本 {existing_version}），"
                f"将被新版本 {new_version} 覆盖"
            )

        self._workflows[workflow_type] = definition
        logger.info(
            f"工作流注册成功: {definition.metadata.name} "
            f"(type={workflow_type.value}, version={definition.metadata.version})"
        )

    def get(self, workflow_type: WorkflowType) -> Optional[WorkflowDefinition]:
        """
        获取工作流定义

        Args:
            workflow_type: 工作流类型

        Returns:
            工作流定义，如果未注册则返回 None
        """
        return self._workflows.get(workflow_type)

    def get_metadata(self, workflow_type: WorkflowType) -> Optional[WorkflowMetadata]:
        """
        获取工作流元数据

        Args:
            workflow_type: 工作流类型

        Returns:
            工作流元数据，如果未注册则返回 None
        """
        definition = self.get(workflow_type)
        return definition.metadata if definition else None

    def list_all(self) -> list[WorkflowType]:
        """
        列出所有已注册的工作流类型

        Returns:
            工作流类型列表
        """
        return list(self._workflows.keys())

    def find_by_intent(self, intent: str) -> Optional[WorkflowType]:
        """
        根据意图查找对应的工作流类型

        Args:
            intent: 意图字符串

        Returns:
            工作流类型，如果未找到则返回 None
        """
        # Intent 到 Workflow 的映射
        intent_to_workflow = {
            "refund": WorkflowType.REFUND,
            "logistics_query": WorkflowType.LOGISTICS,
            "product_query": WorkflowType.PRODUCT,
            "order_query": WorkflowType.ORDER,
            "coupon_query": WorkflowType.COUPON,
            "ticket": WorkflowType.TICKET,
            "human_transfer": WorkflowType.HUMAN_TRANSFER,
            "complaint": WorkflowType.COMPLAINT,
            "general": WorkflowType.GENERAL,
        }

        return intent_to_workflow.get(intent)

    def find_by_priority(self) -> list[WorkflowType]:
        """
        按优先级排序返回工作流类型列表

        Returns:
            按优先级从高到低排序的工作流类型列表
        """
        sorted_workflows = sorted(
            self._workflows.items(),
            key=lambda x: x[1].metadata.priority,
            reverse=True,
        )
        return [wf_type for wf_type, _ in sorted_workflows]

    def is_registered(self, workflow_type: WorkflowType) -> bool:
        """
        检查工作流是否已注册

        Args:
            workflow_type: 工作流类型

        Returns:
            是否已注册
        """
        return workflow_type in self._workflows

    def initialize(self) -> None:
        """
        初始化注册中心

        注册所有预定义的工作流。
        """
        if self._initialized:
            logger.warning("WorkflowRegistry 已初始化，跳过重复初始化")
            return

        logger.info("开始初始化 WorkflowRegistry...")

        # 注册退款工作流
        self.register(WorkflowDefinition(
            metadata=WorkflowMetadata(
                workflow_type=WorkflowType.REFUND,
                name="Refund Workflow",
                description="退款申请与处理流程",
                requires_slots=["order_id", "refund_reason"],
                requires_tools=["refund_query"],
                priority=10,
                tags=["transaction", "customer_service"],
            )
        ))

        # 注册物流查询工作流
        self.register(WorkflowDefinition(
            metadata=WorkflowMetadata(
                workflow_type=WorkflowType.LOGISTICS,
                name="Logistics Workflow",
                description="物流信息查询流程",
                requires_slots=["order_id"],
                requires_tools=["logistics_query"],
                priority=8,
                tags=["query", "logistics"],
            )
        ))

        # 注册商品查询工作流
        self.register(WorkflowDefinition(
            metadata=WorkflowMetadata(
                workflow_type=WorkflowType.PRODUCT,
                name="Product Workflow",
                description="商品信息查询流程",
                requires_slots=["product_id"],
                requires_tools=["product_query"],
                priority=6,
                tags=["query", "product"],
            )
        ))

        # 注册订单查询工作流
        self.register(WorkflowDefinition(
            metadata=WorkflowMetadata(
                workflow_type=WorkflowType.ORDER,
                name="Order Workflow",
                description="订单信息查询流程",
                requires_slots=["order_id"],
                requires_tools=["order_query"],
                priority=7,
                tags=["query", "order"],
            )
        ))

        # 注册优惠券工作流
        self.register(WorkflowDefinition(
            metadata=WorkflowMetadata(
                workflow_type=WorkflowType.COUPON,
                name="Coupon Workflow",
                description="优惠券查询与领取流程",
                requires_tools=["coupon_query"],
                priority=5,
                tags=["query", "promotion"],
            )
        ))

        # 注册工单创建工作流
        self.register(WorkflowDefinition(
            metadata=WorkflowMetadata(
                workflow_type=WorkflowType.TICKET,
                name="Ticket Workflow",
                description="工单创建与跟踪流程",
                requires_slots=["issue_description"],
                requires_tools=["create_ticket"],
                priority=9,
                tags=["customer_service", "issue"],
            )
        ))

        # 注册人工客服转接工作流
        self.register(WorkflowDefinition(
            metadata=WorkflowMetadata(
                workflow_type=WorkflowType.HUMAN_TRANSFER,
                name="Human Transfer Workflow",
                description="人工客服转接流程",
                requires_tools=["transfer_human"],
                priority=15,
                tags=["escalation", "human"],
            )
        ))

        # 注册投诉工作流
        self.register(WorkflowDefinition(
            metadata=WorkflowMetadata(
                workflow_type=WorkflowType.COMPLAINT,
                name="Complaint Workflow",
                description="客户投诉处理流程",
                requires_slots=["complaint_reason"],
                requires_tools=["create_ticket"],
                priority=12,
                tags=["customer_service", "complaint"],
            )
        ))

        # 注册通用工作流
        self.register(WorkflowDefinition(
            metadata=WorkflowMetadata(
                workflow_type=WorkflowType.GENERAL,
                name="General Workflow",
                description="通用闲聊与兜底流程",
                requires_rag=True,
                priority=1,
                tags=["general", "fallback"],
            )
        ))

        self._initialized = True
        logger.info(
            f"WorkflowRegistry 初始化完成，已注册 {len(self._workflows)} 个工作流: "
            f"{[wf.value for wf in self.list_all()]}"
        )

    def get_stats(self) -> dict:
        """
        获取注册中心统计信息

        Returns:
            统计信息字典
        """
        return {
            "total_workflows": len(self._workflows),
            "workflows": [
                {
                    "type": wf_type.value,
                    "name": definition.metadata.name,
                    "version": definition.metadata.version,
                    "priority": definition.metadata.priority,
                    "requires_slots": definition.metadata.requires_slots,
                    "requires_tools": definition.metadata.requires_tools,
                    "requires_rag": definition.metadata.requires_rag,
                }
                for wf_type, definition in self._workflows.items()
            ],
        }


# 全局单例
workflow_registry = WorkflowRegistry()
