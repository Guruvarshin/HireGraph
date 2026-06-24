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

## Latest results

```
Recall@5:        1.000
Precision@5:     0.200   (= 1/5 ceiling; each query has one relevant doc)
MRR (raw):       0.833
MRR (+ reranker):1.000
Faithfulness/5:  5.00
Answer relev./5: 5.00
```

The reranker fixed both near-miss queries (relevant doc moved from rank 2 to
rank 1): "salary band for a senior engineer" promoted the US-comp chunk over the
senior-*definition* chunk, and "score for a mid level engineer" promoted the mid
chunk over the junior chunk. MRR went 0.833 -> 1.000.
