"""End-to-end RAG evaluation across failure modes.

Indexes the labeled corpus into a temporary Pinecone namespace, then measures:

  Retrieval (answerable queries)
    - recall@k, precision@k (order-independent within top-k)
    - MRR, raw vs after the cross-encoder reranker

  Rejection (out-of-domain queries)
    - did the relevance grader correctly return ZERO relevant chunks?
    - did the generated answer abstain ("I don't know")?

  Generation (answerable queries)
    - faithfulness/groundedness and answer relevance, 1-5 via LLM judge

Results are broken down by failure mode. Cleans up its test namespace.

Run:  python eval/run_eval.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict

from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dataset import CORPUS, QUERIES
from metrics import recall_at_k, precision_at_k, reciprocal_rank

load_dotenv()

TOP_K          = 5
RETRIEVE_K     = 12   # over-fetch, then rerank down to TOP_K (matches the app)
EMBED_MODEL    = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
JUDGE_MODEL    = os.getenv("OPENAI_GRADER_MODEL", "gpt-4o-mini")
ANSWER_MODEL   = os.getenv("OPENAI_AGENT_MODEL", "gpt-4o")
RERANK_MODEL   = "bge-reranker-v2-m3"
TEST_NAMESPACE = "__eval_rag_test__"

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_pc     = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
_index  = _pc.Index(os.getenv("PINECONE_INDEX_NAME"))


def embed(texts: list[str]) -> list[list[float]]:
    return [d.embedding for d in _client.embeddings.create(model=EMBED_MODEL, input=texts).data]


def index_corpus() -> None:
    ids  = list(CORPUS.keys())
    vecs = embed([CORPUS[i] for i in ids])
    _index.upsert(
        vectors=[{"id": i, "values": v, "metadata": {"text": CORPUS[i]}} for i, v in zip(ids, vecs)],
        namespace=TEST_NAMESPACE,
    )


def retrieve(query: str, k: int = TOP_K) -> list[dict]:
    qvec = embed([query])[0]
    res  = _index.query(vector=qvec, top_k=k, namespace=TEST_NAMESPACE, include_metadata=True)
    return [{"id": m.id, "score": m.score, "text": m.metadata.get("text", "")} for m in res.matches]


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


def grade(query: str, docs: list[dict]) -> list[dict]:
    """LLM relevance grader (batch): keep only chunks judged relevant."""
    if not docs:
        return []
    listing = "\n".join(f"[{i}] {d['text'][:400]}" for i, d in enumerate(docs))
    resp = _client.chat.completions.create(
        model=JUDGE_MODEL, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "user", "content":
            f"Which documents are relevant to the query? Be strict.\n"
            f"Query: {query}\n\nDocuments:\n{listing}\n\n"
            f'Return ONLY JSON: {{"relevant_indices": [list of relevant [i] numbers]}}'}],
    )
    try:
        idxs = set(json.loads(resp.choices[0].message.content).get("relevant_indices", []))
        return [d for i, d in enumerate(docs) if i in idxs]
    except Exception:
        return docs


def answer(query: str, context: str) -> str:
    resp = _client.chat.completions.create(
        model=ANSWER_MODEL, temperature=0,
        messages=[
            {"role": "system", "content":
                "Answer the question using only facts stated in the context. The context may phrase "
                "things differently than the question; treat synonyms and paraphrases as matches "
                "(e.g. 'employment gap' = 'career break', 'paid leave' = 'vacation', 'penalize' = "
                "'dock points'). Only if the specific information requested is genuinely not present "
                "in the context, reply exactly: I don't know."},
            {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {query}"},
        ],
    )
    return resp.choices[0].message.content.strip()


def _judge(system: str, user: str) -> int:
    resp = _client.chat.completions.create(
        model=JUDGE_MODEL, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    try:
        return int(json.loads(resp.choices[0].message.content).get("score", 1))
    except Exception:
        return 1


_FAITHFUL_SYS = ('Rate how well the ANSWER is supported by the CONTEXT (faithfulness). '
                 '5 = every claim supported; 1 = invents/contradicts. Return ONLY JSON {"score":1-5}.')
_RELEVANCE_SYS = ('Rate how well the ANSWER addresses the QUESTION (relevance). '
                  '5 = directly answers; 1 = off-topic. Return ONLY JSON {"score":1-5}.')


def _abstained(ans: str) -> bool:
    a = ans.lower()
    return any(p in a for p in ["i don't know", "i do not know", "not contain", "no information",
                                "not provided", "cannot find", "isn't in", "is not in"])


def main() -> int:
    print("Indexing labeled corpus into temporary namespace...")
    index_corpus()
    time.sleep(3)

    by_type: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    rows = []

    for item in QUERIES:
        q, gold, typ = item["query"], item["relevant"], item["type"]
        # Retrieve wide, rerank, narrow to TOP_K (matches AgenticRAG).
        pool = retrieve(q, RETRIEVE_K)
        raw_ids = [d["id"] for d in pool[:TOP_K]]            # what plain top-k would have given
        reranked = rerank(q, list(pool))[:TOP_K]            # over-fetch + rerank + narrow
        rer_ids = [d["id"] for d in reranked]
        graded = grade(q, reranked)

        if typ == "negative":
            rejected = (len(graded) == 0)
            ans = answer(q, "\n\n".join(d["text"] for d in reranked))
            abstained = _abstained(ans)
            by_type[typ]["reject"].append(1 if rejected else 0)
            by_type[typ]["abstain"].append(1 if abstained else 0)
            rows.append((typ, q[:40], "-", "-", "-", "rej" if rejected else "KEPT", "abs" if abstained else "ANS"))
        else:
            rec_raw = recall_at_k(raw_ids, gold, TOP_K)
            rec     = recall_at_k(rer_ids, gold, TOP_K)   # final (over-fetch + rerank + narrow)
            prec    = precision_at_k(rer_ids, gold, TOP_K)
            mrr_r   = reciprocal_rank(raw_ids, gold)
            mrr_e   = reciprocal_rank(rer_ids, gold)
            ctx   = "\n\n".join(d["text"] for d in reranked)
            ans   = answer(q, ctx)
            f = _judge(_FAITHFUL_SYS,  f"CONTEXT:\n{ctx}\n\nANSWER:\n{ans}")
            v = _judge(_RELEVANCE_SYS, f"QUESTION:\n{q}\n\nANSWER:\n{ans}")
            for k, val in [("recall_raw", rec_raw), ("recall", rec), ("prec", prec),
                           ("mrr_raw", mrr_r), ("mrr_re", mrr_e), ("faith", f), ("relev", v)]:
                by_type[typ][k].append(val)
            rows.append((typ, q[:40], round(rec, 2), round(prec, 2), f"{mrr_r:.2f}>{mrr_e:.2f}", f, v))

    # --- per-query table ---
    print("\n=== Per-query ===")
    print(f"{'type':<11}{'query':<42}{'rec':<6}{'prec':<6}{'mrr raw>re':<12}{'faith/reject':<14}{'relev/abstain'}")
    for typ, q, rec, prec, mrr, a, b in rows:
        print(f"{typ:<11}{q:<42}{str(rec):<6}{str(prec):<6}{str(mrr):<12}{str(a):<14}{b}")

    # --- per-failure-mode aggregates ---
    def mean(xs): return sum(xs) / len(xs) if xs else 0.0
    print("\n=== By failure mode ===")
    for typ in ["single", "distractor", "multi", "paraphrase", "exact"]:
        d = by_type[typ]
        if not d: continue
        print(f"{typ:<11} recall@5 {mean(d['recall_raw']):.2f}->{mean(d['recall']):.2f}  "
              f"prec@5={mean(d['prec']):.2f}  MRR {mean(d['mrr_raw']):.2f}->{mean(d['mrr_re']):.2f}  "
              f"faith={mean(d['faith']):.1f}  relev={mean(d['relev']):.1f}")
    neg = by_type["negative"]
    if neg:
        print(f"{'negative':<11} correct rejection={mean(neg['reject'])*100:.0f}%  "
              f"answer abstained={mean(neg['abstain'])*100:.0f}%")

    # --- overall (answerable) ---
    ans_types = ["single", "distractor", "multi", "paraphrase", "exact"]
    allrr = [x for t in ans_types for x in by_type[t]["recall_raw"]]
    allr  = [x for t in ans_types for x in by_type[t]["recall"]]
    allp  = [x for t in ans_types for x in by_type[t]["prec"]]
    allmr = [x for t in ans_types for x in by_type[t]["mrr_raw"]]
    allme = [x for t in ans_types for x in by_type[t]["mrr_re"]]
    allf  = [x for t in ans_types for x in by_type[t]["faith"]]
    allv  = [x for t in ans_types for x in by_type[t]["relev"]]
    print("\n=== Overall (answerable queries) ===")
    print(f"Recall@5 (raw):     {mean(allrr):.3f}")
    print(f"Recall@5 (+rerank): {mean(allr):.3f}")
    print(f"Precision@5:        {mean(allp):.3f}")
    print(f"MRR (raw):          {mean(allmr):.3f}")
    print(f"MRR (+ reranker):   {mean(allme):.3f}")
    print(f"Faithfulness/5:     {mean(allf):.2f}")
    print(f"Answer relevance/5: {mean(allv):.2f}")
    print(f"\nNegative rejection: {mean(neg['reject'])*100:.0f}%   abstention: {mean(neg['abstain'])*100:.0f}%")

    print("\nCleaning up test namespace...")
    try:
        _index.delete(delete_all=True, namespace=TEST_NAMESPACE)
    except Exception as exc:
        print(f"(cleanup warning: {exc})")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
