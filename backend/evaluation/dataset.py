"""路由层评测标注数据集。

字段说明：
- kind:      评测点。intent=意图分类（走 classify_intent 完整入口）；
             gate=投诉确认闸门（resolve_complaint_gate，has_pending=True）；
             confirm/deny=确认/拒绝词判定；create=明确创建投诉判定；
             followup=跟进已有投诉判定；coordinate=多域协调触发判定。
- layer:     rule=规则层必须单独命中（离线评测时屏蔽 LLM，规则失手即判失败）；
             llm=必须依赖 LLM 分类（离线模式跳过，--live 模式用真实 API）。
- expected:  intent 填 IntentType 的值；gate 填 create/cancel/ask_again；
             其余填 True/False。

标注依据：classifier.py 的规则表（业务指令通道 / 知识库规则）、
complaint_intent.py 的判定函数、coordinator.py 的 DOMAIN_PATTERNS。
"""

# 借助上下文里不存在的常量会显得突兀，这里集中声明用到的意图值，便于审阅
I = {
    "logistics": "logistics_query",
    "order": "order_query",
    "refund": "refund",
    "coupon": "coupon_query",
    "product": "product_query",
    "knowledge": "knowledge_query",
    "ticket": "ticket",
    "human": "human_transfer",
    "general": "general",
}

