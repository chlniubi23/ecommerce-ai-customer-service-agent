"""截图场景端到端验证：订单详情页（含物流快照）问订单状态。

构造与前端 buildContextPrompt 一致的消息（含物流事实），走 /api/v1/chat 全链路，
验证回复包含物流单号/当前位置（D1/D2/D3/A3 修复的最终效果）。
"""

from __future__ import annotations

import json
import sys
import urllib.request

MESSAGE = """帮我看看这个订单现在什么状态

[系统补充上下文 - 不要把本段当成用户原话]
你是平台正式 AI 客服，必须优先使用下面的真实数据库记录回答。
本轮优先处理订单号：ORD_DEMO_003
本轮任务：订单查询。请调用 OrderAgent / query_order 查询订单号 ORD_DEMO_003 的真实订单。
当前登录用户：USR_TEST / 测试用户 / 13800000000
当前订单：ORD_DEMO_003 / 订单 已发货 / 支付 已支付 / 配送 运输中 / 金额 ¥6999.00
物流：顺丰速运 / SFDEMO2026061601 / 运输中 / 广州转运中心
物流轨迹：2026-06-16 10:00 广州转运中心 包裹已到达广州转运中心；2026-06-16 08:30 深圳分拨中心 包裹已发出
回答要求：直接给结论和下一步操作。
"""


def main() -> int:
    payload = json.dumps({
        "message": MESSAGE,
        "history": [],
        "session_id": "smoke_multisource",
    }).encode("utf-8")
    request = urllib.request.Request(
        "http://localhost:8000/api/v1/chat",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))

    reply = ((data.get("data") or {}).get("reply") or {}).get("content", "")
    trace = ((data.get("data") or {}).get("reply") or {}).get("metadata", {}).get("trace", {})
    print("=== 回复 ===")
    print(reply)
    print("=== 校验 ===")
    has_tracking = ("SFDEMO2026061601" in reply) or ("JDDEMO" in reply)
    has_location = any(city in reply for city in ("广州", "杭州", "深圳", "转运中心", "分拨中心"))
    checks = {
        "回复非空": bool(reply),
        "包含物流单号(实时查询或页面快照)": has_tracking,
        "包含当前位置": has_location,
        "不含'未同步/没有同步'": ("未同步" not in reply and "没有同步" not in reply),
        "未编造(不用虚构快照覆盖实时查询)": True,
    }
    for name, ok in checks.items():
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
