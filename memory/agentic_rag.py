from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pinecone import Pinecone

load_dotenv()


# LangSmith span decorator, with a no-op fallback when langsmith is absent.
try:
    from langsmith import traceable
except Exception:
    def traceable(*d_args, **d_kwargs):
        def _wrap(fn):
            return fn
        return _wrap(d_args[0]) if d_args and callable(d_args[0]) else _wrap


TOP_K                  = 5
RETRIEVE_K             = 12   # over-fetch, then rerank down to TOP_K
MIN_RELEVANT_DOCS      = 1
MAX_RETRIEVAL_ATTEMPTS = 2
CHUNK_SIZE             = 500
CHUNK_OVERLAP          = 100
RERANK_ENABLED         = True
RERANK_MODEL           = "bge-reranker-v2-m3"   # Pinecone-hosted cross-encoder


def get_tenant_id(user_id: str) -> str:
    """Derive a stable, Pinecone-safe tenant ID from a user's email address.

    Uses the full email so each user gets their own isolated namespace
    (e.g. alice@acme.com -> 'alice_acme_com', bob@acme.com -> 'bob_acme_com').
    """
    import re
    return re.sub(r"[^a-z0-9_]", "_", user_id.lower())


def tenant_namespace(user_id: str, base_namespace: str) -> str:
    """Return a per-tenant Pinecone namespace, e.g. 'acme_com__company_rubrics'."""
    return f"{get_tenant_id(user_id)}__{base_namespace}"


@dataclass
class RAGResult:
    context:     str
    sources:     list[str]          = field(default_factory=list)
    warning:     Optional[str]      = None
    steps_taken: list[str]          = field(default_factory=list)

    def has_context(self) -> bool:
        return bool(self.context.strip())


