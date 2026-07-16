# RAG Evaluation

Measures retrieval and generation quality of the RAG layer against a labeled dataset,
with a held-out test split and bootstrap confidence intervals.

## Run

```bash
python eval/run_eval.py          # reports the held-out TEST split (the number to quote)
python eval/run_eval.py --dev    # DEV split - use this while tuning
python eval/run_eval.py --all    # dev + test + full set
```

Requires `OPENAI_API_KEY`, `PINECONE_API_KEY`, and `PINECONE_INDEX_NAME` in the
environment (read from `.env`). It indexes the labeled corpus into a temporary
Pinecone namespace (`__eval_rag_test__`) and deletes it when finished, so real
rubric data is untouched. A full `--all` run is ~1,400 API calls / ~5 minutes.

## Dataset

`dataset.py`: **60 rubric chunks, 200 queries**, each tagged by failure mode.

| Mode | n | What it tests |
|---|---|---|
| `single` | 60 | plain single-fact lookup |
| `distractor` | 35 | near-duplicate neighbours exist (same fact across India/USA/UK, adjacent levels) |
| `multi` | 30 | several gold chunks for one query |
| `paraphrase` | 30 | natural wording with no lexical overlap with the chunk |
| `exact` | 25 | a specific technical term dense retrieval can miss |
| `negative` | 20 | **not in the corpus** - must reject and abstain, not fabricate |

The corpus deliberately contains near-duplicate distractors so that "senior salary
in India" has several plausible-but-wrong neighbours. That is what makes the
reranker's contribution measurable rather than trivial.

## Methodology

Three things make the numbers defensible:

1. **Config is imported from the app.** `run_eval.py` does
   `from memory.agentic_rag import TOP_K, RETRIEVE_K`, so the eval can never drift
   from what production actually runs. (It previously hardcoded `RETRIEVE_K=12`
   while the app ran 20 - the eval was not testing the real system.)
2. **Seeded, stratified dev/test split.** Queries are split 50/50 *within each
   failure mode* with a fixed seed. **Tune on dev. Report test once, config frozen.
   Never tune against test.**
3. **95% bootstrap confidence intervals on every aggregate.** Rerank deltas use a
   **paired** bootstrap (resampling query indices so the two conditions stay paired
   on the same query). A delta whose CI spans zero is reported as *no effect* - the
   harness will not call it an improvement.

## What it measures

Retrieval (vs ground-truth ids in `dataset.py`):
- **Recall@k** - what fraction of the gold chunks appeared in the top k?
- **MRR** - mean reciprocal rank of the first gold chunk (1.0 = always rank 1).
- **Precision@k** - reported but **not meaningful here**: it is mechanically capped
  (a single-gold query at k=5 maxes out at 0.2), so it measures gold-set size, not
  quality. Read MRR for ranking.

Generation (LLM-as-judge, 1-5):
- **Faithfulness** - is the answer supported by the retrieved context?
- **Answer relevance** - does the answer address the question?

Out-of-domain:
- **Rejection** - did the grader return zero relevant chunks?
- **Abstention** - did the generated answer say "I don't know"?

### The experiment design

Both arms see the **identical pool**, so the comparison is clean and paired:

```python
pool     = retrieve(q, RETRIEVE_K)          # 20 chunks ranked by the embedding
raw_ids  = pool[:TOP_K]                     # BASELINE:  embedding's own top 5
reranked = rerank(q, pool)[:TOP_K]          # TREATMENT: cross-encoder's top 5 of the same 20
```

The only variable is *who picks the final 5*. This is why a paired bootstrap is the
correct test for the delta.

## Latest results — held-out TEST split (n=99: 89 answerable, 10 out-of-domain)

```
                      mean     [95% bootstrap CI]
Recall@5 (raw)        0.968    [0.930, 0.997]
Recall@5 (+rerank)    0.985    [0.966, 1.000]
  -> rerank delta     +0.017   [-0.014, 0.056]   NO EFFECT (CI spans zero)
MRR (raw)             0.885    [0.828, 0.940]
MRR (+rerank)         0.980    [0.955, 1.000]
  -> MRR delta        +0.096   [0.047, 0.146]    SIGNIFICANT
Faithfulness/5        4.15     [3.83, 4.46]
Answer relevance/5    4.65     [4.42, 4.87]
Out-of-domain         100% rejection, 100% abstention
```

By failure mode (recall raw -> reranked):

