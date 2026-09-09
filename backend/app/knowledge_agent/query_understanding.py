"""Knowledge Query Understanding - 大白话查询理解层

为什么需要这一层：
- 向量库使用 N-gram Hash Embedding（rag/vectorstore/chroma_store.py），
  它基于字面字符 n-gram 重叠做相似度匹配，**不理解语义**。
- 用户说大白话（"我那笔钱咋还没回来啊"），知识库写的是正式术语
  （"退款到账时效"），两者字符几乎零重叠 → 检索直接失败。
- 这一层把口语改写成知识库里的"检索关键词"，让检索召回率大幅提升。

双层设计（成本/延迟最优）：
1. 规则快路径（Rule Fast-Path）：基于口语词典做同义改写 + 分类识别。
   零延迟、零 LLM 成本，覆盖绝大多数高频口语。
2. LLM 语义改写（LLM Rewrite）：仅当规则置信度低且句子像口语/含指代时，
   才调用 LLM 把句子改写为正式检索 Query，避免每次都付 LLM 成本。

架构位置：
- knowledge_agent/ 层，被 tools/knowledge_search_tool.py 在检索前调用
- 输出 QueryUnderstanding，供检索 Query 构建 + 分类过滤 + Trace 展示
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from app.services.llm import call_llm

logger = logging.getLogger(__name__)


# ============================================================
# 口语 → 正式检索术语 词典
# ============================================================
# 每条规则：colloquial patterns（口语片段）→ canonical terms（知识库检索关键词）+ category
# patterns 用 "包含匹配"（substring），覆盖用户最常见的大白话表达。
# canonical terms 直接取自各原子知识卡 "检索关键词" 字段，保证字面命中。

@dataclass(frozen=True)
class LexiconRule:
    category: str
    patterns: tuple[str, ...]       # 口语触发词
    canonical: tuple[str, ...]      # 改写后的正式检索词
    weight: float = 1.0             # 命中权重（影响分类置信度）


COLLOQUIAL_LEXICON: tuple[LexiconRule, ...] = (
    # ---------- 退款到账时效 ----------
    LexiconRule(
        category="refund",
        patterns=("钱啥时候到", "钱什么时候到", "钱咋还没", "钱怎么还没", "钱还没回来",
                  "钱没退", "退的钱呢", "我那笔钱", "退款到哪了", "退的款呢",
                  "啥时候退给我", "多久退到", "多久能到账", "几天到账", "到账要多久"),
        canonical=("退款多久到账", "退款到账时效", "退款审核", "原路退回"),
        weight=1.2,
    ),
    LexiconRule(
        category="refund",
        patterns=("审核多久", "审核要多久", "还在审核", "审核完了吗", "审核进度"),
        canonical=("退款审核时效", "退款审核多久", "退款规则"),
    ),
    # ---------- 能不能退 / 七天无理由 ----------
    LexiconRule(
        category="refund",
        patterns=("能退不", "能退吗", "可以退吗", "能不能退", "想退掉", "想退货",
                  "不想要了", "买错了想退", "退得了吗", "支持退吗", "拆封了能退"),
        canonical=("七天无理由退货", "退货条件", "退款规则", "无理由退货"),
        weight=1.1,
    ),
    # ---------- 退不了 / 拒绝退款 ----------
    LexiconRule(
        category="refund",
        patterns=("退不了", "不给退", "为啥不能退", "为什么不能退", "退款被拒",
                  "拒绝退款", "退款失败", "不让退", "退款驳回"),
        canonical=("什么情况不能退款", "退款拒绝", "退款被拒", "售后期限"),
        weight=1.2,
    ),
    # ---------- 退货运费 ----------
    LexiconRule(
        category="refund",
        patterns=("退货运费", "退货要钱吗", "运费谁出", "运费谁承担", "退回去的邮费"),
        canonical=("退货运费谁承担", "退货运费", "退货规则"),
    ),

    # ---------- 物流配送时效 ----------
    LexiconRule(
        category="logistics",
        patterns=("快递到哪", "我东西呢", "我的货呢", "包裹呢", "咋还没到", "怎么还没到",
                  "什么时候到", "啥时候发货", "啥时候到", "多久能到", "几天能到",
                  "发货了吗", "到哪里了", "物流到哪", "货到哪了"),
        canonical=("物流配送时效", "配送状态", "物流多久能到", "配送规则", "签收"),
        weight=1.2,
    ),
    # ---------- 物流不更新 / 异常 ----------
    LexiconRule(
        category="logistics",
        patterns=("不动了", "不更新", "卡住了", "物流停了", "一直不动", "好几天没动",
                  "没有物流信息", "轨迹不更新", "停在那"),
        canonical=("物流不更新怎么办", "物流异常", "异常件", "物流核查"),
        weight=1.1,
    ),
    LexiconRule(
        category="logistics",
        patterns=("快递丢了", "包裹丢了", "东西丢了", "没收到货", "没收到东西", "丢件"),
        canonical=("快递丢了怎么办", "丢件", "异常件", "物流赔付"),
    ),
    LexiconRule(
        category="logistics",
        patterns=("包装破了", "包裹破损", "盒子烂了", "东西压坏了", "外包装坏了", "破损"),
        canonical=("包裹破损怎么办", "物流赔付", "异常件"),
    ),
    LexiconRule(
        category="logistics",
        patterns=("改地址", "改收货地址", "换地址", "地址写错了"),
        canonical=("能改收货地址吗", "修改收货地址", "发货规则"),
    ),

    # ---------- 优惠券 ----------
    LexiconRule(
        category="coupon",
        patterns=("券咋用", "券怎么用", "优惠券怎么使", "怎么领券", "在哪领券", "哪里领券",
                  "怎么领优惠券", "优惠券在哪", "领券"),
        canonical=("优惠券怎么领取", "优惠券使用", "优惠券领取", "优惠券规则"),
        weight=1.1,
    ),
    LexiconRule(
        category="coupon",
        patterns=("券用不了", "优惠券用不了", "为啥用不了", "券不能用", "券失效",
                  "券过期", "优惠券为什么不能用"),
        canonical=("优惠券为什么不能用", "优惠券使用限制", "优惠券失效", "优惠券规则"),
    ),
    LexiconRule(
        category="coupon",
        patterns=("满减", "能不能叠加", "券能叠加", "叠加使用"),
        canonical=("满减券规则", "优惠券使用限制", "优惠券叠加"),
    ),

    # ---------- 会员 ----------
    LexiconRule(
        category="membership",
        patterns=("会员有啥用", "会员有什么用", "会员等级", "会员有哪些等级", "怎么升级会员",
                  "会员权益", "怎么成为会员", "会员怎么升", "升会员"),
        canonical=("会员等级有哪些", "会员权益", "成长值", "会员升级"),
        weight=1.1,
    ),
    LexiconRule(
        category="membership",
        patterns=("积分能干嘛", "积分有什么用", "积分能提现", "积分怎么用", "积分规则",
                  "成长值怎么来", "成长值咋算"),
        canonical=("积分规则", "成长值规则", "积分可以提现吗", "会员权益"),
    ),

    # ---------- 投诉 ----------
    LexiconRule(
        category="complaint",
        patterns=("我要投诉", "投诉咋弄", "投诉怎么弄", "怎么投诉", "投诉在哪", "找你们领导",
                  "找主管", "要投诉你们", "投诉提交"),
        canonical=("投诉怎么提交", "投诉流程", "投诉升级", "主管介入"),
        weight=1.1,
    ),
    LexiconRule(
        category="complaint",
        patterns=("投诉多久", "投诉处理多久", "投诉啥时候有结果", "什么时候升级主管",
                  "投诉结果不满意", "投诉没人管"),
        canonical=("投诉多久处理", "投诉升级规则", "主管介入", "处理时限"),
    ),

    # ---------- 物流赔付 ----------
    LexiconRule(
        category="logistics",
        patterns=("能赔吗", "赔不赔", "怎么赔", "赔偿", "理赔"),
        canonical=("物流赔付规则", "丢件赔付", "异常件赔付"),
    ),
)


# 商品型号别名（命中即归类 product，并补充正式型号词）
PRODUCT_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("MacBook Air M4", ("苹果笔记本", "mac air", "macbook air", "air m4", "苹果air")),
    ("MacBook Pro M4", ("macbook pro", "mac pro", "苹果pro本")),
    ("ThinkBook 14+", ("thinkbook", "联想thinkbook", "think book")),
    ("iPhone 16", ("iphone16", "iphone 16", "苹果16", "苹果手机16")),
    ("iPhone 16 Pro", ("iphone16pro", "iphone 16 pro", "苹果16pro")),
    ("iPad Air", ("ipad air", "ipadair", "苹果平板air")),
    ("AirPods Pro 2", ("airpods", "airpods pro", "苹果耳机", "苹果无线耳机")),
    ("Sony WH-1000XM5", ("索尼耳机", "wh-1000xm5", "xm5", "索尼降噪")),
    ("ROG Ally", ("rog ally", "rog掌机", "败家之眼掌机")),
    ("Xiaomi 15", ("小米15", "小米 15", "xiaomi 15")),
)

# 商品类问句信号（用户在问规格/参数）
PRODUCT_INTENT_TERMS = (
    "参数", "配置", "规格", "多大", "几寸", "屏幕", "内存", "存储", "续航",
    "电池", "重量", "芯片", "处理器", "接口", "扩展", "能不能升级内存",
    "值得买", "怎么样", "好用吗", "适合", "对比", "区别",
)


# 短问题/指代词阈值（触发 LLM 改写判断）
_REFERENCE_WORDS = ("这个", "那个", "它", "上面", "刚才", "之前", "还能", "还可以",
                    "怎么办", "咋办", "咋整")


@dataclass
class QueryUnderstanding:
    """查询理解结果"""
    original_query: str
    normalized_query: str                       # 口语改写为正式术语后的查询
    expanded_query: str                         # normalized + 扩展词，最终用于检索
    category: str = ""                          # 推断的知识分类
    canonical_terms: list[str] = field(default_factory=list)
    matched_phrases: list[str] = field(default_factory=list)
    product_target: str = ""                    # 命中的商品正式型号
    confidence: float = 0.0                     # 理解置信度
    used_llm: bool = False                      # 是否触发了 LLM 改写
    debug: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "original_query": self.original_query,
            "normalized_query": self.normalized_query,
            "expanded_query": self.expanded_query,
            "category": self.category,
            "canonical_terms": self.canonical_terms,
            "matched_phrases": self.matched_phrases,
            "product_target": self.product_target,
            "confidence": round(self.confidence, 3),
            "used_llm": self.used_llm,
        }


# 分类级扩展词（与 knowledge_search_tool._expand_query_terms 对齐，集中维护）
CATEGORY_EXPANSIONS: dict[str, str] = {
    "refund": "退款规则 退款时效 退款多久到账 退款审核 七天无理由 退款拒绝 售后流程",
    "product": "商品知识 参数介绍 核心参数 规格信息 芯片 内存 存储 屏幕 重量 续航 接口 兼容性",
    "membership": "会员等级 会员权益 积分 成长值 升级机制",
    "coupon": "优惠券领取 优惠券使用 满减券 折扣券 发放规则 使用限制 失效规则",
    "logistics": "物流规则 配送时效 发货 签收 异常件 物流赔付",
    "complaint": "投诉规则 投诉流程 投诉升级 主管介入 处理时限",
    "sop": "客服SOP 客服处理规范 升级SOP 主管处理SOP",
    "operation": "运营规则 活动规则 促销规则 价格策略 库存管理",
    "policy": "平台规则 政策 条款 适用范围 例外情况",
    "faq": "高频问答 常见问题 标准回答",
}


LLM_REWRITE_PROMPT = """你是电商客服知识库的"检索查询改写器"。

