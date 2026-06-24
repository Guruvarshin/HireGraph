"""End-to-end RAG evaluation.

Indexes the labeled corpus into a temporary Pinecone namespace, then measures:
  Retrieval  - recall@k, precision@k, MRR vs the ground-truth relevant ids
  Generation - faithfulness (is the answer grounded in retrieved context?) and
               answer relevance (does the answer address the query?), scored 1-5
               by an LLM judge (the same LLM-as-judge idea used in the app's grader)

Run:  python eval/run_eval.py
Needs OPENAI_API_KEY and PINECONE_API_KEY / PINECONE_INDEX_NAME in the env.
Cleans up its test namespace at the end.
"""

from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dataset import CORPUS, QUERIES
from metrics import recall_at_k, precision_at_k, reciprocal_rank

load_dotenv()

TOP_K          = 5
EMBED_MODEL    = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
JUDGE_MODEL    = os.getenv("OPENAI_GRADER_MODEL", "gpt-4o-mini")
ANSWER_MODEL   = os.getenv("OPENAI_AGENT_MODEL", "gpt-4o")
TEST_NAMESPACE = "__eval_rag_test__"

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_pc     = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
_index  = _pc.Index(os.getenv("PINECONE_INDEX_NAME"))


def embed(texts: list[str]) -> list[list[float]]:
    resp = _client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def index_corpus() -> None:
    ids   = list(CORPUS.keys())
    vecs  = embed([CORPUS[i] for i in ids])
    items = [
        {"id": i, "values": v, "metadata": {"text": CORPUS[i]}}
        for i, v in zip(ids, vecs)
    ]
    _index.upsert(vectors=items, namespace=TEST_NAMESPACE)


def retrieve(query: str, k: int = TOP_K) -> list[dict]:
    qvec = embed([query])[0]
    res  = _index.query(vector=qvec, top_k=k, namespace=TEST_NAMESPACE, include_metadata=True)
    return [{"id": m.id, "score": m.score, "text": m.metadata.get("text", "")} for m in res.matches]


RERANK_MODEL = "bge-reranker-v2-m3"   # Pinecone-hosted cross-encoder


def rerank(query: str, docs: list[dict]) -> list[dict]:
    """Cross-encoder rerank via Pinecone inference (same as AgenticRAG._rerank)."""
    if len(docs) <= 1:
        return docs
    try:
        result = _pc.inference.rerank(
            model=RERANK_MODEL, query=query,
            documents=[d["text"] for d in docs], top_n=len(docs),
        )
        return [docs[item.index] for item in result.data]
    except Exception:
        return docs


def _judge(system: str, user: str) -> int:
    """Ask the judge for a 1-5 integer score; return it (defaults to 1 on parse error)."""
    resp = _client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    try:
        return int(json.loads(resp.choices[0].message.content).get("score", 1))
    except Exception:
        return 1


def answer(query: str, context: str) -> str:
    resp = _client.chat.completions.create(
        model=ANSWER_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": "Answer the question using ONLY the provided context. "
                                          "If the context does not contain the answer, say you don't know."},
            {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {query}"},
        ],
    )
    return resp.choices[0].message.content.strip()


_FAITHFUL_SYS = ('Rate how well the ANSWER is supported by the CONTEXT (faithfulness/groundedness). '
                 '5 = every claim is supported; 1 = the answer contradicts or invents facts not in context. '
                 'Return ONLY JSON: {"score": 1-5}.')
_RELEVANCE_SYS = ('Rate how well the ANSWER addresses the QUESTION (answer relevance). '
                  '5 = directly and fully answers it; 1 = off-topic or non-answer. '
                  'Return ONLY JSON: {"score": 1-5}.')


def main() -> int:
    print("Indexing labeled corpus into temporary namespace...")
    index_corpus()
    # Pinecone serverless upserts are near-immediate but allow a beat for consistency.
    import time; time.sleep(3)

    rec, prec, rr, rr_rr = [], [], [], []
    faith, relev  = [], []
    rows = []

    for item in QUERIES:
        q, gold = item["query"], item["relevant"]
        docs = retrieve(q, TOP_K)
        retrieved_ids = [d["id"] for d in docs]

        # Reranked order (cross-relevance) for comparison.
        reranked_ids = [d["id"] for d in rerank(q, list(docs))]

        r  = recall_at_k(retrieved_ids, gold, TOP_K)
        p  = precision_at_k(retrieved_ids, gold, TOP_K)
        mr = reciprocal_rank(retrieved_ids, gold)
        mr_re = reciprocal_rank(reranked_ids, gold)
        rec.append(r); prec.append(p); rr.append(mr); rr_rr.append(mr_re)

        # Generation is judged on the reranked (best-first) context, as the app serves it.
        reranked_docs = rerank(q, list(docs))
        context = "\n\n".join(d["text"] for d in reranked_docs)
        ans = answer(q, context)
        f = _judge(_FAITHFUL_SYS,  f"CONTEXT:\n{context}\n\nANSWER:\n{ans}")
        v = _judge(_RELEVANCE_SYS, f"QUESTION:\n{q}\n\nANSWER:\n{ans}")
        faith.append(f); relev.append(v)

        rows.append((q[:42], retrieved_ids[:3], reranked_ids[:3], sorted(gold), round(mr, 2), round(mr_re, 2), f, v))

    print("\n=== Per-query results ===")
    print(f"{'query':<44}{'top3 raw':<22}{'top3 reranked':<22}{'gold':<8}{'rr':<6}{'rr+rerank':<11}{'faith':<7}{'relev'}")
    for q, raw3, re3, gold, mr, mr_re, f, v in rows:
        print(f"{q:<44}{str(raw3):<22}{str(re3):<22}{str(gold):<8}{mr:<6}{mr_re:<11}{f:<7}{v}")

    n = len(QUERIES)
    print("\n=== Aggregate (mean over queries) ===")
    print(f"Recall@{TOP_K}:           {sum(rec)/n:.3f}")
    print(f"Precision@{TOP_K}:        {sum(prec)/n:.3f}")
    print(f"MRR (raw):           {sum(rr)/n:.3f}")
    print(f"MRR (+ reranker):    {sum(rr_rr)/n:.3f}")
    print(f"Faithfulness/5:      {sum(faith)/n:.2f}")
    print(f"Answer relev./5:     {sum(relev)/n:.2f}")

    print("\nCleaning up test namespace...")
    try:
        _index.delete(delete_all=True, namespace=TEST_NAMESPACE)
    except Exception as exc:
        print(f"(cleanup warning: {exc})")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
