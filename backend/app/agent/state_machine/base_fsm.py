"""
BaseFSM - 有限状态机抽象基类

职责：
- 定义 FSM 统一接口
- 管理状态转移规则
- 提供槽位定义和追问生成

设计理念：
- 每个业务流程（退款、物流）对应一个 FSM 子类
- FSM 不做 LLM 调用，只做状态管理
- 状态转移由 SlotManager 驱动
- FSM 是纯逻辑层，无副作用

架构位置：
- agent/state_machine/ 层
- 被 flows/ 调用，配合 SlotManager 使用

扩展规划：
- Phase 5: 支持条件分支状态转移
- Phase 6: 支持并行状态（AND-state）
- Phase 7: 可视化状态图导出
"""

import logging
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SlotDefinition:
    """
    槽位定义

    描述一个 Flow 需要收集的参数。

    Attributes:
        name: 槽位名称（如 order_id）
        description: 中文描述（用于生成追问）
        required: 是否必填
        prompt: 追问用户时的提示语
        state: 等待此槽位时 FSM 应处于的状态
    """
    name: str
    description: str
    required: bool = True
    prompt: str = ""
    state: str = ""


@dataclass
class FSMResult:
    """
    FSM 处理结果

    描述 FSM 在处理一次用户输入后的状态。

    Attributes:
        new_state: 转移后的新状态
        waiting_for: 下一步需要等待的 Slot（空 = 不等待）
        prompt: 需要向用户发送的追问（空 = 不追问）
        ready: 所有必填 Slot 已就绪，可以执行工具
        slots: 当前已收集的所有 Slot
    """
    new_state: str = ""
    waiting_for: str = ""
    prompt: str = ""
    ready: bool = False
    slots: dict[str, Any] = field(default_factory=dict)


class BaseFSM(ABC):
    """
    有限状态机抽象基类

    子类必须实现：
    - flow_name: 关联的 Flow 名称
    - states: 状态枚举
    - slot_definitions: 需要收集的 Slot 定义
    - initial_state: 初始状态
    - terminal_state: 终止状态

    使用方式：
        fsm = RefundFSM()
        result = fsm.process(current_state="START", slots={}, user_input="123456")
        # result.new_state = "WAIT_REFUND_REASON"
        # result.waiting_for = "refund_reason"
        # result.prompt = "请问退款原因是什么？"
    """

    @property
    @abstractmethod
    def flow_name(self) -> str:
        """关联的 Flow 名称（如 refund, logistics_query）"""
        ...

    @property
    @abstractmethod
    def slot_definitions(self) -> list[SlotDefinition]:
        """需要收集的 Slot 定义列表（按收集顺序排列）"""
        ...

    @property
    @abstractmethod
    def initial_state(self) -> str:
        """初始状态"""
        ...

    @property
    @abstractmethod
    def terminal_state(self) -> str:
        """终止状态"""
        ...

    def process(
        self,
        current_state: str,
        slots: dict[str, Any],
        user_input: str,
    ) -> FSMResult:
        """
        处理一次用户输入，推进状态机

        逻辑：
        1. 如果当前有 waiting_for，尝试用 user_input 填充对应 slot
        2. 检查所有必填 slot 是否已就绪
        3. 如果缺失，转移到等待该 slot 的状态
        4. 如果全部就绪，转移到 PROCESSING 状态

        Args:
            current_state: 当前 FSM 状态
            slots: 当前已收集的 slots
            user_input: 用户本轮输入

        Returns:
            FSMResult: 包含新状态、等待信息、追问提示
        """
        # 找到当前等待的 slot 并填充
        waiting_slot = self._find_waiting_slot(current_state)
        if waiting_slot and user_input.strip():
            # 使用宽松提取（正在等待时允许自由文本）
            extractor = getattr(self, '_extract_slot_value_waiting', self._extract_slot_value)
            extracted = extractor(waiting_slot.name, user_input)
            if extracted is not None:
                slots[waiting_slot.name] = extracted
                logger.info(f"[{self.flow_name}FSM] 填充 {waiting_slot.name} = {extracted}")

        # 检查下一个缺失的必填 slot
        missing = self._find_next_missing(slots)

        if missing is None:
            # 全部就绪 → PROCESSING
            return FSMResult(
                new_state="PROCESSING",
                ready=True,
                slots=slots,
            )
        else:
            # 还有缺失 → 转移到等待状态
            return FSMResult(
                new_state=missing.state,
                waiting_for=missing.name,
                prompt=missing.prompt,
                ready=False,
                slots=slots,
            )

    def get_initial_result(self, slots: dict[str, Any], user_input: str) -> FSMResult:
        """
        首次进入流程时的处理

        先尝试从首条用户输入中提取尽量多的 slot，
        然后检查缺失。

        Args:
            slots: 初始 slots（通常为空）
            user_input: 用户首条输入

        Returns:
            FSMResult
        """
        # 尝试从首条输入中提取所有 slot
        for slot_def in self.slot_definitions:
            if slot_def.name not in slots:
                extracted = self._extract_slot_value(slot_def.name, user_input)
                if extracted is not None:
                    slots[slot_def.name] = extracted

        # 检查缺失
        missing = self._find_next_missing(slots)
        if missing is None:
            return FSMResult(
                new_state="PROCESSING",
                ready=True,
                slots=slots,
            )
        else:
            return FSMResult(
                new_state=missing.state,
                waiting_for=missing.name,
                prompt=missing.prompt,
                ready=False,
                slots=slots,
            )

    def _find_waiting_slot(self, current_state: str) -> SlotDefinition | None:
        """根据当前状态找到正在等待的 Slot 定义"""
        for slot_def in self.slot_definitions:
            if slot_def.state == current_state:
                return slot_def
        return None

    def _find_next_missing(self, slots: dict[str, Any]) -> SlotDefinition | None:
        """找到下一个缺失的必填 Slot"""
        for slot_def in self.slot_definitions:
            if slot_def.required and slot_def.name not in slots:
                return slot_def
        return None

    @abstractmethod
    def _extract_slot_value(self, slot_name: str, user_input: str) -> Any | None:
        """
        从用户输入中提取指定 Slot 的值

        子类实现具体的提取逻辑（正则/关键词/LLM）。

        Args:
            slot_name: 要提取的 Slot 名称
            user_input: 用户输入

        Returns:
            提取到的值，None 表示未提取到
        """
        ...