用户用口语/大白话提问，但知识库文档使用正式术语。你的任务：把用户问题改写成适合检索企业知识库的**正式中文查询**，并判断它属于哪个知识分类。

知识分类（只能选其一）：
- refund（退款/退货/售后/到账/七天无理由）
- logistics（物流/配送/发货/签收/快递异常/丢件/破损/赔付）
- coupon（优惠券/满减/折扣/领券/用券）
- membership（会员/等级/权益/积分/成长值）
- complaint（投诉/升级/主管介入/处理时限）
- product（具体商品参数/规格/型号，如 MacBook、iPhone、ThinkBook）
- sop（客服处理规范/流程）
- policy（平台政策/规则/条款）
- faq（其他常见问题）
- other（无法归类）

要求：
1. normalized_query：用知识库正式术语重写问题，保留核心诉求，去掉情绪词和废话
2. keywords：3-6 个正式检索关键词
3. category：上面分类之一
4. 不要编造用户没问的内容

只输出 JSON，格式：
{{"normalized_query": "...", "keywords": ["...", "..."], "category": "..."}}

用户问题：{query}"""


class KnowledgeQueryUnderstanding:
    """知识库查询理解服务（规则快路径 + LLM 改写兜底）"""

    # 规则置信度达到此值则跳过 LLM
    RULE_CONFIDENCE_SKIP_LLM = 0.6

    def understand_sync(self, query: str) -> QueryUnderstanding:
        """同步规则理解（不调用 LLM），供无需 LLM 兜底的场景使用"""
        return self._rule_understand(query)

    async def understand(
        self,
        query: str,
        history: list[dict] | None = None,
        allow_llm: bool = True,
    ) -> QueryUnderstanding:
        """
        理解用户查询

        Args:
            query: 用户原始问题（可能是大白话）
            history: 对话历史（用于指代消解判断）
            allow_llm: 是否允许 LLM 改写兜底

        Returns:
            QueryUnderstanding
        """
        result = self._rule_understand(query)

        # 规则已足够自信 → 直接返回，零 LLM 成本
        if result.confidence >= self.RULE_CONFIDENCE_SKIP_LLM:
            logger.info(
                "[QueryUnderstanding] 规则命中 category=%s conf=%.2f phrases=%s",
                result.category, result.confidence, result.matched_phrases,
            )
            return result

        # 规则不自信 + 允许 LLM + 句子像口语 → LLM 改写
        if allow_llm and self._should_use_llm(query):
            llm_result = await self._llm_rewrite(query, result)
            if llm_result:
                logger.info(
                    "[QueryUnderstanding] LLM 改写: '%s' → '%s' (category=%s)",
                    query[:30], llm_result.normalized_query[:40], llm_result.category,
                )
                return llm_result

        logger.info(
            "[QueryUnderstanding] 规则低置信 fallback category=%s conf=%.2f",
            result.category, result.confidence,
        )
        return result

    # -------------------- 规则层 --------------------

    def _rule_understand(self, query: str) -> QueryUnderstanding:
        text = query.strip()
        lowered = text.lower()

        matched_phrases: list[str] = []
        canonical_terms: list[str] = []
        category_scores: dict[str, float] = {}

        # 1. 口语词典匹配
        for rule in COLLOQUIAL_LEXICON:
            hit = next((p for p in rule.patterns if p in lowered), None)
            if hit:
                matched_phrases.append(hit)
                canonical_terms.extend(rule.canonical)
                category_scores[rule.category] = (
                    category_scores.get(rule.category, 0.0) + rule.weight
                )

        # 2. 商品型号识别
        product_target = ""
        for formal_name, aliases in PRODUCT_ALIASES:
            if any(alias in lowered for alias in aliases):
                product_target = formal_name
                canonical_terms.append(formal_name)
                category_scores["product"] = category_scores.get("product", 0.0) + 1.3
                break

        # 商品参数问句信号加成
        if product_target or any(term in lowered for term in PRODUCT_INTENT_TERMS):
            if product_target:
                category_scores["product"] = category_scores.get("product", 0.0) + 0.4

        # 3. 决定分类
        category = ""
        confidence = 0.0
        if category_scores:
            category = max(category_scores, key=category_scores.get)
            top_score = category_scores[category]
            # 置信度：命中权重映射到 0~1，单条强命中即可达 0.6+
            confidence = min(1.0, 0.35 + top_score * 0.3)

        # 4. 构建 normalized / expanded query
        # normalized：原问题 + 正式术语（去重）
        unique_terms = _dedupe_preserve_order(canonical_terms)
        normalized_query = text
        if unique_terms:
            normalized_query = f"{text} {' '.join(unique_terms)}".strip()

        expanded_query = self._build_expanded(normalized_query, category, product_target)

        return QueryUnderstanding(
            original_query=text,
            normalized_query=normalized_query,
            expanded_query=expanded_query,
            category=category,
            canonical_terms=unique_terms,
            matched_phrases=matched_phrases,
            product_target=product_target,
            confidence=confidence,
            used_llm=False,
            debug={"category_scores": category_scores},
        )

    def _build_expanded(self, normalized_query: str, category: str, product_target: str) -> str:
        parts = [normalized_query]
        expansion = CATEGORY_EXPANSIONS.get(category, "")
        if expansion:
            parts.append(expansion)
        if product_target:
            parts.append(product_target)
        return " ".join(parts).strip()

    # -------------------- LLM 层 --------------------

    def _should_use_llm(self, query: str) -> bool:
        """判断是否值得调用 LLM 改写（句子像口语/短/含指代）"""
        text = query.strip()
        if len(text) <= 14:
            return True
        if any(word in text for word in _REFERENCE_WORDS):
            return True
        # 含口语语气词 → 倾向口语
        if any(tone in text for tone in ("啊", "呀", "咋", "呢", "嘛", "咧", "哈")):
            return True
        return False

    async def _llm_rewrite(
        self, query: str, rule_result: QueryUnderstanding,
    ) -> QueryUnderstanding | None:
        try:
            raw = await call_llm(
                system_prompt=LLM_REWRITE_PROMPT.format(query=query[:200]),
                user_message=query[:200],
                history=[],
                temperature=0.1,
                max_tokens=200,
            )
            data = _parse_json(raw)
            if not data:
                return None

            normalized = str(data.get("normalized_query", "")).strip() or query
            keywords = data.get("keywords", [])
            if not isinstance(keywords, list):
                keywords = []
            keywords = [str(k).strip() for k in keywords if str(k).strip()]
            category = str(data.get("category", "")).strip().lower()
            if category not in CATEGORY_EXPANSIONS and category != "other":
                category = rule_result.category or category

            # 合并规则层与 LLM 的术语
            merged_terms = _dedupe_preserve_order(
                rule_result.canonical_terms + keywords
            )
            normalized_query = f"{normalized} {' '.join(merged_terms)}".strip()
            expanded_query = self._build_expanded(
                normalized_query, category, rule_result.product_target
            )

            return QueryUnderstanding(
                original_query=query,
                normalized_query=normalized_query,
                expanded_query=expanded_query,
                category=category if category != "other" else "",
                canonical_terms=merged_terms,
                matched_phrases=rule_result.matched_phrases,
                product_target=rule_result.product_target,
                confidence=max(rule_result.confidence, 0.75),
                used_llm=True,
                debug={
                    "rule_category": rule_result.category,
                    "llm_category": category,
                    "llm_keywords": keywords,
                },
            )
        except Exception as exc:
            logger.warning("[QueryUnderstanding] LLM 改写失败: %s", exc)
            return None


# -------------------- 辅助函数 --------------------

def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out


def _parse_json(raw: str) -> dict | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


# 全局单例
knowledge_query_understanding = KnowledgeQueryUnderstanding()