EVAL_CASES: list[dict] = [
    # ===== 意图分类 · 规则层（离线必须全对）=====
    # -- 前端注入的"本轮任务"可信指令通道 --
    {"kind": "intent", "layer": "rule", "text": "本轮任务：物流查询 订单ORD1001到哪里了", "expected": I["logistics"],
     "note": "前端系统上下文注入的任务指令，必须走完整文本匹配"},
    {"kind": "intent", "layer": "rule", "text": "本轮任务：订单查询", "expected": I["order"]},
    {"kind": "intent", "layer": "rule", "text": "本轮任务：退款/售后", "expected": I["refund"]},
    {"kind": "intent", "layer": "rule", "text": "本轮任务：转人工", "expected": I["human"]},
    {"kind": "intent", "layer": "rule", "text": "logisticsagent 帮我查快递", "expected": I["logistics"]},
    {"kind": "intent", "layer": "rule", "text": "query_order ORD_2002", "expected": I["order"]},
    {"kind": "intent", "layer": "rule", "text": "refund_apply 订单ORD3003", "expected": I["refund"]},
    {"kind": "intent", "layer": "rule", "text": "humantransferagent", "expected": I["human"]},
    # -- 投诉：明确创建 / 跟进已有（历史 bug 高发区）--
    {"kind": "intent", "layer": "rule", "text": "我要投诉订单ORD_DEMO_003，外包装破损", "expected": I["ticket"]},
    {"kind": "intent", "layer": "rule", "text": "帮我创建一个投诉", "expected": I["ticket"]},
    {"kind": "intent", "layer": "rule", "text": "工单CMP_DEMO_D01处理到哪了，是否需要升级", "expected": I["ticket"],
     "note": "带编号+投诉名词+跟进动作 → 跟进（只读），不是新建"},
    {"kind": "intent", "layer": "rule", "text": "这个订单我已经投诉了，我想知道最新处理进展", "expected": I["ticket"],
     "note": "过去完成语气+跟进 → 跟进而非新建"},
    # -- 优惠券 / 推荐：路由层复用 Flow 提示词做单一事实源 --
    {"kind": "intent", "layer": "rule", "text": "我现在有哪些优惠券", "expected": I["coupon"]},
    {"kind": "intent", "layer": "rule", "text": "我的优惠券有哪些", "expected": I["coupon"]},
    {"kind": "intent", "layer": "rule", "text": "有哪些券可以用", "expected": I["coupon"]},
    {"kind": "intent", "layer": "rule", "text": "根据我买过的东西推荐", "expected": I["product"]},
    {"kind": "intent", "layer": "rule", "text": "有什么值得入手的", "expected": I["product"]},
    {"kind": "intent", "layer": "rule", "text": "给我推荐几款笔记本", "expected": I["product"]},
    # -- 知识库规则（域词+疑问词交集 / 关键词表）--
    {"kind": "intent", "layer": "rule", "text": "退款政策是什么", "expected": I["knowledge"],
     "note": "干扰样本：有'退款'但问的是政策，不是要发起退款"},
    {"kind": "intent", "layer": "rule", "text": "七天无理由退货规则", "expected": I["knowledge"]},
    {"kind": "intent", "layer": "rule", "text": "优惠券怎么使用", "expected": I["knowledge"],
     "note": "通用规则问题进知识库；'我有哪些券'才进 CouponFlow"},
    {"kind": "intent", "layer": "rule", "text": "会员等级怎么划分的", "expected": I["knowledge"]},
    {"kind": "intent", "layer": "rule", "text": "ThinkBook 参数介绍", "expected": I["knowledge"]},
    {"kind": "intent", "layer": "rule", "text": "macbook air 支持扩展内存吗", "expected": I["knowledge"]},
    {"kind": "intent", "layer": "rule", "text": "投诉升级规则是什么", "expected": I["knowledge"],
     "note": "干扰样本：不含创建动词，应进知识库而非建投诉工单"},

    # ===== 意图分类 · LLM 层（离线跳过，--live 用真实 API）=====
    {"kind": "intent", "layer": "llm", "text": "我要退款", "expected": I["refund"]},
    {"kind": "intent", "layer": "llm", "text": "东西坏了想退钱", "expected": I["refund"]},
    {"kind": "intent", "layer": "llm", "text": "帮我查下我的订单", "expected": I["order"]},
    {"kind": "intent", "layer": "llm", "text": "快递到哪了", "expected": I["logistics"]},
    {"kind": "intent", "layer": "llm", "text": "我的快递怎么还没到", "expected": I["logistics"]},
    {"kind": "intent", "layer": "llm", "text": "帮我转接人工客服", "expected": I["human"]},
    {"kind": "intent", "layer": "llm", "text": "查询我的投诉记录", "expected": I["ticket"],
     "note": "不带编号的投诉查询，规则层不命中，靠 LLM 分类"},
    {"kind": "intent", "layer": "llm", "text": "你好呀", "expected": I["general"]},

    # ===== 投诉确认闸门（has_pending=True，纯函数，离线运行）=====
    {"kind": "gate", "text": "确认提交投诉", "expected": "create"},
    {"kind": "gate", "text": "确认", "expected": "create"},
    {"kind": "gate", "text": "确定", "expected": "create"},
    {"kind": "gate", "text": "同意", "expected": "create"},
    {"kind": "gate", "text": "没问题", "expected": "create"},
    {"kind": "gate", "text": "就这么办", "expected": "create"},
    {"kind": "gate", "text": "不用了", "expected": "cancel"},
    {"kind": "gate", "text": "取消，不提交", "expected": "cancel"},
    {"kind": "gate", "text": "先不要", "expected": "cancel"},
    {"kind": "gate", "text": "算了", "expected": "cancel"},
    # 弱肯定词收紧后的关键回归：用户转题不再误触发创建
    {"kind": "gate", "text": "好的", "expected": "ask_again", "note": "弱肯定词不得触发写操作"},
    {"kind": "gate", "text": "可以", "expected": "ask_again", "note": "弱肯定词不得触发写操作"},
    {"kind": "gate", "text": "嗯", "expected": "ask_again", "note": "弱肯定词不得触发写操作"},
    {"kind": "gate", "text": "麻烦了", "expected": "ask_again"},
    {"kind": "gate", "text": "帮我查下物流", "expected": "ask_again", "note": "等待确认时转题 → 不明确"},
    {"kind": "gate", "text": "这个订单到底怎么回事", "expected": "ask_again"},

    # ===== 确认/拒绝词判定 =====
    {"kind": "confirm", "text": "好的就这样", "expected": False, "note": "弱肯定词收紧"},
    {"kind": "confirm", "text": "是的，提交吧", "expected": True, "note": "含'提交'强信号仍确认"},
    {"kind": "confirm", "text": "帮我查物流", "expected": False},
    {"kind": "confirm", "text": "行", "expected": False},
    {"kind": "deny", "text": "不用了", "expected": True},
    {"kind": "deny", "text": "别", "expected": True},
    {"kind": "deny", "text": "确认提交", "expected": False, "note": "肯定词不是拒绝"},

    # ===== 明确创建投诉判定 =====
    {"kind": "create", "text": "我要投诉这个订单", "expected": True},
    {"kind": "create", "text": "我想提交投诉", "expected": True},
    {"kind": "create", "text": "总结当前订单、物流、退款和投诉情况", "expected": False,
     "note": "只读总结类绝不建投诉（历史 bug）"},
    {"kind": "create", "text": "投诉情况怎么样了", "expected": False},
    {"kind": "create", "text": "我投诉过了，帮我看看进展", "expected": False},

    # ===== 跟进已有投诉判定 =====
    {"kind": "followup", "text": "工单CMP_DEMO_D01的进度", "expected": True},
    {"kind": "followup", "text": "之前投诉过这个订单现在处理得怎么样", "expected": True},
    {"kind": "followup", "text": "我要投诉", "expected": False},
    {"kind": "followup", "text": "订单ORD1001的物流到哪了", "expected": False},

    # ===== 多域协调触发 =====
    {"kind": "coordinate", "text": "帮我查下订单ORD1的物流，再看看我的优惠券", "expected": True,
     "note": "logistics+order+coupon 独立多域 → 协作"},
    {"kind": "coordinate", "text": "查下订单顺便推荐个商品", "expected": True},
    {"kind": "coordinate", "text": "我要退款，帮我看下这个订单的状态", "expected": False,
     "note": "订单只是退款的依赖域，不协作，走退款确认闸门"},
    {"kind": "coordinate", "text": "我要投诉并且申请退款", "expected": True,
     "note": "双写域互不为依赖 → 进协调；协调器对 refund/complaint 只做只读查询与引导，绝不静默写库（见 test_coordinator_safety）"},
    {"kind": "coordinate", "text": "查下物流信息", "expected": False, "note": "单域不协作"},
    {"kind": "coordinate", "text": "你好", "expected": False},
]
