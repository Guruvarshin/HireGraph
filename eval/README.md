# RAG Evaluation

Measures the retrieval and generation quality of the RAG layer against a labeled dataset.

## Run

```bash
python eval/run_eval.py
```

Requires `OPENAI_API_KEY`, `PINECONE_API_KEY`, and `PINECONE_INDEX_NAME` in the environment (read from `.env`). It indexes a small labeled corpus into a temporary Pinecone namespace (`__eval_rag_test__`) and deletes it when finished, so your real rubric data is untouched.

## What it measures

Retrieval (vs ground-truth relevant ids in `dataset.py`):
- **Recall@k** - did the relevant chunk appear in the top k?
- **Precision@k** - fraction of the top k that are relevant. With one relevant doc per query the ceiling is `1/k`, so read MRR for ranking quality.
- **MRR** - mean reciprocal rank of the first relevant chunk (1.0 = always rank 1).

Generation (LLM-as-judge, scored 1-5):
- **Faithfulness/groundedness** - is the answer supported by the retrieved context?
- **Answer relevance** - does the answer address the question?

## Files

- `dataset.py` - the labeled corpus and queries with ground-truth relevant ids.
- `metrics.py` - pure recall@k / precision@k / MRR functions.
- `run_eval.py` - indexes, retrieves, judges, prints the report, cleans up.

## Reranker

After retrieval, the top-k chunks are reordered by a **cross-encoder reranker**
(`bge-reranker-v2-m3`, served by Pinecone's hosted inference API - no extra key
or local model). An embedding (bi-encoder) scores the query and each chunk
independently, so it can rank a topically-similar chunk above the one that
actually answers the query. A cross-encoder reads query and chunk together and
returns a single joint relevance score, which corrects that ordering. The same
reranker runs in the app at `AgenticRAG._rerank`.

## Dataset

27 rubric chunks and 20 queries tagged by failure mode (`dataset.py`):
single, distractor (definition vs fact), multi-relevant, paraphrase, exact-term,
and negative (out-of-domain that must be rejected, not answered).

## Pipeline

Retrieve wide (top_k=12) -> cross-encoder rerank -> narrow to top 5 -> grade.
Over-fetching then reranking lets the cross-encoder pull truly-relevant chunks
that the embedding ranked at positions 6-12 into the final top 5, so the
reranker improves recall, not just ordering.

## Latest results (by failure mode), recall shown as raw -> after rerank

```
single      recall@5 0.60->1.00  prec@5=0.20  MRR 0.33->1.00  faith=5.0  relev=5.0
distractor  recall@5 1.00->1.00  prec@5=0.20  MRR 0.60->1.00  faith=5.0  relev=5.0
multi       recall@5 0.83->0.92  prec@5=0.60  MRR 1.00->1.00  faith=5.0  relev=5.0
paraphrase  recall@5 1.00->1.00  prec@5=0.20  MRR 1.00->1.00  faith=2.3  relev=3.7
exact       recall@5 1.00->1.00  prec@5=0.20  MRR 1.00->1.00  faith=5.0  relev=5.0
negative    correct rejection=100%   answer abstained=100%

Overall (answerable): Recall@5 0.833 raw -> 0.979 reranked | MRR 0.742 -> 1.000
                      Faithfulness 4.50 | Answer relevance 4.75
Out-of-domain:        100% rejection, 100% abstention (no hallucination)
```

## What the eval surfaced, and the fixes applied

- The cross-encoder reranker lifts both ranking (MRR 0.742 -> 1.000) and recall
  (0.833 -> 0.979): with retrieve-wide/rerank-narrow it recovers relevant chunks
  the embedding alone left outside the top 5 (e.g. it ranked the senior salary
  band below the senior *definition*, and the reranker pulled it to rank 1).
- Out-of-domain handling is perfect: every negative is rejected and the answer
  abstains - no fabrication, and this held after the generation prompt was
  loosened (the key risk).
- Two weaknesses found in the first run, and the fixes:
  1. Multi-relevant recall was capped at 0.83 by top_k=5. Fix: retrieve wide
     (12) and rerank down to 5, raising multi recall to 0.92 and overall recall
     to 0.979.
  2. Over-abstention on paraphrase (faith/relev 2.3): retrieval was correct but
     the strict "answer only from context" prompt made the answerer say "I don't
     know" when wording differed (career break vs employment gap). Fix: allow
     synonym/paraphrase bridging in the answer prompt while still abstaining on
     genuinely-absent info; paraphrase relevance recovered 2.3 -> 3.7 and
     negatives stayed at 100% abstention.
