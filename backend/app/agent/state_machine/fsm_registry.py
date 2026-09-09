"""
FSM Registry - 状态机注册中心

职责：
- 管理所有业务 FSM 实例
- 按 flow_name 查找对应 FSM
- 应用启动时注册所有 FSM

使用方式：
    fsm = fsm_registry.get("refund")
    result = fsm.process(current_state, slots, user_input)
"""

import logging
from app.agent.state_machine.base_fsm import BaseFSM

logger = logging.getLogger(__name__)

# 全局 FSM 注册表
_fsm_store: dict[str, BaseFSM] = {}


class FSMRegistry:
    """FSM 注册中心"""

    def register(self, fsm: BaseFSM) -> None:
        """注册一个 FSM 实例"""
        _fsm_store[fsm.flow_name] = fsm
        logger.info(f"[FSMRegistry] 注册 FSM: {fsm.flow_name}")

    def get(self, flow_name: str) -> BaseFSM | None:
        """根据 flow_name 获取 FSM"""
        return _fsm_store.get(flow_name)

    def has(self, flow_name: str) -> bool:
        """是否有对应 FSM"""
        return flow_name in _fsm_store

    def list_registered(self) -> list[str]:
        """列出所有已注册 FSM"""
        return list(_fsm_store.keys())


# 全局单例
fsm_registry = FSMRegistry()


def init_fsm() -> None:
    """初始化注册所有 FSM（应用启动时调用）"""
    from app.agent.state_machine.refund_fsm import RefundFSM
    from app.agent.state_machine.logistics_fsm import LogisticsFSM

    fsm_registry.register(RefundFSM())
    fsm_registry.register(LogisticsFSM())

    logger.info(f"[FSMRegistry] 注册完成: {fsm_registry.list_registered()}")
