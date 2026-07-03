"""主动事件发射的安全封装。

工具在成功执行写动作后调用 emit_proactive_event 落一条主动事件。
封装的意义：主动提醒是"锦上添花"，任何失败（无 user_id、DB 抖动）都不能
影响主流程（退款/投诉/转人工本身已经成功），因此这里吞掉所有异常并记日志。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def emit_proactive_event(
    user_id: str | None,
    event_type: str,
    severity: str,
    title: str,
    description: str,
    action_prompt: str,
    dedup_key: str,
    order_id: str | None = None,
    related_id: str | None = None,
) -> dict[str, Any] | None:
    """落一条主动事件；失败时返回 None，绝不向上抛出（不拖累主流程）。"""
    if not user_id:
        # 没有用户身份时无法归属事件，静默跳过（例如匿名/系统内部调用）。
        return None
    try:
        from app.database.repositories import ProactiveEventRepository

        return ProactiveEventRepository().emit(
            user_id=user_id,
            event_type=event_type,
            severity=severity,
            title=title,
            description=description,
            action_prompt=action_prompt,
            dedup_key=dedup_key,
            order_id=order_id,
            related_id=related_id,
        )
    except Exception as exc:  # noqa: BLE001 - 主动提醒失败不能影响主流程
        logger.warning("[proactive] emit failed (%s): %s", dedup_key, exc)
        return None
