"""End-to-end RAG evaluation across failure modes, with a held-out test split.

Indexes the labeled corpus into a temporary Pinecone namespace, then measures:

  Retrieval (answerable queries)
    - recall@k, precision@k (order-independent within top-k)
    - MRR, raw vs after the cross-encoder reranker
    - the rerank DELTA with a paired bootstrap CI (does reranking actually help?)

  Rejection (out-of-domain queries)
    - did the relevance grader correctly return ZERO relevant chunks?
    - did the generated answer abstain ("I don't know")?

  Generation (answerable queries)
    - faithfulness/groundedness and answer relevance, 1-5 via LLM judge

METHODOLOGY
  - Config (TOP_K / RETRIEVE_K) is imported from the app so the eval can never
    drift from what production actually runs.
  - Queries are split DEV/TEST, stratified by failure mode with a fixed seed.
    Tune on DEV. Report TEST once, with the config frozen. Never tune on TEST.
  - All aggregates carry a 95% bootstrap CI. A delta without a CI is not a result.
  - See dataset.py: this is a SYNTHETIC, self-authored benchmark. It is a
    regression test, not evidence of real-world generalization.

Run:  python eval/run_eval.py            (reports TEST split)
      python eval/run_eval.py --dev      (reports DEV split, for tuning)
      python eval/run_eval.py --all      (reports both + full set)
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))          # repo root, so `memory` imports
from dataset import CORPUS, QUERIES
from metrics import recall_at_k, precision_at_k, reciprocal_rank

load_dotenv()

# Import the REAL config from the app so eval and production can't drift apart.
from memory.agentic_rag import TOP_K, RETRIEVE_K   # noqa: E402

EMBED_MODEL    = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
JUDGE_MODEL    = os.getenv("OPENAI_GRADER_MODEL", "gpt-4o-mini")
ANSWER_MODEL   = os.getenv("OPENAI_AGENT_MODEL", "gpt-4o")
RERANK_MODEL   = "bge-reranker-v2-m3"
TEST_NAMESPACE = "__eval_rag_test__"

SPLIT_SEED     = 42
TEST_FRACTION  = 0.5
BOOTSTRAP_N    = 2000
MAX_WORKERS    = 8

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_pc     = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
_index  = _pc.Index(os.getenv("PINECONE_INDEX_NAME"))

ANSWERABLE = ["single", "distractor", "multi", "paraphrase", "exact"]


# ---------------------------------------------------------------- split ----
def split_queries() -> tuple[list[dict], list[dict]]:
    """Stratified dev/test split, seeded so it is stable across runs."""
    rng = random.Random(SPLIT_SEED)
    by_type: dict[str, list[dict]] = defaultdict(list)
    for q in QUERIES:
        by_type[q["type"]].append(q)
    dev, test = [], []
    for typ in sorted(by_type):
        items = sorted(by_type[typ], key=lambda x: x["query"])
        rng.shuffle(items)
        cut = int(len(items) * TEST_FRACTION)
        test.extend(items[:cut])
        dev.extend(items[cut:])
    return dev, test


# ------------------------------------------------------------ primitives ----
def embed(texts: list[str]) -> list[list[float]]:
    return [d.embedding for d in _client.embeddings.create(model=EMBED_MODEL, input=texts).data]


def index_corpus() -> None:
    ids  = list(CORPUS.keys())
    vecs = embed([CORPUS[i] for i in ids])
    _index.upsert(
        vectors=[{"id": i, "values": v, "metadata": {"text": CORPUS[i]}} for i, v in zip(ids, vecs)],
        namespace=TEST_NAMESPACE,
    )


def retrieve(query: str, k: int) -> list[dict]:
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


# ------------------------------------------------------------ statistics ----
def mean(xs) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def bootstrap_ci(xs: list[float], n: int = BOOTSTRAP_N, seed: int = 0) -> tuple[float, float]:
    """95% percentile bootstrap CI for the mean."""
    if not xs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    k = len(xs)
    means = []
    for _ in range(n):
        means.append(mean([xs[rng.randrange(k)] for _ in range(k)]))
    means.sort()
    return (means[int(0.025 * n)], means[int(0.975 * n)])


def paired_bootstrap_ci(a: list[float], b: list[float], n: int = BOOTSTRAP_N,
                        seed: int = 0) -> tuple[float, float]:
    """95% CI on the PAIRED delta (b - a). Resamples query indices, not values,
    so the two conditions stay paired on the same query."""
    if not a or len(a) != len(b):
        return (0.0, 0.0)
    rng = random.Random(seed)
    k = len(a)
    diffs = []
    for _ in range(n):
        idx = [rng.randrange(k) for _ in range(k)]
        diffs.append(mean([b[i] for i in idx]) - mean([a[i] for i in idx]))
    diffs.sort()
    return (diffs[int(0.025 * n)], diffs[int(0.975 * n)])


def fmt(v: float, lo: float, hi: float, p: int = 3) -> str:
    return f"{v:.{p}f}  [{lo:.{p}f}, {hi:.{p}f}]"


# -------------------------------------------------------------- pipeline ----
def evaluate_one(item: dict) -> dict:
    q, gold, typ = item["query"], item["relevant"], item["type"]
    pool     = retrieve(q, RETRIEVE_K)
    raw_ids  = [d["id"] for d in pool[:TOP_K]]        # what plain top-k would give
    reranked = rerank(q, list(pool))[:TOP_K]          # over-fetch + rerank + narrow
    rer_ids  = [d["id"] for d in reranked]
    graded   = grade(q, reranked)
    ctx      = "\n\n".join(d["text"] for d in reranked)
    ans      = answer(q, ctx)

    if typ == "negative":
        return {"type": typ, "query": q,
                "reject": 1 if len(graded) == 0 else 0,
                "abstain": 1 if _abstained(ans) else 0}

    return {
        "type": typ, "query": q,
        "recall_raw": recall_at_k(raw_ids, gold, TOP_K),
        "recall":     recall_at_k(rer_ids, gold, TOP_K),
        "prec":       precision_at_k(rer_ids, gold, TOP_K),
        "mrr_raw":    reciprocal_rank(raw_ids, gold),
        "mrr_re":     reciprocal_rank(rer_ids, gold),
        "faith":      _judge(_FAITHFUL_SYS,  f"CONTEXT:\n{ctx}\n\nANSWER:\n{ans}"),
        "relev":      _judge(_RELEVANCE_SYS, f"QUESTION:\n{q}\n\nANSWER:\n{ans}"),
    }


def report(name: str, results: list[dict]) -> None:
    ans_rows = [r for r in results if r["type"] in ANSWERABLE]
    neg_rows = [r for r in results if r["type"] == "negative"]

    print(f"\n{'='*72}\n  {name}   (n={len(results)}: {len(ans_rows)} answerable, {len(neg_rows)} out-of-domain)\n{'='*72}")

    print("\n--- By failure mode ---")
    print(f"{'mode':<12}{'n':<5}{'recall@5 raw->rerank':<24}{'prec@5':<9}{'MRR raw->re':<16}{'faith':<7}{'relev'}")
    for typ in ANSWERABLE:
        rows = [r for r in ans_rows if r["type"] == typ]
        if not rows:
            continue
        print(f"{typ:<12}{len(rows):<5}"
              f"{mean([r['recall_raw'] for r in rows]):.3f} -> {mean([r['recall'] for r in rows]):.3f}      "
              f"{mean([r['prec'] for r in rows]):.3f}    "
              f"{mean([r['mrr_raw'] for r in rows]):.3f} -> {mean([r['mrr_re'] for r in rows]):.3f}    "
              f"{mean([r['faith'] for r in rows]):.2f}   {mean([r['relev'] for r in rows]):.2f}")

    if not ans_rows:
        return
    rec_raw = [r["recall_raw"] for r in ans_rows]
    rec_re  = [r["recall"]     for r in ans_rows]
    mrr_raw = [r["mrr_raw"]    for r in ans_rows]
    mrr_re  = [r["mrr_re"]     for r in ans_rows]
    prec    = [r["prec"]       for r in ans_rows]
    faith   = [r["faith"]      for r in ans_rows]
    relev   = [r["relev"]      for r in ans_rows]

    print(f"\n--- Overall (answerable, n={len(ans_rows)}) — mean [95% bootstrap CI] ---")
    print(f"Recall@5 (raw):      {fmt(mean(rec_raw), *bootstrap_ci(rec_raw))}")
    print(f"Recall@5 (+rerank):  {fmt(mean(rec_re),  *bootstrap_ci(rec_re))}")
    d_lo, d_hi = paired_bootstrap_ci(rec_raw, rec_re)
    d = mean(rec_re) - mean(rec_raw)
    sig = "SIGNIFICANT" if d_lo > 0 else ("no effect (CI spans 0)" if d_hi > 0 else "NEGATIVE")
    print(f"  -> rerank delta:   {fmt(d, d_lo, d_hi)}   {sig}")
    print(f"Precision@5:         {fmt(mean(prec), *bootstrap_ci(prec))}")
    print(f"MRR (raw):           {fmt(mean(mrr_raw), *bootstrap_ci(mrr_raw))}")
    print(f"MRR (+rerank):       {fmt(mean(mrr_re),  *bootstrap_ci(mrr_re))}")
    m_lo, m_hi = paired_bootstrap_ci(mrr_raw, mrr_re)
    md = mean(mrr_re) - mean(mrr_raw)
    msig = "SIGNIFICANT" if m_lo > 0 else ("no effect (CI spans 0)" if m_hi > 0 else "NEGATIVE")
    print(f"  -> MRR delta:      {fmt(md, m_lo, m_hi)}   {msig}")
    print(f"Faithfulness/5:      {fmt(mean(faith), *bootstrap_ci(faith), p=2)}")
    print(f"Answer relevance/5:  {fmt(mean(relev), *bootstrap_ci(relev), p=2)}")

    if neg_rows:
        rej = [r["reject"] for r in neg_rows]
        abst = [r["abstain"] for r in neg_rows]
        print(f"\n--- Out-of-domain (n={len(neg_rows)}) ---")
        print(f"Correct rejection:   {fmt(mean(rej), *bootstrap_ci(rej), p=2)}")
        print(f"Answer abstained:    {fmt(mean(abst), *bootstrap_ci(abst), p=2)}")
        leaked = [r["query"] for r in neg_rows if not r["abstain"]]
        if leaked:
            print(f"  hallucinated on:   {leaked}")


def main() -> int:
    which = "test"
    if "--dev" in sys.argv: which = "dev"
    if "--all" in sys.argv: which = "all"

    dev, test = split_queries()
    print(f"Config from app: TOP_K={TOP_K}, RETRIEVE_K={RETRIEVE_K}")
    print(f"Split (seed={SPLIT_SEED}): dev n={len(dev)}, test n={len(test)}")
    print("Indexing labeled corpus into temporary namespace...")
    index_corpus()
    time.sleep(3)

    targets = {"dev": [("DEV split (for tuning)", dev)],
               "test": [("TEST split (held out — report this)", test)],
               "all": [("DEV split (for tuning)", dev),
                       ("TEST split (held out — report this)", test),
                       ("FULL set (all 200)", QUERIES)]}[which]

    try:
        for name, items in targets:
            print(f"\nRunning {len(items)} queries ({MAX_WORKERS} workers)...")
            t0 = time.time()
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                results = list(ex.map(evaluate_one, items))
            print(f"  ...done in {time.time()-t0:.0f}s")
            report(name, results)
    finally:
        print("\nCleaning up test namespace...")
        try:
            _index.delete(delete_all=True, namespace=TEST_NAMESPACE)
        except Exception as exc:
            print(f"(cleanup warning: {exc})")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