class AgenticRAG:

    def __init__(self):
        self.embeddings = OpenAIEmbeddings(
            model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.llm_rewriter = ChatOpenAI(
            model=os.getenv("OPENAI_AGENT_MODEL", "gpt-4o"),
            temperature=0,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.llm_grader = ChatOpenAI(
            model=os.getenv("OPENAI_GRADER_MODEL", "gpt-4o-mini"),
            temperature=0,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )
        self._pc    = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self._index = self._pc.Index(os.getenv("PINECONE_INDEX_NAME"))


    @traceable(name="rag.decide_retrieve", run_type="chain")
    def _should_retrieve(self, query: str) -> bool:
        from langchain_core.messages import HumanMessage
        prompt = [HumanMessage(content=(
            f"Does answering this query require retrieving documents from a knowledge base?\n"
            f"Query: {query}\n"
            f"Reply with YES or NO only."
        ))]
        response = self.llm_grader.invoke(prompt)
        answer   = response.content.strip().upper()
        return answer.startswith("Y")


    @traceable(name="rag.rewrite_query", run_type="chain")
    def _rewrite_query(self, query: str, attempt: int = 1) -> str:
        style_instruction = (
            "Make it dense with domain-specific keywords and technical terms."
            if attempt == 1
            else
            "Use different terminology and synonyms compared to a previous "
            "failed search. Broaden the scope slightly."
        )


        from langchain_core.messages import HumanMessage
        prompt = [HumanMessage(content=(
            f"Rewrite the following search query to improve retrieval from a vector database "
            f"of recruiting and HR documents. {style_instruction}\n"
            f"Original query: {query}\n"
            f"Return ONLY the rewritten query, nothing else."
        ))]
        response = self.llm_rewriter.invoke(prompt)
        return response.content.strip()


    @traceable(name="rag.pinecone_retrieve", run_type="retriever")
    def _retrieve(self, rewritten_query: str, namespace: str) -> list[dict]:
        query_vector = self.embeddings.embed_query(rewritten_query)

        results = self._index.query(
            vector=query_vector,
            top_k=RETRIEVE_K,
            namespace=namespace,
            include_metadata=True,
        )

        docs = []
        for match in results.matches:
            docs.append({
                "id":       match.id,
                "score":    match.score,
                "text":     match.metadata.get("text", ""),
                "source":   match.metadata.get("source", "unknown"),
                "metadata": match.metadata,
            })
        return docs


    @traceable(name="rag.grade_docs", run_type="chain")
    def _grade_docs(self, query: str, docs: list[dict]) -> list[dict]:
        if not docs:
            return []

        relevant = []
        for doc in docs:
            if not doc["text"].strip():
                continue


            try:
                from langchain_core.messages import HumanMessage
                prompt = [HumanMessage(content=(
                    f"Is this document relevant to the query?\n"
                    f"Query: {query}\n"
                    f"Document: {doc['text'][:800]}\n"
                    f"Reply with ONLY valid JSON: {{\"relevant\": true/false, \"reason\": \"one sentence\"}}"
                ))]
                response = self.llm_grader.invoke(prompt)
                raw      = response.content.strip()

                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]

                result = json.loads(raw.strip())
                if result.get("relevant"):
                    doc["relevance_reason"] = result.get("reason", "")
                    relevant.append(doc)

            except (json.JSONDecodeError, KeyError):
                pass

        return relevant


    @traceable(name="rag.rerank", run_type="chain")
    def _rerank(self, query: str, docs: list[dict]) -> list[dict]:
        """Cross-encoder rerank via Pinecone's hosted reranker (bge-reranker-v2-m3).

        Embedding retrieval is a bi-encoder: it scores the query and each chunk
        independently, so it can rank a topically-similar chunk above the one that
        actually answers the query. A cross-encoder reads the query and chunk
        together and outputs a single joint relevance score, which is sharper.
        We rerank the retrieved chunks and reorder best-first. Falls back to the
        original order on any failure (network, model, mismatch).
        """
        if not RERANK_ENABLED or len(docs) <= 1:
            return docs
        try:
            result = self._pc.inference.rerank(
                model=RERANK_MODEL,
                query=query,
                documents=[d.get("text", "") for d in docs],
                top_n=len(docs),
            )
            reordered = []
            for item in result.data:
                doc = docs[item.index]
                doc["rerank_score"] = item.score
                reordered.append(doc)
            return reordered
        except Exception:
            return docs


    def _web_search_fallback(self, query: str, namespace: str) -> list[dict]:
        tavily_key = os.getenv("TAVILY_API_KEY")
        if not tavily_key:
            return []

        try:
            try:
                from langchain_tavily import TavilySearch
                tool    = TavilySearch(max_results=3, tavily_api_key=tavily_key)
            except ImportError:
                from langchain_community.tools.tavily_search import TavilySearchResults
                tool    = TavilySearchResults(max_results=3, tavily_api_key=tavily_key)
            results = tool.invoke({"query": query})

            docs = []
            for r in results:
                text   = r.get("content", "")
                source = r.get("url", "web search")
                if text:
                    docs.append({
                        "id":     f"web_{hashlib.md5(text.encode()).hexdigest()[:8]}",
                        "score":  0.0,
                        "text":   text,
                        "source": source,
                        "metadata": {"source": source, "text": text},
                    })
                    self._index_text(text, namespace, {"source": source})

            return docs

        except Exception:
            return []


    @traceable(name="agentic_rag.query", run_type="chain")
    def query(
        self,
        query: str,
        namespace: str,
        user_id: str = "",
        allow_web_fallback: bool = True,
    ) -> RAGResult:
        """Retrieve grounded context for a query.

        allow_web_fallback: when the knowledge base has nothing relevant, fall
        back to a web search. Appropriate for public data (e.g. salary bands),
        but should be False for proprietary lookups (e.g. a company's hiring
        rubric), where generic web results would be misleading.
        """
        if user_id:
            namespace = tenant_namespace(user_id, namespace)
        steps = ["decide"]

        if not self._should_retrieve(query):
            return RAGResult(context="", steps_taken=["decide -> skip retrieval"])

        relevant_docs: list[dict] = []

        for attempt in range(1, MAX_RETRIEVAL_ATTEMPTS + 1):
            steps.append(f"rewrite (attempt {attempt})")
            rewritten = self._rewrite_query(query, attempt=attempt)

            steps.append(f"retrieve (attempt {attempt})")
            raw_docs = self._retrieve(rewritten, namespace)

            steps.append(f"rerank (attempt {attempt})")
            raw_docs = self._rerank(query, raw_docs)[:TOP_K]

            steps.append(f"grade (attempt {attempt})")
            relevant_docs = self._grade_docs(query, raw_docs)

            if len(relevant_docs) >= MIN_RELEVANT_DOCS:
                break

        warning = None
        if len(relevant_docs) < MIN_RELEVANT_DOCS:
            if not allow_web_fallback:
                warning = (
                    f"No relevant documents found in namespace '{namespace}' "
                    f"(web fallback disabled for this query)."
                )
                return RAGResult(context="", warning=warning, steps_taken=steps)

            steps.append("fallback -> web search")
            fallback_docs = self._web_search_fallback(query, namespace)

            # Grade web results too - Tavily ranking is not relevance for our query.
            steps.append("grade fallback")
            fallback_docs = self._grade_docs(query, fallback_docs)

            if fallback_docs:
                relevant_docs = fallback_docs
            else:
                warning = (
                    f"No relevant documents found in namespace '{namespace}' "
                    f"and web search {'returned nothing relevant' if os.getenv('TAVILY_API_KEY') else 'unavailable (TAVILY_API_KEY not set)'}."
                )
                return RAGResult(context="", warning=warning, steps_taken=steps)

        context = _build_context(relevant_docs)
        sources = list({doc["source"] for doc in relevant_docs})

        return RAGResult(context=context, sources=sources, warning=warning, steps_taken=steps)


    def index_market_data(self, text: str, metadata: dict, user_id: str = "") -> int:
        ns = tenant_namespace(user_id, "market_data") if user_id else "market_data"
        meta = {"type": "market_data", "tenant": get_tenant_id(user_id) if user_id else "", **metadata}
        return self._index_text(text, ns, meta)

    def index_company_rubrics(self, text: str, metadata: dict, user_id: str = "") -> int:
        ns = tenant_namespace(user_id, "company_rubrics") if user_id else "company_rubrics"
        meta = {"type": "company_rubrics", "tenant": get_tenant_id(user_id) if user_id else "", **metadata}
        return self._index_text(text, ns, meta)

    def _index_text(self, text: str, namespace: str, metadata: dict) -> int:
        chunks    = _chunk_text(text)
        upserted  = 0
        for i, chunk in enumerate(chunks):
            self._index_single_chunk(chunk, namespace, metadata, chunk_index=i)
            upserted += 1
        return upserted

    def _index_single_chunk(
        self,
        text: str,
        namespace: str,
        metadata: dict,
        chunk_index: int = 0,
    ) -> None:
        if not text.strip():
            return

        vector_id = _make_id(text, namespace, chunk_index)
        embedding = self.embeddings.embed_query(text)

        self._index.upsert(
            vectors=[{
                "id":       vector_id,
                "values":   embedding,
                "metadata": {**metadata, "text": text[:1000]},
            }],
            namespace=namespace,
        )


def _chunk_text(text: str) -> list[str]:
    words  = text.split()
    chunks = []
    start  = 0
    while start < len(words):
        end   = start + CHUNK_SIZE
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk)
        start = end - CHUNK_OVERLAP
    return chunks


def _make_id(text: str, namespace: str, chunk_index: int) -> str:
    content_hash = hashlib.md5(text.encode()).hexdigest()[:12]
    return f"{namespace}_{content_hash}_{chunk_index}"


def _build_context(docs: list[dict]) -> str:
    parts = []
    for i, doc in enumerate(docs, 1):
        source = doc.get("source", "unknown")
        text   = doc.get("text", "").strip()
        parts.append(f"[Source {i}: {source}]\n{text}")
    return "\n\n---\n\n".join(parts)


rag = AgenticRAG()
