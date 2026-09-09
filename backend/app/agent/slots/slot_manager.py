"""
SlotManager - 槽位填充管理器

职责：
- 协调 FSM + Session 完成槽位收集
- 判断是否需要追问
- 生成追问消息
- 所有 Slot 就绪后标记 ready

使用方式：
    result = slot_manager.process(session, user_input)
    if result.ready:
        # 执行工具
    else:
        # 返回 result.prompt 追问用户

设计理念：
- SlotManager 不直接操作 FSM，而是通过 FSMRegistry 查找
- 不同 Flow 的 Slot 逻辑完全解耦
- 追问文案定义在 FSM 的 SlotDefinition 中
"""

import logging
from dataclasses import dataclass, field
from typing import Any
from app.agent.memory.session import Session
from app.agent.state_machine.base_fsm import FSMResult
from app.agent.state_machine.fsm_registry import fsm_registry

logger = logging.getLogger(__name__)


@dataclass
class SlotFillingResult:
    """
    槽位填充结果

    Attributes:
        ready: 所有必填 Slot 已就绪
        prompt: 追问提示（ready=False 时有值）
        new_state: FSM 新状态
        waiting_for: 当前等待的 Slot
        slots: 已收集的 Slot 值
    """
    ready: bool = False
    prompt: str = ""
    new_state: str = ""
    waiting_for: str = ""
    slots: dict[str, Any] = field(default_factory=dict)


class SlotManager:
    """槽位填充管理器"""

    def process(self, session: Session, user_input: str) -> SlotFillingResult:
        """
        处理一轮用户输入，推进槽位填充

        逻辑：
        1. 根据 session.current_flow 找到对应 FSM
        2. 调用 FSM.process() 提取 Slot + 推进状态
        3. 更新 Session 状态
        4. 返回结果

        Args:
            session: 当前会话
            user_input: 用户输入

        Returns:
            SlotFillingResult
        """
        flow_name = session.current_flow
        fsm = fsm_registry.get(flow_name)

        if fsm is None:
            # 无对应 FSM，直接返回 ready（走原有 Flow 逻辑）
            return SlotFillingResult(ready=True, slots=session.slots)

        # 判断是首次进入还是继续填充
        if session.current_state in ("START", ""):
            # 首次进入：尝试从用户输入中一次性提取所有 Slot
            fsm_result = fsm.get_initial_result(
                slots=dict(session.slots),
                user_input=user_input,
            )
        else:
            # 继续填充：根据当前状态处理
            fsm_result = fsm.process(
                current_state=session.current_state,
                slots=dict(session.slots),
                user_input=user_input,
            )

        # 更新 Session
        session.current_state = fsm_result.new_state
        session.waiting_for = fsm_result.waiting_for
        session.slots = fsm_result.slots

        logger.info(
            f"[SlotManager] flow={flow_name}, "
            f"state={fsm_result.new_state}, "
            f"waiting={fsm_result.waiting_for}, "
            f"ready={fsm_result.ready}, "
            f"slots={fsm_result.slots}"
        )

        return SlotFillingResult(
            ready=fsm_result.ready,
            prompt=fsm_result.prompt,
            new_state=fsm_result.new_state,
            waiting_for=fsm_result.waiting_for,
            slots=fsm_result.slots,
        )


# 全局单例
slot_manager = SlotManager()
