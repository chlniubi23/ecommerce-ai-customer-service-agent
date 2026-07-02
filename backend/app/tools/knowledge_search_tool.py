"""Knowledge search tool backed by the existing RAG infrastructure."""

from __future__ import annotations

import logging
from typing import Any

from app.database.repositories import AgentAuditRepository
from app.knowledge_agent.context import knowledge_context_builder
from app.knowledge_agent.query_understanding import knowledge_query_understanding
from app.rag.services.context_builder import build_retrieval_query
from app.rag.services.retrieval_service import retrieval_service
from app.rag.vectorstore import chroma_store
from app.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class KnowledgeSearchTool(BaseTool):
    """Search enterprise knowledge through RetrievalService and VectorStore."""

    @property
    def name(self) -> str:
        return "knowledge_search"

    @property
    def description(self) -> str:
        return (
            "Search enterprise knowledge base documents, policies, SOPs, FAQ and "
            "product documentation through the existing RAG retrieval service."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "query": {"type": "string", "description": "Knowledge question or search query.", "required": True},
            "top_k": {"type": "integer", "description": "Number of chunks to retrieve.", "required": False},
            "min_score": {"type": "number", "description": "Minimum relevance score.", "required": False},
            "category": {"type": "string", "description": "Optional knowledge category.", "required": False},
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = str(kwargs.get("query", "")).strip()
        top_k = int(kwargs.get("top_k") or 5)
        min_score = float(kwargs.get("min_score") or 0.01)
        history = kwargs.get("history") or []
        allow_llm = bool(kwargs.get("allow_llm", True))

        if not query:
            return ToolResult(success=False, error="Missing knowledge query", tool_name=self.name)

        # ===== 大白话查询理解层 =====
        # 顺序很关键：
        # 1) 先用对话历史做指代消解（"那要多久啊" + 上文"退款" → "退款 那要多久啊"），
        #    否则裸追问句无任何可识别术语。
        # 2) 再在消解后的句子上跑查询理解，把口语改写为知识库正式术语 + 推断分类，
        #    解决 N-gram Embedding 字面匹配缺陷。
        history_list = history if isinstance(history, list) else []
        context_resolved_query = build_retrieval_query(query, history_list)
        understanding = await knowledge_query_understanding.understand(
            context_resolved_query,
            history=history_list,
            allow_llm=allow_llm,
        )

        # 分类：显式传入 > 查询理解推断 > 关键词兜底
        explicit_category = str(kwargs.get("category", "")).strip()
        keyword_category = _normalize_category("", context_resolved_query)
        allowed_categories = _resolve_allowed_categories(explicit_category, understanding.category, keyword_category)
        # 主分类用于查询扩展/排序：优先显式，其次 LLM，再次关键词
        category = explicit_category or understanding.category or keyword_category

        # 检索 Query：优先用查询理解的 expanded_query（已含口语改写 + 分类扩展）
        expanded_query = understanding.expanded_query or _expand_query_terms(context_resolved_query, category)
        retrieval_window = max(top_k * 8, 30)

        retrieval = retrieval_service.query_knowledge(
            question=expanded_query,
            top_k=retrieval_window,
            min_score=min_score,
        )
        chunks = retrieval.chunks

        if allowed_categories:
            category_chunks = [chunk for chunk in chunks if _chunk_matches_any_category(chunk, allowed_categories)]
            if category_chunks:
                chunks = category_chunks
            else:
                fallback = retrieval_service.query_knowledge(
                    question=expanded_query,
                    top_k=retrieval_window,
                    min_score=max(0.0, min_score * 0.5),
                )
                chunks = [chunk for chunk in fallback.chunks if _chunk_matches_any_category(chunk, allowed_categories)]

        chunks = _expand_same_source_chunks(query, chunks)
        chunks = _rank_chunks_for_query(
            query, chunks, category, product_target=understanding.product_target,
        )[:top_k]

        search_result = knowledge_context_builder.build(
            query=query,
            retrieval_query=expanded_query,
            chunks=chunks,
        )
        data = {
            "query": query,
            "retrieval_query": expanded_query,
            "inferred_category": category,
            "query_understanding": understanding.to_dict(),
            "documents": search_result.documents,
            "chunks": search_result.chunks,
            "citations": [citation.to_dict() for citation in search_result.citations],
            "similarity_scores": [
                {
                    "chunk_id": citation.chunk_id,
                    "score": citation.similarity_score,
                    "document_id": citation.document_id,
                    "document_name": citation.document_name,
                }
                for citation in search_result.citations
            ],
            "final_context": search_result.context,
            "answer_constraints": search_result.answer_constraints,
            "debug_info": {
                **retrieval.debug_info,
                **search_result.debug_info,
                "inferred_category": category,
                "expanded_query": expanded_query,
                "query_understanding": understanding.to_dict(),
            },
        }
        success = bool(chunks)
        _record_audit(self.name, kwargs, data, success)
        if not success:
            return ToolResult(success=False, data=data, error="No relevant knowledge chunks found", tool_name=self.name)
        return ToolResult(success=True, data=data, tool_name=self.name)


def _normalize_category(explicit_category: str, query: str) -> str:
    if explicit_category:
        return explicit_category
    lowered = query.lower()
    rules = [
        ("refund", ["退款", "退货", "售后", "审核", "到账", "拒绝", "七天无理由"]),
        ("product", ["参数", "配置", "芯片", "内存", "存储", "屏幕", "重量", "续航", "接口", "兼容", "macbook", "thinkbook", "iphone", "ipad", "airpods", "sony", "rog", "xiaomi"]),
        ("membership", ["会员", "积分", "成长值", "等级", "权益"]),
        ("coupon", ["优惠券", "满减", "折扣", "领取", "使用", "失效"]),
        ("logistics", ["物流", "配送", "发货", "签收", "到哪", "异常", "赔付"]),
        ("complaint", ["投诉", "升级", "主管", "处理", "申诉"]),
        ("sop", ["sop", "流程", "规范", "客服处理"]),
        ("policy", ["政策", "规则", "协议", "隐私"]),
        ("operation", ["运营", "活动", "价格", "库存"]),
        ("faq", ["faq", "常见问题", "怎么", "如何", "为什么"]),
    ]
    for category, keywords in rules:
        if any(keyword in lowered for keyword in keywords):
            return category
    return ""


def _expand_query_terms(query: str, category: str) -> str:
    expansions = {
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
    extra = expansions.get(category, "")
    return f"{query} {extra}".strip()


def _resolve_allowed_categories(explicit_category: str, llm_category: str, keyword_category: str) -> list[str]:
    """收敛出允许的知识分类集合。

    LLM 查询理解的分类不稳定（例如把"七天无理由退货"误判为 policy），
    因此把 显式分类 / LLM 分类 / 关键词分类 取并集，避免类别硬过滤把真正
    相关的块（如 refund）误删。保持顺序、去重、去空。
    """
    allowed: list[str] = []
    for cat in (explicit_category, llm_category, keyword_category):
        cat = (cat or "").strip()
        if cat and cat not in allowed:
            allowed.append(cat)
    return allowed


def _chunk_matches_any_category(chunk: dict[str, Any], categories: list[str]) -> bool:
    return any(_chunk_matches_category(chunk, c) for c in categories)


def _chunk_matches_category(chunk: dict[str, Any], category: str) -> bool:
    metadata = chunk.get("metadata", {}) or {}
    chunk_category = str(metadata.get("knowledge_category") or metadata.get("category") or "").lower()
    file_name = str(metadata.get("file_name") or metadata.get("source") or "").lower()
    if chunk_category and chunk_category != "other":
        return chunk_category == category
    return f"/{category}/" in file_name or file_name.startswith(f"{category}_") or category in file_name


def _rank_chunks_for_query(
    query: str,
    chunks: list[dict[str, Any]],
    category: str = "",
    product_target: str = "",
) -> list[dict[str, Any]]:
    """Stabilize runtime ranking for explicit enterprise knowledge questions."""
    lowered_query = query.lower()
    active_terms = _active_terms(lowered_query, category)
    # 优先用查询理解传入的商品型号（覆盖口语别名场景），否则从字面提取
    resolved_product = product_target or _product_target(lowered_query)
    target_source = _target_source_for_query(lowered_query)

    def score(chunk: dict[str, Any]) -> float:
        content = str(chunk.get("content", "")).lower()
        metadata = chunk.get("metadata", {}) or {}
        file_name = str(metadata.get("file_name", "")).lower()
        base = float(chunk.get("relevance_score", 0.0) or 0.0)
        term_hits = sum(1 for term in active_terms if term.lower() in content)
        query_token_hits = sum(1 for token in _query_tokens(lowered_query) if token in content or token in file_name)
        source_boost = 0.0
        if category and _chunk_matches_category(chunk, category):
            source_boost += 0.2
        if any(term in content for term in ["原子知识卡", "核心参数", "关键参数", "规格信息"]):
            source_boost += 0.25
        if any(term in content for term in ["核心规则", "规则说明", "适用范围", "常见问题", "可回答问题"]):
            source_boost += 0.12
        if resolved_product:
            normalized_target = resolved_product.lower().replace("-", "_").replace(" ", "_")
            if _matches_product_target(file_name, content, normalized_target):
                source_boost += 0.45
            elif category == "product" and _looks_like_product_chunk(file_name, content):
                source_boost -= 0.18
        if target_source and target_source in file_name:
            source_boost += 0.35
        if "knowledge agent" in content:
            source_boost += 0.04
        return base + term_hits * 0.04 + query_token_hits * 0.03 + source_boost

    ranked = sorted(chunks, key=score, reverse=True)
    for chunk in ranked:
        chunk["runtime_rank_score"] = round(score(chunk), 4)
    return ranked


def _target_source_for_query(lowered_query: str) -> str:
    source_rules = [
        ("seven_day_return_atomic", ["七天无理由", "无理由退货"]),
        ("refund_rejection_atomic", ["不能退款", "无法退款", "退款被拒", "拒绝退款"]),
        ("refund_timeline_atomic", ["退款多久到账", "多久到账", "到账时效", "退款时效", "退款规则"]),
        ("coupon_receive_atomic", ["优惠券怎么领取", "怎么领取优惠券", "领券", "优惠券领取"]),
        ("membership_level_atomic", ["会员等级", "会员权益", "会员有哪些等级"]),
        ("logistics_timeline_atomic", ["物流政策", "配送时效", "配送状态"]),
        ("complaint_escalation_atomic", ["投诉升级", "主管介入"]),
    ]
    for source, phrases in source_rules:
        if any(phrase in lowered_query for phrase in phrases):
            return source
    return ""


def _product_target(lowered_query: str) -> str:
    product_aliases = [
        ("macbook_air_m4", ["macbook air m4", "macbook air", "air m4"]),
        ("macbook_pro_m4", ["macbook pro m4", "macbook pro"]),
        ("thinkbook_14_plus", ["thinkbook 14+", "thinkbook 14 plus", "thinkbook"]),
        ("iphone_16", ["iphone16", "iphone 16"]),
        ("ipad_air", ["ipad air"]),
        ("airpods_pro_2", ["airpods pro 2", "airpods"]),
        ("sony_wh_1000xm5", ["sony wh-1000xm5", "wh-1000xm5", "xm5"]),
        ("rog_ally", ["rog ally"]),
        ("xiaomi_15", ["xiaomi 15", "小米15", "小米 15"]),
    ]
    for target, aliases in product_aliases:
        if any(alias in lowered_query for alias in aliases):
            return target
    return ""


def _matches_product_target(file_name: str, content: str, target: str) -> bool:
    normalized_file = file_name.replace("-", "_").replace(" ", "_")
    normalized_content = content.replace("-", "_").replace(" ", "_")
    if target in normalized_file or target in normalized_content:
        return True
    if target == "iphone_16" and "iphone_16" in normalized_file:
        return True
    return False


def _looks_like_product_chunk(file_name: str, content: str) -> bool:
    product_markers = [
        "macbook", "thinkbook", "iphone", "ipad", "airpods", "sony", "rog",
        "xiaomi", "产品定位", "核心参数",
    ]
    source = f"{file_name} {content}".lower()
    return any(marker in source for marker in product_markers)


def _active_terms(lowered_query: str, category: str) -> list[str]:
    terms = {
        "product": ["参数", "配置", "芯片", "内存", "存储", "屏幕", "重量", "续航", "接口", "spec", "sku", "兼容"],
        "refund": ["退款", "退货", "审核", "到账", "拒绝", "售后", "七天无理由"],
        "coupon": ["优惠券", "满减", "折扣", "领取", "使用", "失效"],
        "membership": ["会员", "等级", "积分", "成长值", "权益"],
        "logistics": ["物流", "配送", "发货", "签收", "异常", "赔付"],
        "complaint": ["投诉", "升级", "主管", "处理时限"],
        "sop": ["sop", "流程", "规范", "客服"],
    }
    selected = terms.get(category, [])
    if selected:
        return selected
    return [term for values in terms.values() for term in values if term in lowered_query]


def _query_tokens(query: str) -> list[str]:
    separators = [" ", "，", "。", "？", "?", "、", "+", "-", "_"]
    tokens = [query]
    for sep in separators:
        next_tokens: list[str] = []
        for token in tokens:
            next_tokens.extend(token.split(sep))
        tokens = next_tokens
    return [token for token in tokens if len(token.strip()) >= 2]


def _expand_same_source_chunks(query: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Include relevant sibling chunks from the same source document."""
    if not chunks or not _is_detail_query(query):
        return chunks

    query_text = query.lower()
    source_names = {
        str((chunk.get("metadata") or {}).get("file_name", ""))
        for chunk in chunks
        if (chunk.get("metadata") or {}).get("file_name")
    }
    matched_sources = {
        name for name in source_names if _source_matches_query(name, query_text)
    }
    if not matched_sources:
        return chunks

    by_id = {chunk.get("chunk_id"): dict(chunk) for chunk in chunks}
    for item in chroma_store._data:
        metadata = item.get("metadata", {}) or {}
        file_name = str(metadata.get("file_name", ""))
        if file_name not in matched_sources:
            continue
        chunk_id = item.get("id")
        if chunk_id in by_id:
            continue
        by_id[chunk_id] = {
            "chunk_id": chunk_id,
            "content": item.get("content", ""),
            "metadata": metadata,
            "distance": 1.0,
            "relevance_score": 0.0,
        }
    return list(by_id.values())


def _is_detail_query(query: str) -> bool:
    text = query.lower()
    detail_terms = ["参数", "配置", "规格", "芯片", "内存", "存储", "屏幕", "重量", "续航", "接口", "介绍", "说明", "兼容"]
    return any(term in text for term in detail_terms)


def _source_matches_query(file_name: str, query_text: str) -> bool:
    stem = file_name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").lower()
    tokens = [token for token in stem.split() if len(token) > 1]
    if not tokens:
        return False
    hits = sum(1 for token in tokens if token in query_text)
    return hits >= max(1, min(2, len(tokens)))


def _record_audit(tool_name: str, kwargs: dict[str, Any], result: dict[str, Any], success: bool) -> None:
    try:
        AgentAuditRepository().record(
            agent_name=kwargs.get("agent_name", "KnowledgeAgent"),
            tool_name=tool_name,
            user_request=str(kwargs.get("query", "")),
            execution_result=result,
            workflow_id=kwargs.get("workflow_id"),
            session_id=kwargs.get("session_id"),
            success=success,
        )
    except Exception as exc:
        logger.warning("[KnowledgeSearchTool] audit log failed: %s", exc)
