"""
Tool Calling System - 工具调用子系统

Phase 3 核心模块，让 Agent 具备真正的任务执行能力。

架构：
- base_tool.py: 工具抽象基类 + ToolResult
- tool_registry.py: 工具注册中心
- tool_router.py: 工具选择器（Intent → Tool）
- logistics_tool.py: 物流查询工具 (Mock)
- refund_tool.py: 退款工具 (Mock)
- product_tool.py: 商品查询工具 (Mock)
"""