```
single      n=30   1.000 -> 1.000   MRR 0.865 -> 1.000   faith 4.20  relev 5.00
distractor  n=17   1.000 -> 1.000   MRR 0.855 -> 0.971   faith 3.35  relev 4.12
multi       n=15   0.942 -> 0.908   MRR 0.967 -> 1.000   faith 5.00  relev 5.00
paraphrase  n=15   0.867 -> 1.000   MRR 0.783 -> 0.917   faith 4.20  relev 4.20
exact       n=12   1.000 -> 1.000   MRR 1.000 -> 1.000   faith 4.00  relev 4.67
```

The full set (n=200) replicates it: recall delta +0.005 [-0.015, 0.028] (no effect),
MRR delta +0.065 [0.031, 0.102] (significant).

## What the eval actually shows

**The reranker buys ranking, not recall.** On this corpus the recall delta's CI spans
zero. This is a **ceiling effect**: retrieving 20 of 60 chunks, the bi-encoder already
lands a gold chunk in the top 5 ~97% of the time, so there is nothing left to recover.
The over-fetch mechanism is real - it just has no headroom here. What is unambiguous
is ordering: **MRR +0.096, CI entirely above zero**.

**Where the reranker earns its place:**
- **paraphrase recall 0.867 -> 1.000** - rescues queries with no lexical overlap.
- **distractor MRR 0.782 -> 0.943** (full set) - correctly orders near-duplicate
  India/USA/UK bands. Exactly the failure a cross-encoder's joint query-chunk
  scoring is built for.

**Its measurable cost:** on multi-gold queries reranking can evict a relevant chunk
(recall 0.942 -> 0.908). Note `multi` also has a hard ceiling: a query with 6 gold
chunks can never exceed recall 5/6 = 0.83 at k=5.

**Weakest real number:** faithfulness on `distractor` queries (3.35) - answers are
less grounded when confusable neighbours sit in the context window.

## RETRACTION

A previous version of this README reported:

> `Overall (answerable): Recall@5 0.833 raw -> 0.979 reranked | MRR 0.742 -> 1.000`
> "the reranker improves recall, not just ordering"

**That claim is withdrawn.** It came from a 20-query set that was *tuned against and
then reported on* - train/test contamination. It did not replicate on a held-out
split at the app's real config. The recall claim specifically is false on this
benchmark.

The old README also documented the contamination in plain sight, as if it were good
practice: *"Two weaknesses found in the first run, and the fixes: (1) multi-relevant
recall capped at 0.83 -> fix: retrieve wide (12)... (2) over-abstention on paraphrase
-> fix: allow synonym bridging in the answer prompt."* That is the loop - look at the
eval, turn a knob, report the improved number on the same eval. No model is being
trained, but the optimizer is the developer and the parameters are the config and
prompts, so it is contamination all the same.

## Known limitations (read before quoting any number)

1. **Synthetic and self-authored.** The corpus and the queries were written by the
   same people who built the retriever, so they share lexical and structural priors
   with the chunker. **Absolute numbers are optimistic.** This is a *regression
   benchmark* - it will catch a retrieval regression - **not evidence of real-world
   generalization.**
2. **A residual prompt leak affects the generation metrics.** The answer prompt in
   `run_eval.py` hardcodes synonym pairs (`'paid leave' = 'vacation'`,
   `'employment gap' = 'career break'`, `'penalize' = 'dock points'`) that exist
   *because those specific eval queries were failing*. Two such queries land in the
   TEST split. Impact: **recall/MRR are unaffected** (the prompt runs after
   retrieval and cannot change what Pinecone returns, so the rerank findings stand),
   but **faithfulness and answer relevance are inflated.**
3. **`_abstained()` is a hand-written keyword list.** The 100% abstention figure is
   partly an artifact of extending that list until it caught every case - fitting the
   metric rather than the system.

**To make this defensible:** source queries from real usage traces (LangSmith),
have relevance labeled by someone who did not build the retrieval, remove the
eval-specific synonyms from the answer prompt, replace the keyword-matching
abstention check with a judge, and run the whole thing as a CI merge gate so a
regression fails the build.

## Files

- `dataset.py` - the labeled corpus (60 chunks) and 200 queries with ground-truth ids.
- `metrics.py` - pure recall@k / precision@k / MRR functions.
- `run_eval.py` - split, index, retrieve, rerank, grade, judge, bootstrap, report, clean up.
