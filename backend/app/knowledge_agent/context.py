"""Knowledge context builder for Knowledge Agent answers."""

from __future__ import annotations

from app.knowledge_agent.models import KnowledgeSearchResult, KnowledgeSourceCitation


ANSWER_CONSTRAINTS = [
    "Answer only from retrieved knowledge chunks.",
    "If retrieved knowledge is insufficient, clearly say the knowledge base does not contain enough information.",
    "Do not invent platform rules, policy details, refund conditions, delivery timelines or product specifications.",
    "Prefer concise customer-service wording and include source-aware reasoning metadata.",
    "For product questions, answer in fields: product positioning, core specs, features, use cases, compatibility, advantages, common questions.",
    "For policy and SOP questions, answer in fields: rule, scope, process, boundary, exception, next action, source.",
    "Always include a short source citation section with document name and chunk id when available.",
]


class KnowledgeContextBuilder:
    """Builds answer context, citation context and anti-hallucination constraints."""

    def build(self, *, query: str, retrieval_query: str, chunks: list[dict]) -> KnowledgeSearchResult:
        citations = [self._citation_from_chunk(chunk) for chunk in chunks]
        documents = self._documents_from_citations(citations)
        context = self.build_context(chunks)
        return KnowledgeSearchResult(
            query=query,
            retrieval_query=retrieval_query,
            documents=documents,
            chunks=chunks,
            citations=citations,
            context=context,
            answer_constraints=list(ANSWER_CONSTRAINTS),
            has_relevant=bool(chunks),
            debug_info={
                "retrieved_chunks": len(chunks),
                "retrieved_documents": len(documents),
                "top_similarity": citations[0].similarity_score if citations else 0.0,
            },
        )

    def build_context(self, chunks: list[dict]) -> str:
        if not chunks:
            return "No relevant knowledge chunks were retrieved."
        parts: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            metadata = chunk.get("metadata", {}) or {}
            source = metadata.get("file_name") or metadata.get("source") or "unknown"
            document_id = metadata.get("file_id") or metadata.get("document_id") or source
            category = metadata.get("knowledge_category") or metadata.get("category") or "other"
            score = float(chunk.get("relevance_score", chunk.get("similarity", 0.0)) or 0.0)
            hit_index = metadata.get("chunk_index", index)

            # 来源标注（任务 B4）：区分"命中片段"与"父块完整上下文"，
            # 内容优先使用父块完整内容（分数与引用仍对应命中的子块）
            parent_content = str(chunk.get("parent_content", "") or "").strip()
            if parent_content and metadata.get("parent_id"):
                source_tag = f"[来源: {category}/{source} | 命中: 子块#{hit_index} | 父块完整内容]"
                content = parent_content
            else:
                source_tag = f"[来源: {category}/{source} | 命中: 片段#{hit_index}]"
                content = str(chunk.get("content", ""))

            parts.append(
                "\n".join(
                    [
                        f"[Knowledge Chunk {index}]",
                        f"Document: {source}",
                        f"Document ID: {document_id}",
                        f"Chunk ID: {chunk.get('chunk_id', '')}",
                        f"Category: {category}",
                        f"Similarity: {score:.4f}",
                        source_tag,
                        "Content:",
                        content,
                    ]
                )
            )
        return "\n\n---\n\n".join(parts)

    def build_system_prompt(self, search_result: KnowledgeSearchResult) -> str:
        constraints = "\n".join(f"- {item}" for item in search_result.answer_constraints)
        return f"""You are the independent Knowledge Agent for an AI commerce customer service platform.

Responsibilities:
- Answer enterprise knowledge questions about platform rules, refund policies, delivery rules, membership rules, after-sales policy, complaint handling, customer-service SOP, product documentation and FAQ.
- Use only the retrieved knowledge context below.
- Do not access or infer from structured business database data.

Answer constraints:
{constraints}

回答风格（重要）：
- 你是在手机聊天框里回答用户，像淘宝/抖音客服那样说话
- 纯文本，绝对不要用 Markdown 符号（不要 **、##、`、---、列表数字或 - ）
- 简短口语，先直接给答案，再补最关键的一两点，正常 2-4 句话说完
- 不要罗列字段标题，不要长篇大论，挑用户最需要的说
- 如果知识库没有足够信息，就直说没查到，别编

Retrieved knowledge context:
{search_result.context}
"""

    def _citation_from_chunk(self, chunk: dict) -> KnowledgeSourceCitation:
        metadata = chunk.get("metadata", {}) or {}
        document_name = metadata.get("file_name") or metadata.get("source") or "unknown"
        document_id = metadata.get("file_id") or metadata.get("document_id") or document_name
        score = float(chunk.get("relevance_score", chunk.get("similarity", 0.0)) or 0.0)
        return KnowledgeSourceCitation(
            document_name=document_name,
            document_id=document_id,
            chunk_id=chunk.get("chunk_id", ""),
            similarity_score=score,
            category=metadata.get("knowledge_category") or metadata.get("category", ""),
            source=metadata.get("source", document_name),
            metadata=metadata,
        )

    def _documents_from_citations(self, citations: list[KnowledgeSourceCitation]) -> list[dict]:
        by_id: dict[str, dict] = {}
        for citation in citations:
            item = by_id.setdefault(
                citation.document_id,
                {
                    "document_id": citation.document_id,
                    "document_name": citation.document_name,
                    "category": citation.category or "other",
                    "source": citation.source,
                    "chunks": [],
                    "max_similarity": 0.0,
                },
            )
            item["chunks"].append(citation.chunk_id)
            item["max_similarity"] = max(item["max_similarity"], citation.similarity_score)
        return list(by_id.values())


knowledge_context_builder = KnowledgeContextBuilder()
