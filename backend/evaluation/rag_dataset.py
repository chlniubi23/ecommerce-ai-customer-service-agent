"""RAG 检索评测数据集（黄金问题 30 条）。

命题纪律（防自证约束，红线 #2）：
- 所有问题先基于电商客服通用场景独立撰写，再对照 knowledge_base/knowledge/
  的文件名清单标注期望来源（expected_source_hint 用文件名关键词）；
- 禁止从知识文件内容里反抄问题，避免评测虚高失去回归意义。

字段说明：
- question: 评测问题（含书面/口语变体）；
- expected_category: 期望命中的知识类别；
- expected_source_hint: 期望命中文件名包含的关键词（top1/top3 命中判定用）；
- expect_answer: True=知识库应能回答；False=无答案问题（验证不编造兜底）；
- is_colloquial: 是否口语变体（每类至少 1 条）。

构成：10 个类别 × ≥2 条 + 每类 ≥1 条口语变体 + 3 条无答案问题 = 30 条。
"""

from __future__ import annotations

RAG_EVAL_CASES: list[dict] = [
    # ================= refund（退款/售后）4 条 =================
    {
        "question": "七天无理由退货的规则是什么",
        "expected_category": "refund",
        "expected_source_hint": "seven_day_return",
        "expect_answer": True,
        "is_colloquial": False,
    },
    {
        "question": "我买的东西不想要了，还能退吗",
        "expected_category": "refund",
        "expected_source_hint": "no_reason_return_guide",
        "expect_answer": True,
        "is_colloquial": True,
    },
    {
        "question": "退款审核需要多长时间，钱多久能到账",
        "expected_category": "refund",
        "expected_source_hint": "refund_timeline",
        "expect_answer": True,
        "is_colloquial": False,
    },
    # ================= coupon（优惠券）3 条 =================
    {
        "question": "优惠券怎么领取、怎么使用",
        "expected_category": "coupon",
        "expected_source_hint": "coupon_receive",
        "expect_answer": True,
        "is_colloquial": False,
    },
    {
        "question": "券咋领啊，在哪里领",
        "expected_category": "coupon",
        "expected_source_hint": "coupon_receive",
        "expect_answer": True,
        "is_colloquial": True,
    },
    {
        "question": "优惠券过期了还能用吗",
        "expected_category": "coupon",
        "expected_source_hint": "coupon",
        "expect_answer": True,
        "is_colloquial": False,
    },
    # ================= membership（会员）3 条 =================
    {
        "question": "会员等级有哪些，各等级权益是什么",
        "expected_category": "membership",
        "expected_source_hint": "membership_level",
        "expect_answer": True,
        "is_colloquial": False,
    },
    {
        "question": "积分能提现吗，咋用啊",
        "expected_category": "membership",
        "expected_source_hint": "points_usage",
        "expect_answer": True,
        "is_colloquial": True,
    },
    # ================= logistics（物流）3 条 =================
    {
        "question": "物流配送一般多久能到",
        "expected_category": "logistics",
        "expected_source_hint": "logistics_timeline",
        "expect_answer": True,
        "is_colloquial": False,
    },
    {
        "question": "我的快递咋还没到啊",
        "expected_category": "logistics",
        "expected_source_hint": "late_delivery",
        "expect_answer": True,
        "is_colloquial": True,
    },
    {
        "question": "包裹显示外包装破损了怎么办，能赔吗",
        "expected_category": "logistics",
        "expected_source_hint": "compensation",
        "expect_answer": True,
        "is_colloquial": False,
    },
    # ================= complaint（投诉）3 条 =================
    {
        "question": "投诉了没人处理怎么办，会不会升级到主管",
        "expected_category": "complaint",
        "expected_source_hint": "complaint_",
        "expect_answer": True,
        "is_colloquial": False,
    },
    {
        "question": "你们这服务太差了，我要投诉",
        "expected_category": "complaint",
        "expected_source_hint": "escalation",
        "expect_answer": True,
        "is_colloquial": True,
    },
    {
        "question": "投诉处理有时间限制吗，多久给答复",
        "expected_category": "complaint",
        "expected_source_hint": "complaint_",
        "expect_answer": True,
        "is_colloquial": False,
    },
    # ================= product（商品）3 条 =================
    {
        "question": "MacBook Air 的内存支持扩展吗",
        "expected_category": "product",
        "expected_source_hint": "macbook_air",
        "expect_answer": True,
        "is_colloquial": True,
    },
    {
        "question": "iPhone 16 的芯片是什么型号",
        "expected_category": "product",
        "expected_source_hint": "iphone_16",
        "expect_answer": True,
        "is_colloquial": False,
    },
    {
        "question": "ThinkBook 14+ 的屏幕参数怎么样",
        "expected_category": "product",
        "expected_source_hint": "thinkbook_14",
        "expect_answer": True,
        "is_colloquial": False,
    },
    # ================= policy（政策）2 条 =================
    {
        "question": "平台的隐私政策是怎么规定的",
        "expected_category": "policy",
        "expected_source_hint": "privacy_policy",
        "expect_answer": True,
        "is_colloquial": False,
    },
    {
        "question": "用户协议里对账号有啥要求",
        "expected_category": "policy",
        "expected_source_hint": "user_agreement",
        "expect_answer": True,
        "is_colloquial": True,
    },
    # ================= sop（客服 SOP）2 条 =================
    {
        "question": "客服处理退款的标准流程是什么",
        "expected_category": "sop",
        "expected_source_hint": "refund_sop",
        "expect_answer": True,
        "is_colloquial": False,
    },
    {
        "question": "啥情况下工单要往上转给主管处理",
        "expected_category": "sop",
        "expected_source_hint": "escalation",
        "expect_answer": True,
        "is_colloquial": True,
    },
    # ================= operation（运营）2 条 =================
    {
        "question": "现在平台有什么促销活动，规则是什么",
        "expected_category": "operation",
        "expected_source_hint": "promotion",
        "expect_answer": True,
        "is_colloquial": False,
    },
    {
        "question": "现在搞啥活动，有啥优惠力度",
        "expected_category": "operation",
        "expected_source_hint": "campaign_rules",
        "expect_answer": True,
        "is_colloquial": True,
    },
    # ================= faq（常见问题）4 条 =================
    {
        "question": "平台支持哪些付款方式",
        "expected_category": "faq",
        "expected_source_hint": "payment_methods",
        "expect_answer": True,
        "is_colloquial": False,
    },
    {
        "question": "能用花呗付款不",
        "expected_category": "faq",
        "expected_source_hint": "payment_methods",
        "expect_answer": True,
        "is_colloquial": True,
    },
    {
        # 基线修订：原为无答案条目，但基线显示其会被错误命中且给出不可靠回答；
        # G2 已补"平台服务边界"知识卡，该问题成为可正确回答的知识条目。
        "question": "附近哪家线下门店有现货可以自提",
        "expected_category": "faq",
        "expected_source_hint": "service_boundary",
        "expect_answer": True,
        "is_colloquial": False,
    },
    {
        # 基线修订：同上，补服务边界卡后改为可回答。
        "question": "能帮我修一下我的笔记本电脑吗",
        "expected_category": "faq",
        "expected_source_hint": "service_boundary",
        "expect_answer": True,
        "is_colloquial": True,
    },
    # ================= 无答案问题（验证不编造兜底）3 条 =================
    {
        "question": "怎么申请营业执照",
        "expected_category": "other",
        "expected_source_hint": "",
        "expect_answer": False,
        "is_colloquial": False,
    },
    {
        "question": "怎么煮出一碗好吃的面条",
        "expected_category": "other",
        "expected_source_hint": "",
        "expect_answer": False,
        "is_colloquial": False,
    },
    {
        "question": "附近有什么好吃的餐厅可以推荐",
        "expected_category": "other",
        "expected_source_hint": "",
        "expect_answer": False,
        "is_colloquial": True,
    },
]

# 无答案问题条数（方案要求 3 条）
NO_ANSWER_COUNT = 3
