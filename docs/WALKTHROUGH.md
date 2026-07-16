# HireGraph - Live Walkthrough Script

Glance at this during the screen share. Goal: make it clear how the whole pipeline works inside, using the live app + the LangSmith trace tree.

---

## Pre-call checklist (do 30 min before)
- [ ] Wake the Railway backend (free tier sleeps ~40s). Open the live app and do one full run.
- [ ] Have a known-good JD + 2-3 resumes ready to upload (do NOT improvise inputs).
- [ ] Tabs open: live app, GitHub repo, editor (`graph/pipeline.py`, `memory/agentic_rag.py`, `eval/run_eval.py`, `utils/guardrails.py`), terminal, LangSmith project.
- [ ] Run one clean pipeline so a fresh, complete trace is ready to open.
- [ ] `python eval/run_eval.py` ready to run live.
- [ ] Close notifications, bump editor font, one clean browser window.

---

## The 30-minute arc

**0-2 min - Frame it (say this):**
> "HireGraph is a multi-agent recruiting pipeline: five LLM agents that screen resumes, plan interviews, and draft offers, orchestrated as a LangGraph state machine with human approval gates. The hard parts aren't the LLM calls, they're the systems around them: durable state so a run pauses for days and resumes, an agentic RAG layer that grounds every decision in the company's own rubric, multi-tenant isolation, and an eval harness so I know it works instead of hoping. It's deployed and live."

**2-7 min - Live demo:** upload JD + resumes -> show shortlist with 4-dimension scores + bias flags -> show the human-in-the-loop pause at shortlist review. If time: upload a resume with an injection line -> show it flagged, not processed.

**7-16 min - LangSmith trace drill-down (see next section).**

**16-18 min - AI-first process (this is what they're buying):**
> "How I built this matters as much as what it is. I work plan-first with Claude Code and treat the AI as a junior engineer whose output I review, not autocomplete. Two examples: it first wrote me a reranker that was an LLM cosplaying as a cross-encoder, half the function was parsing its own messy output. I rejected it and used a real cross-encoder. And on the resume injection defense, a review comment reframed it: 'if injection is detected, don't call the AI at all.' I catch the model's over-engineering and its blind spots."

**18-30 min - Follow-ups** (let him drive; answers in the cheatsheet).

---

## LangSmith trace drill-down (the core of the demo)

Open the trace collapsed to the top level, then drill down. Span -> what you say:

```
Pipeline run
├─ Agent 1: JD Parser
├─ Agent 2: Resume Screener
│   ├─ agentic_rag.query
│   │   ├─ rag.rewrite_query
│   │   ├─ rag.pinecone_retrieve
│   │   ├─ rag.rerank
│   │   └─ rag.grade_docs
│   └─ Score candidate  (one per candidate)
├─ Agent 3: Interview Planner
├─ Agent 4: Interview Evaluator
└─ Agent 5: Offer Drafter
```

1. **Top level (Agents 1-5):** "One upload fans out into five agent stages, in order. Each is a separate span I can open."
2. **Agent 2: Resume Screener -> Score candidate (click it):** "Here's one candidate's screening. Input: the resume summary plus the company rubric. Output: a 4-dimension score with reasoning and bias flags. This is the exact input-to-output of a single decision."
3. **Expand agentic_rag.query under it:** "This is where the score gets grounded. It's not embed-and-hope, it's a self-correcting loop: rewrite the query, retrieve a wide pool, rerank with a cross-encoder, grade each chunk for relevance, retry with new terms if weak. That's what pulls the company's real hiring bar into the prompt. (I had a decide-to-retrieve gate here but removed it after the trace showed it wrongly skipping salary retrieval.)"
4. **Click a rag.rerank span:** "Cross-encoder reranker. The embedding is a bi-encoder that scores query and doc independently, so it mis-ranks. This reads them together. On my eval it took recall 0.83 to 0.98."
5. **Click a ChatOpenAI span:** "Here's the actual prompt sent and the raw model response, with token count, latency, and cost. I can see exactly what each step costs."

Progression to hit: **stages -> one candidate's I/O -> the RAG loop -> the raw LLM call.** That is "how it works inside."

---

## Then run the eval live
`python eval/run_eval.py` -> when metrics print:
> "This is a labeled eval across six failure modes. It didn't just score, it found two weaknesses: multi-fact recall capped by top_k, and a strict prompt over-abstaining on paraphrases. I fixed both, retrieve-wide/rerank-narrow and a synonym-bridging prompt, and re-measured: recall 0.83 to 0.98, MRR to 1.0, 100% out-of-domain abstention with zero hallucination."

---

## Closer (20 sec)
> "The throughline: I don't just build agents, I build the measurement loop and the guardrails that make them trustworthy in production, and I do it plan-first with AI as a reviewed collaborator."

---

## Do / Don't
- DO say "why" after every "what". DO show the eval running. DO own the tradeoffs and known flaws.
- DON'T read code line by line. DON'T overclaim (no TTFT/streaming/fine-tuning). DON'T let the demo die on a cold backend.
- On "I don't know": "I haven't done X in production. Here's how I'd find out: [measure this, try that]."

---

## Known flaws to own if asked (honesty signals)
- `X-Recruiter-ID` header is spoofable -> would use signed JWT from the OAuth session.
- Sequential graph, not parallel DAGs -> would parallelize independent per-candidate calls.
- Eval set is small -> would grow it from real production traces and wire into CI.
