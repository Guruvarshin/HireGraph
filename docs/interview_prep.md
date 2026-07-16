# HireGraph - Interview Prep & Project Deep-Dive

This document is written so that anyone can understand the entire project, every design decision, and every concept used, by reading it top to bottom. Each project-specific question links to the exact file and line it relates to. Concept questions explain the underlying theory in plain language.

Link note: code links are relative to this `docs/` folder, so they point at `../<path>`. On GitHub the `#L<n>` anchor jumps to the line.

---

## Code Map (where everything lives)

| Component | File | Key lines |
|---|---|---|
| Pipeline graph (nodes, edges, interrupts) | [graph/pipeline.py](../graph/pipeline.py) | build [L112](../graph/pipeline.py#L112), interrupts [L149](../graph/pipeline.py#L149), resume [L180](../graph/pipeline.py#L180) |
| Agentic RAG | [memory/agentic_rag.py](../memory/agentic_rag.py) | query loop [L211](../memory/agentic_rag.py#L211), tenancy [L33](../memory/agentic_rag.py#L33) |
| Agents | [agents/](../agents) | jd [L86](../agents/jd_parser.py#L86), screener [L130](../agents/resume_screener.py#L130), planner [L157](../agents/interview_planner.py#L157), evaluator [L114](../agents/interview_evaluator.py#L114), offer [L130](../agents/offer_drafter.py#L130) |
| Prompts | [prompts/agents.py](../prompts/agents.py) | one per agent, [L1](../prompts/agents.py#L1)+ |
| State + data models | [models/pipeline.py](../models/pipeline.py) | stages [L23](../models/pipeline.py#L23), state [L191](../models/pipeline.py#L191) |
| Checkpointer (durable state) | [memory/checkpointer.py](../memory/checkpointer.py) | [L15](../memory/checkpointer.py#L15) |
| Mongo persistence | [memory/database.py](../memory/database.py) | indexes [L32](../memory/database.py#L32) |
| API routes | [api/routes/pipeline.py](../api/routes/pipeline.py) | start [L142](../api/routes/pipeline.py#L142), approvals [L251](../api/routes/pipeline.py#L251)+ |
| Auth (OAuth sign-in) | [api/routes/auth.py](../api/routes/auth.py) | scopes [L28](../api/routes/auth.py#L28) |
| Email (Brevo) + .ics | [utils/email_client.py](../utils/email_client.py) | send [L18](../utils/email_client.py#L18), ics [L82](../utils/email_client.py#L82) |
| Resume parsing + injection defense | [utils/resume_parser.py](../utils/resume_parser.py) · [utils/guardrails.py](../utils/guardrails.py) | extract+summarize [L11](../utils/resume_parser.py#L11) |
| App entry + CORS | [api/main.py](../api/main.py) | routers [L56](../api/main.py#L56) |
| Frontend identity header | [ui/lib/user.js](../ui/lib/user.js) | [L19](../ui/lib/user.js#L19) |

---

## 0. The 30-Second Pitch (memorize)

> HireGraph is a multi-agent AI recruiting pipeline. It takes a job description and a batch of resumes and runs them through five specialized LLM agents (JD parsing, resume screening, interview planning, interview evaluation, offer drafting), orchestrated as a LangGraph state machine. The pipeline pauses at five human-in-the-loop checkpoints where a recruiter approves or edits the AI's output before it proceeds. It grounds JD parsing, resume scoring, interview-plan design, and offer salaries in the company's own hiring rubric using an agentic, self-correcting RAG layer over Pinecone, and it is multi-tenant: each recruiter's knowledge base is isolated in its own Pinecone namespace. Resume uploads are screened by AWS Bedrock Guardrails for prompt-injection and PII, and the whole pipeline is traced in LangSmith.

---

## 1. Project Overview & Motivation

**Q: Walk me through what this project does.**
A: It automates the recruiting funnel end to end. A recruiter uploads a JD plus resumes. The system: (1) parses the JD into structured fields, (2) scores each resume on four dimensions against the company's rubric, (3) generates a tailored interview plan per candidate, (4) synthesizes interviewer feedback into a hire/no-hire call, and (5) drafts offer letters with salary justified against the company's pay bands. Between these, a human reviews and approves. The control loop is the LangGraph build in [graph/pipeline.py:112](../graph/pipeline.py#L112); the entry point is the `start` API in [api/routes/pipeline.py:142](../api/routes/pipeline.py#L142).
Concept: this is an "AI workflow" rather than a chatbot. The value is automating judgment-heavy but repetitive work while keeping a person accountable.

**Q: Why multi-agent instead of one big prompt?**

A: Each stage has a distinct objective, output schema, and failure mode, so I split them into specialist agents (the five `run_*` functions, e.g. [agents/resume_screener.py:130](../agents/resume_screener.py#L130)). Benefits: (1) focused prompts produce more reliable structured output, (2) errors are isolated per stage, (3) the seams between agents are the natural places to insert human approval, and (4) I can improve one agent without touching the others. A single mega-prompt would be brittle, hard to debug, and impossible to pause mid-flow for a human.
Concept: "separation of concerns" applied to LLM calls, the same reason you split a monolith into services.

**Q: Who is the user and what problem does it solve?**
A: Recruiters and hiring managers. It cuts the manual hours in screening and offer drafting while keeping a human in control of every consequential decision (who advances, who gets an offer, what salary). The AI does the heavy lifting; the human keeps accountability. Identity is the recruiter's email, carried as the `X-Recruiter-ID` header from the frontend ([ui/lib/user.js:19](../ui/lib/user.js#L19)).

**Q: What is the single most technically interesting part?**
A: Two things. (1) The LangGraph state machine with `interrupt_before` ([graph/pipeline.py:149](../graph/pipeline.py#L149)) that lets a long-running, stateful workflow pause for human input and resume days later from a durable checkpoint. (2) The agentic RAG loop ([memory/agentic_rag.py:211](../memory/agentic_rag.py#L211)) that self-corrects its own retrieval: rewrite, retrieve, cross-encoder rerank, grade, retry, web-fallback.

---

## 2. LangGraph & Orchestration

**Q: What is LangGraph and why use it here?**
A: LangGraph is a framework for building stateful, multi-step LLM workflows as a graph of nodes over a shared state, with durable checkpointing and the ability to pause (interrupt) execution. I use it because I need three things a plain script or a linear LangChain chain does not give you: a typed shared state that flows through stages, persistence so a run can pause and resume, and interrupts for human-in-the-loop. The graph is assembled in [graph/pipeline.py:112](../graph/pipeline.py#L112).
Concept: think of it as a workflow engine (like a state machine or DAG runner) specialized for LLM apps.

**Q: How is the graph structured?**
A: It is a linear `StateGraph` ([graph/pipeline.py:115](../graph/pipeline.py#L115)). Nodes are added at [L118-128](../graph/pipeline.py#L118), edges wire them in sequence at [L134-144](../graph/pipeline.py#L134), and the entry point is `jd_parser` ([L131](../graph/pipeline.py#L131)). The five agent nodes do the real work; the `*_review` nodes (e.g. `_shortlist_review` at [L21](../graph/pipeline.py#L21)) are thin functions that just advance the stage after a human approves.

**Q: What is a node, and what does it return?**
A: A node is a function that receives the shared state and returns a partial dict of updates, which LangGraph merges back into the state. For example `run_resume_screener` returns `{"candidates": ..., "shortlist": ..., "current_stage": ...}` ([agents/resume_screener.py:130](../agents/resume_screener.py#L130)). Returning only changed keys keeps nodes decoupled.
Concept: nodes are pure-ish transformations of state, like reducers.

**Q: How do the human checkpoints work technically?**
A: The graph is compiled with `interrupt_before=[...]` ([graph/pipeline.py:149](../graph/pipeline.py#L149)) listing the five gate nodes. When execution reaches one, LangGraph stops before running it and returns control, checkpointing the state. The recruiter approves via an API endpoint (e.g. `approve_shortlist` at [api/routes/pipeline.py:251](../api/routes/pipeline.py#L251)), which calls `resume_pipeline` ([graph/pipeline.py:180](../graph/pipeline.py#L180)) to write their edits with `update_state` and then `invoke(None)` to continue.
Concept: an interrupt is a built-in "pause and persist" so a human can step into an otherwise automated flow.

**Q: What is a thread_id?**
A: A UUID generated per pipeline run ([api/routes/pipeline.py:142](../api/routes/pipeline.py#L142) start handler). It is the key LangGraph uses to load and save that run's checkpoint, set in `get_config` ([graph/pipeline.py:162](../graph/pipeline.py#L162)), and it is also the primary key in the Mongo `pipeline_runs` collection. One thread_id equals one hiring run.

**Q: How do you resume a paused pipeline?**
A: `resume_pipeline(thread_id, state_update)` ([graph/pipeline.py:180](../graph/pipeline.py#L180)) calls `update_state` to inject the recruiter's edits into the checkpoint, then `invoke(None, config)`. Passing `None` tells LangGraph to continue from the last checkpoint rather than start over.

**Q: What happens if a node throws?**
A: The API wraps `start_pipeline`/`resume_pipeline` in try/except, marks the run failed in Mongo, and returns a 500 (e.g. [api/routes/pipeline.py](../api/routes/pipeline.py#L226)). Inside agents, per-candidate errors are caught so one bad resume does not kill the batch; the agent returns partial results plus an `error_message` (pattern in [agents/resume_screener.py:130](../agents/resume_screener.py#L130)).

---

## 3. The Five Agents

**Q: Describe each agent's input/output contract.**
A:
- JD Parser ([agents/jd_parser.py:86](../agents/jd_parser.py#L86)): raw JD text in, structured `JobDescription` out ([models/pipeline.py:77](../models/pipeline.py#L77)).
- Resume Screener ([agents/resume_screener.py:130](../agents/resume_screener.py#L130)): JD + resume + rubric in, `CandidateScore` out ([models/pipeline.py:109](../models/pipeline.py#L109)) with four dimension scores, reasoning, bias flags, shortlist recommendation.
- Interview Planner ([agents/interview_planner.py:157](../agents/interview_planner.py#L157)): shortlisted candidates in, `InterviewPlan` out ([models/pipeline.py:132](../models/pipeline.py#L132)) with tailored rounds.
- Interview Evaluator ([agents/interview_evaluator.py:114](../agents/interview_evaluator.py#L114)): interviewer feedback in, `InterviewEvaluation` out ([models/pipeline.py:155](../models/pipeline.py#L155)).
- Offer Drafter ([agents/offer_drafter.py:130](../agents/offer_drafter.py#L130)): approved evaluations + comp-band context in, `OfferDraft` out ([models/pipeline.py:166](../models/pipeline.py#L166)).

**Q: How do agents return structured data reliably?**
A: Each has a strict system prompt demanding JSON-only ([prompts/agents.py:1](../prompts/agents.py#L1)+). Responses are run through a `_extract_json` helper that strips markdown code fences, then `json.loads`, then a Pydantic model validates the shape. If parsing or validation fails, the agent raises a `RuntimeError` with the raw output truncated for debugging. Temperature is 0 (set on the `ChatOpenAI` clients).
Concept: never trust raw LLM text; validate at the boundary. Pydantic is the contract.

**Q: Why temperature 0?**
A: These are extraction and scoring tasks, not creative writing. Temperature 0 makes sampling greedy (always the most probable token), so the same resume yields the same score and the JSON format stays stable. Set where each model is constructed in the agents and in [memory/agentic_rag.py:61](../memory/agentic_rag.py#L61).

**Q: The screener has bias flags, explain.**
A: The screener prompt ([prompts/agents.py:26](../prompts/agents.py#L26)) instructs the model to surface potential bias signals (name, prestige, gap, non-linear career, company prestige) as a list and explicitly not to penalize for short gaps, bootcamps, foreign university names, or short startup stints. Flags are advisory; they surface to the recruiter and never auto-reject. A helper normalizes whether the LLM returns a list or a dict of flags (in [agents/resume_screener.py](../agents/resume_screener.py#L34)).
Concept: responsible-AI design in a sensitive domain, surface bias rather than silently acting on it.

**Q: How does the screener use the company rubric?**
A: Before scoring it calls `rag.query("scoring criteria for ...", namespace="company_rubrics", user_id=...)` ([agents/resume_screener.py:168](../agents/resume_screener.py#L168)). Relevant rubric chunks are injected into the prompt so the model scores against this company's bar, not a generic one.

**Q: Where is agentic RAG actually used across the pipeline?**
A: In four agents - it is the shared grounding layer, not a single feature. Each makes a judgment and first retrieves the relevant slice of the company's rubric via the same `rag.query(...)` loop:
- **JD Parser** ([jd_parser.py:97](../agents/jd_parser.py#L97)): "hiring standards seniority expectations" - parses the JD against the company's seniority conventions.
- **Resume Screener** ([resume_screener.py:168](../agents/resume_screener.py#L168)): "scoring criteria for {seniority} {title}" - scores against the company's hiring bar (the four dimension scores + shortlist flag).
- **Interview Planner** ([interview_planner.py:195](../agents/interview_planner.py#L195)): "interview process rounds format for {seniority} {title}" - designs rounds that match the company's actual interview process.
- **Offer Drafter** ([offer_drafter.py:186](../agents/offer_drafter.py#L186)): "{seniority} {title} salary compensation {location}" - justifies the offer salary against the company's pay bands.
One deliberate nuance: the first three pass `allow_web_fallback=False` because the rubric/process is proprietary (a generic web result would mislead), while the offer/salary query leaves web fallback on (default) because market pay data is public, so if the rubric has nothing it can pull current rates from Tavily rather than fabricate.

---

## 4. RAG / Agentic Retrieval (high-value topic)

**Q: Walk through your RAG pipeline step by step.**
A: It is a self-correcting agentic loop in `AgenticRAG.query` ([memory/agentic_rag.py](../memory/agentic_rag.py)):
1. Rewrite: an LLM reformulates the query to be keyword-dense; on a retry it uses different terms and broadens scope.
2. Retrieve: embed the rewritten query, query Pinecone for a wide pool (RETRIEVE_K=12) in the user's namespace.
3. Rerank: reorder the pool with a cross-encoder (`bge-reranker-v2-m3` via Pinecone inference) and narrow to the top 5. Over-fetching then reranking pulls in chunks the embedding ranked at 6-12 that actually answer the query, so the reranker improves recall, not just ordering.
4. Grade: for each retained chunk an LLM returns `{"relevant": bool, "reason": ...}`; only relevant chunks pass.
5. Retry: if fewer than `MIN_RELEVANT_DOCS` (1) pass, loop back to rewrite, capped at `MAX_RETRIEVAL_ATTEMPTS` (2).
6. Fallback: if still nothing (and web fallback is allowed), web-search via Tavily, grade those results too, and index the kept ones.

**Q: Don't you have a "decide whether to retrieve" step?**
A: I did - a decide gate that asked an LLM "does this query need retrieval?" and skipped retrieval on NO. I removed it. The LangSmith trace showed it wrongly classifying salary as general knowledge and skipping the offer drafter's pay-band lookup, so the offer was priced from the model's priors instead of the company's rubric. Since all my callers are grounding calls that have already decided they need the rubric, the gate was pure downside: an extra LLM call that could skip needed retrieval. So retrieval now always runs. The point worth making: a decide/route gate is the least "agentic" step anyway (a one-shot classifier), and finding this via the trace is exactly why I instrument every step.

**Q: Is it still agentic without the decide gate?**
A: Yes. Agentic RAG is defined by the system reflecting on and correcting its own retrieval, not by a routing gate. The loop still grades every chunk for relevance (reflection), rewrites and retries with new terminology when retrieval is weak (adaptive iteration), and falls back to a web-search tool when the KB fails (tool use). Those three - reflection, adaptive iteration, tool use - are the defining agentic markers and are all intact. The decide gate was a one-shot router, the weakest agentic signal.

**Q: Why agentic RAG instead of naive embed-and-retrieve?**
A: Naive RAG returns the top-k whether or not they are relevant, and the LLM then hallucinates on weak context. The agentic loop adds self-correction: it grades relevance, rewrites and retries on weak retrieval, and falls back to the web rather than fabricating. It trades extra LLM calls for groundedness and far fewer hallucinations.
Concept: this is "reflection," the agent evaluating and correcting its own intermediate output.

**Q: Why agentic RAG and not hybrid search?**
A: They are not alternatives; they improve different layers and are complementary. Hybrid search improves the retrieval step itself by fusing dense (embedding) similarity with sparse keyword search (BM25), so the candidate set catches both semantic matches and exact terms. Agentic RAG is a control loop wrapped around retrieval ([memory/agentic_rag.py:211](../memory/agentic_rag.py#L211)): rewrite, retrieve, rerank, grade for relevance, retry, fall back. One improves what you fetch; the other decides whether what you fetched is trustworthy enough to feed the model. You can run agentic RAG with a hybrid retriever inside its `_retrieve` step ([memory/agentic_rag.py:116](../memory/agentic_rag.py#L116)).
I prioritized the agentic loop because the dominant risk in a hiring tool is the LLM confidently reasoning over context that looks retrieved but is not relevant (a wrong score or mispriced offer), not missing a keyword. The grader ([L139](../memory/agentic_rag.py#L139)) and web fallback ([L176](../memory/agentic_rag.py#L176)) attack that directly; hybrid search would not, since it improves recall but never checks relevance or groundedness.
Honest caveat: hybrid search would genuinely help here and is a good next improvement, because rubrics contain exact tokens (specific skills like "Kafka" or "PostgreSQL", seniority labels, pay-band names) where pure dense embeddings can under-retrieve and BM25 nails exact-term recall. The strongest design is hybrid retrieval inside the agentic loop: hybrid maximizes candidate-set quality, the agentic grader/retry guarantees groundedness on top. So it is "add hybrid underneath," not "agentic instead of hybrid."

**Q: What is the cost tradeoff of that loop?**
A: Each query can cost several small LLM calls (rewrite + one grade per chunk, possibly twice) plus one rerank call. I use GPT-4o-mini for those cheap, high-volume steps ([memory/agentic_rag.py:61](../memory/agentic_rag.py#L61)) and cap retries at 2. For recruiting, where a wrong salary or missed rubric is expensive, the extra pennies buy reliability. (I removed a decide gate that was one more call and was misrouting, so the loop is now leaner too.)

**Q: How do you chunk documents?**
A: A word-based sliding window in `_chunk_text` ([memory/agentic_rag.py:298](../memory/agentic_rag.py#L298)): 500 words per chunk with 100 words of overlap. Overlap prevents losing meaning that straddles a boundary.
Concept: chunking balances retrievable specificity against context cost; overlap preserves continuity.

**Q: How are vector IDs generated and why?**
A: `_make_id` ([memory/agentic_rag.py:311](../memory/agentic_rag.py#L311)) builds `{namespace}_{md5(text)[:12]}_{chunk_index}`. The content hash makes re-uploading the same document idempotent: identical chunks overwrite rather than duplicate.

**Q: Which embedding model, and why must dimensions match?**
A: OpenAI `text-embedding-3-small`, 1536 dimensions ([memory/agentic_rag.py:61](../memory/agentic_rag.py#L61)). The Pinecone index must be created with the same 1536 dimensions, because similarity search compares vectors of equal length.

---

## 5. Vector DB & Multi-Tenancy

**Q: How is multi-tenancy implemented?**
A: Pinecone namespaces partition one index. `get_tenant_id` ([memory/agentic_rag.py:33](../memory/agentic_rag.py#L33)) sanitizes the user's full email into a Pinecone-safe string, and `tenant_namespace` ([L43](../memory/agentic_rag.py#L43)) yields `{tenant}__{base}`, e.g. `guruvarshinib_ai_gmail_com__company_rubrics`. Every index/query call passes the user id, so a search only ever touches that user's partition.
Concept: a namespace is a hard data boundary, stronger than filtering, you cannot accidentally cross it.

**Q: Why full email and not the email domain?**
A: I started with the domain so a whole company shared one namespace, but that collides all personal Gmail users and ignores that different recruiters maintain different rubrics. Full-email isolation is the safe default: one user, one knowledge base. The change lives in `get_tenant_id` ([memory/agentic_rag.py:33](../memory/agentic_rag.py#L33)).

**Q: Why namespaces instead of metadata filters or separate indexes?**
A: Namespaces are free, give hard isolation, and avoid the per-index endpoint cost of one index per tenant. Metadata filtering would work but is weaker; a filter bug could leak data, a namespace boundary cannot be crossed.

**Q: How is the rest of the app multi-tenant?**
A: Every route requires the `X-Recruiter-ID` header. Mongo `pipeline_runs` are scoped by `user_id` ([memory/database.py:123](../memory/database.py#L123)), and every read verifies ownership, e.g. `state.get("user_id") != x_recruiter_id` raises 403 ([api/routes/pipeline.py:135](../api/routes/pipeline.py#L135)).

**Q: You merged two namespaces into one, why?**
A: Originally rubrics and salary "market data" were separate namespaces. But comp data is just another company-owned document, so I folded it into `company_rubrics`; the offer drafter now queries that one namespace for salary ([agents/offer_drafter.py:186](../agents/offer_drafter.py#L186)). Fewer moving parts and one upload for the user.

---

## 6. State Management & Persistence

**Q: Where does pipeline state live?**
A: Two places. (1) LangGraph's checkpointer ([memory/checkpointer.py:15](../memory/checkpointer.py#L15), `MongoDBSaver`) stores the authoritative graph state in `lg_checkpoints`, keyed by thread_id; this is what enables pause/resume. (2) A denormalized copy in `pipeline_runs` ([memory/database.py:80](../memory/database.py#L80)) for fast dashboard listing.
Concept: two representations for two access patterns, a CQRS-style split.
Writes go to the LangGraph checkpoint as the full authoritative state; reads for the dashboard come from a small denormalized pipeline_runs summary. It's a CQRS-style split — different models for the write and read paths — so listing runs is cheap without loading every full checkpoint, and the detail view reads the checkpoint directly when it needs the truth.
CQRS = Command Query Responsibility Segregation. The core idea: the way you write data and the way you read data have different needs, so use different models (or stores) for each instead of forcing one shape to serve both.

Command side = writes/mutations. Optimized for correctness and capturing the full truth.
Query side = reads. Optimized for fast, convenient retrieval in the shape the UI wants.
In a strict CQRS system these are two separate models kept in sync. HireGraph uses a lightweight, CQRS-style split — not the full pattern, but the same instinct.

**Q: Why two copies, is that not duplication?**
A: They serve different reads. The checkpoint is the source of truth for execution; the `pipeline_runs` doc is a read-optimized projection (status, stage, title, counts) for the "my pipelines" list ([memory/database.py:123](../memory/database.py#L123)). Replaying full graph state for every list item would be expensive.

**Q: How do you delete a run, and what's the gotcha?**
A: `DELETE /pipeline/{thread_id}` ([api/routes/pipeline.py](../api/routes/pipeline.py)), ownership-checked (403 if not yours), calls `delete_pipeline_run` ([memory/database.py:140](../memory/database.py#L140)). The gotcha is a direct consequence of the two-store design: deleting must clean up *both* stores. The original helper only removed the `pipeline_runs` summary, which would leave the authoritative LangGraph state (`lg_checkpoints` + `lg_checkpoint_writes`) orphaned in Mongo forever. So delete now clears all three collections keyed by thread_id. The UI does an optimistic remove and restores the card if the call fails.
Concept: any time you denormalize into a second store, deletes (and updates) have to fan out to every copy, or you leak orphaned state.

**Q: What is `PipelineState`?**
A: A `TypedDict` (total=False) at [models/pipeline.py:191](../models/pipeline.py#L191) holding thread_id, user_id, recruiter info, status, current_stage, the JD, and the lists (candidates, shortlist, plans, feedback, evaluations, offer_drafts) plus timestamps. TypedDict keeps it a plain dict for LangGraph while giving type hints.

**Q: Pydantic models vs the TypedDict state, why both?**
A: The state is plain dicts (LangGraph-friendly, JSON-serializable). The Pydantic models ([models/pipeline.py:77](../models/pipeline.py#L77)+) validate data at the boundaries when an agent produces output or an API receives a request, then I `model_dump(mode="json")` back to dicts. Validation at the edges, dicts in the middle.

---

## 7. Human-in-the-Loop (HITL)

**Q: Why HITL at all?**
A: The decisions are consequential and legally sensitive (rejections, offers, salary). A wrong automated rejection or mispriced offer is costly and possibly discriminatory. HITL keeps a human accountable while the AI accelerates the work. The five gates are declared at [graph/pipeline.py:149](../graph/pipeline.py#L149).

**Q: Where does it pause and why those points?**
A: shortlist review (before committing who advances), finalist review (approve plans, add interviewer emails), awaiting feedback (humans actually interview), offer-candidates review (choose who gets offers), offer review (approve/edit salary before sending). Each endpoint validates the stage and ownership before resuming, e.g. `approve_shortlist` [L251](../api/routes/pipeline.py#L251), `approve_plans` [L292](../api/routes/pipeline.py#L292), `submit_feedback` [L327](../api/routes/pipeline.py#L327), `approve_offer_candidates` [L391](../api/routes/pipeline.py#L391), `approve_final_offers` [L424](../api/routes/pipeline.py#L424).

**Q: How does the recruiter's edit flow back into the graph?**
A: The endpoint passes the edited list as `state_update` to `resume_pipeline` ([graph/pipeline.py:180](../graph/pipeline.py#L180)); `update_state` writes it into the checkpoint, then `invoke(None)` resumes. Feedback uses `update_state` directly ([api/routes/pipeline.py:353](../api/routes/pipeline.py#L353)).

**Q: Can a run resume days later?**
A: Yes, that is the point of durable checkpointing. State sits in Mongo indefinitely; nothing is in memory, so a recruiter can submit feedback a week later and the graph continues from where it paused.

---

## 8. Prompt Engineering

**Q: How do you enforce JSON output?**
A: System prompts ([prompts/agents.py](../prompts/agents.py#L1)) specify the exact schema, say "JSON only, no markdown," and give per-field rules (e.g. years must be an integer or null). Plus defensive parsing (`_extract_json`) and Pydantic as a net.

**Q: How do you handle markdown-fenced JSON?**
A: A regex in `_extract_json` (top of each agent, e.g. [agents/resume_screener.py](../agents/resume_screener.py#L27)) pulls content out of triple-backtick fences before `json.loads`. GPT models love fences, so this prevents parse breaks. The grader has the same guard ([memory/agentic_rag.py:139](../memory/agentic_rag.py#L139)).

**Q: How are interview questions made candidate-specific?**
A: The planner prompt ([prompts/agents.py:62](../prompts/agents.py#L62)) says questions must reference this candidate's resume, and the resume is in context, so the model generates questions about the candidate's actual projects.

**Q: The offer drafter once produced a 2023 date, what happened?**
A: The prompt said "start date ~3-4 weeks from now," but GPT has no notion of "now," so it guessed a stale date from training. Fix: inject the real current date into the prompt before the call ([agents/offer_drafter.py](../agents/offer_drafter.py#L130)). Classic "LLMs do not know today's date" gotcha.

---

## 9. LLM Integration & Reliability

**Q: Which models, where, and why the split?**
A: GPT-4o for the five agents (complex reasoning + structured output); GPT-4o-mini for the RAG grader and rewriter (cheap, high-volume). All model ids come from env vars, so they are swappable without code changes ([memory/agentic_rag.py:61](../memory/agentic_rag.py#L61)).

**Q: How would you make it model-agnostic?**
A: Agents already read model ids from env. I would add a provider abstraction so `ChatOpenAI` could become `ChatBedrock` (Claude) or `ChatGoogleGenerativeAI` (Gemini) by env toggle. Since everything goes through LangChain's chat interface, call sites barely change.

**Q: Main failure modes and handling?**
A: (1) Malformed JSON -> regex extract + Pydantic + RuntimeError with raw output. (2) One bad resume -> per-candidate try/except, partial results ([agents/resume_screener.py:130](../agents/resume_screener.py#L130)). (3) API error -> caught, surfaced as error_message, run marked failed. (4) Empty/garbage input -> guards (empty resume returns a zero score; a "Parsing..." JD title blocks screening).

---

## 10. Auth, Security & Email

**Q: How does auth work?**
A: Google OAuth 2.0 for sign-in only ([api/routes/auth.py:40](../api/routes/auth.py#L40) start, [L60](../api/routes/auth.py#L60) callback). The callback exchanges the code for tokens, fetches the user's email, stores a recruiter profile, and the email becomes the tenant identity. Scopes are limited to `openid email profile` ([api/routes/auth.py:28](../api/routes/auth.py#L28)).

**Q: Why only sign-in scopes?**
A: `gmail.send` is a restricted scope and `calendar` is sensitive; both force Google's multi-week app-verification before non-test users can sign in. Requesting only non-sensitive scopes removes verification entirely, anyone can sign in instantly.

**Q: How do you send email then?**
A: The Brevo HTTP API over HTTPS ([utils/email_client.py:18](../utils/email_client.py#L18)). The app POSTs sender, recipient, HTML, and `.ics` attachments to Brevo's endpoint ([L52](../utils/email_client.py#L52)). Single-sender verification lets me send from a Gmail address to anyone without a domain. `Reply-To` is the recruiter ([L40](../utils/email_client.py#L40)).

**Q: Why not SMTP or the Gmail API?**
A: The Gmail API needs the restricted scope (verification). Gmail SMTP avoids that but cloud hosts (Railway) block outbound SMTP ports, so SMTP hangs and times out in production. An HTTP API uses port 443, which is never blocked. See the email saga below.

**Q: Calendar invites without the Calendar API?**
A: I build `.ics` (iCalendar VEVENT) files in `_build_ics` ([utils/email_client.py:82](../utils/email_client.py#L82)) and attach one per scheduled round in `send_interview_invite` ([L131](../utils/email_client.py#L131)). Recipients add them to any calendar. No Google scope, works across providers.

**Q: Walk me through the email saga, it is a good debugging story.**
A: Three stages. (1) Originally Gmail API + Calendar API (both HTTPS) worked but needed restricted scopes. (2) I switched to Gmail SMTP to drop verification; it worked locally but on Railway each send hung ~1 minute then failed with `Errno 101`. The 1-minute hang (587 then 465, each 30s timeout) showed both SMTP ports were blocked, which most PaaS do to deter spam. (3) Confirmed because the emails that did arrive were from the old HTTPS API code, never SMTP. Fix: the Brevo HTTP API on 443. Lesson: clouds block SMTP, which is exactly why transactional-email APIs exist.

**Q: The `X-Recruiter-ID` is just an email header, is it not spoofable?**
A: Yes, a known simplification ([ui/lib/api.js:66](../ui/lib/api.js#L66) sets it). In production I would replace it with a signed JWT from the OAuth session so identity cannot be forged. It is a deliberate, documented tradeoff.

---

## 11. Deployment & Infrastructure

**Q: How is it deployed?**
A: Backend is Dockerized and runs on Railway (builds from the Dockerfile; `railway.toml` sets a `/health` healthcheck, defined at [api/main.py:62](../api/main.py#L62)). Frontend (Next.js) on Vercel. MongoDB Atlas and Pinecone are managed. Secrets are env vars in the host dashboard.

**Q: How does the container handle ports?**
A: The Dockerfile CMD runs `uvicorn ... --port ${PORT:-8000}`. The host injects `$PORT`; it falls back to 8000 locally. One line makes it portable across Railway, Render, and Cloud Run.

**Q: Why Railway over Render?**
A: Railway's Hobby plan keeps the service warm (no cold starts), which is a better live-demo experience; Render's free tier sleeps after ~15 minutes. The tradeoff is Render is free without a card. Both block SMTP, so email was unaffected by the choice.

**Q: How would you scale this?**
A: The backend is stateless (all state in Mongo/Pinecone), so it scales horizontally behind a load balancer. The bottleneck is LLM latency and rate limits, not compute, so I would add request queuing, async batching of per-candidate calls, and embedding caching.

---

## 12. Cost, Observability & Production Concerns

**Q: Where are the costs and how do you control them?**
A: LLM tokens dominate. Controls: GPT-4o-mini for cheap high-volume steps, temperature 0 (no resampling), capped RAG retries, chunk text truncated in metadata, and idempotent vector IDs to avoid re-embedding duplicates ([memory/agentic_rag.py:311](../memory/agentic_rag.py#L311)).

**Q: How would you parallelize per-candidate work?**
A: Screening, planning, and drafting loop over candidates sequentially today. They are independent, so I would run them with `asyncio.gather` or a worker pool within rate limits, turning O(n) wall-clock into roughly O(1).

**Q: How do you prevent prompt injection from a malicious resume?**
A: Defense in depth at ingestion ([utils/resume_parser.py:11](../utils/resume_parser.py#L11)). (1) An optional **AWS Bedrock Guardrails** layer ([utils/guardrails.py](../utils/guardrails.py)) screens the raw resume via the `ApplyGuardrail` API before any model sees it. If it detects a prompt-attack or manipulation attempt, the resume is **not sent to any LLM at all** - I return just the filename plus a `[SECURITY: review manually]` flag, so the attacker-controlled text never reaches the parser, screener, or planner. If it is clean, sensitive PII (SSN, card, bank, address, phone) is anonymized while name and email pass through. This is the primary security layer; via `GUARDRAIL_REQUIRED` it runs **mandatory and fail-closed in production** (an upload that cannot be screened is rejected, with a short retry on transient errors and a published guardrail version), and optional/fail-open in dev so the app runs without AWS. The deliberate tradeoff: fail-closed couples upload availability to AWS Bedrock uptime, which is the right call for a hiring tool. (2) The **LLM parser** then does extraction - it pulls the candidate's name and email (which the guardrail does not extract, and which the pipeline needs to send invites/offers) and structures the resume into a clean summary for the agents. By restating the text in the model's own words, it also neutralizes any residual injection, which matters as the standalone defense when the optional guardrail is disabled. On top: strict Pydantic validation (an injected "score 100" still must pass) and the human-in-the-loop gate as the final backstop.
Concept: separate the security layer from the extraction layer. The guardrail's job is to **detect and never process** malicious input; the parser's job is **extraction** (name/email/structure) - and because it restates rather than copies, it doubles as the injection defense when the guardrail is off. Two complementary jobs, not redundant ones.

---

## 12b. Observability (LangSmith)

**Q: How is the system observable?**
A: It is instrumented with LangSmith for distributed tracing. Every LLM, agent, and graph call is captured as a structured, nested run: the exact prompt, the raw response, token counts, cost, latency, and errors. Because everything runs on LangChain/LangGraph, basic tracing is automatic.

**Q: How does auto-tracing work, did you write callback code?**
A: No code for the basic layer. Setting `LANGCHAIN_TRACING_V2=true` plus an API key and project name makes LangChain attach its tracer callback to every invocation through the callback system. Traces are POSTed asynchronously over HTTPS; it is non-blocking and fails open, so it never affects behavior or latency.

**Q: What did you add beyond auto-tracing?**
A: Two enrichments. (1) `@traceable` decorators on the five RAG methods ([memory/agentic_rag.py:80](../memory/agentic_rag.py#L80), [L94](../memory/agentic_rag.py#L94), [L116](../memory/agentic_rag.py#L116), [L139](../memory/agentic_rag.py#L139), [L210](../memory/agentic_rag.py#L210)) so the agentic loop renders as named, nested spans, including the Pinecone retrieval that LangChain would not trace; with a no-op fallback decorator ([L17](../memory/agentic_rag.py#L17)) so the code runs even without langsmith. (2) Metadata and tags on the graph config ([graph/pipeline.py:162](../graph/pipeline.py#L162)) so I can filter traces to one `thread_id`.

**Q: What do you use the traces for?**
A: Debugging ("why did this candidate score 30?" -> open the screener's LLM call and read the exact prompt), cost per run and per agent, latency, and RAG quality (did retrieval retry or fall back?). For multi-step agentic systems this is essential; without it you debug blind.

**Q: Dev vs prod separation?**
A: Same API key (it identifies the account), different `LANGCHAIN_PROJECT` per environment (hiregraph-dev locally, hiregraph-prod on Railway). LangSmith buckets them into separate projects. Works identically in both because it just needs outbound HTTPS.

---

## 13. Testing & Quality

**Q: How would you test a non-deterministic LLM pipeline?**
A: Layered. (1) Deterministic unit tests for pure functions: chunking ([memory/agentic_rag.py:298](../memory/agentic_rag.py#L298)), id generation ([L311](../memory/agentic_rag.py#L311)), ics building ([utils/email_client.py:82](../utils/email_client.py#L82)), tenant namespacing ([L43](../memory/agentic_rag.py#L43)), JSON extraction. (2) Pydantic schema validation as a contract test on agent outputs. (3) A RAG eval harness ([eval/run_eval.py](../eval/run_eval.py)) over a labeled dataset measuring recall@k, precision@k, MRR, and LLM-judge faithfulness/relevance - the same idea extends to a golden resumes+JD set with expected score ranges (strong > 70, weak < 40), tolerant to variance. (4) Mock the LLM for graph-flow tests asserting state transitions and interrupts.

**Q: How do you evaluate screening quality?**
A: Build a recruiter-labeled set, run the screener, and measure rank correlation / precision@k against the labels. Temperature 0 keeps it stable enough to catch regressions when prompts change.

---

## 14. Design Decisions & Tradeoffs

**Q: Biggest tradeoff you made?**
A: Reliability over speed/cost in the RAG loop, multiple LLM calls per retrieval to self-correct ([memory/agentic_rag.py:211](../memory/agentic_rag.py#L211)). For a domain where a wrong salary or missed rubric is expensive, groundedness wins over latency.

**Q: Something you would do differently?**
A: Start model-agnostic, use signed sessions instead of an email header, and add tracing/evals earlier (tracing is now done). Also parallelize per-candidate calls sooner.

**Q: Why MongoDB and not Postgres?**
A: State is deeply nested, schema-flexible JSON (variable-length lists of evaluations, plans), and LangGraph ships a first-class `MongoDBSaver` checkpointer ([memory/checkpointer.py:15](../memory/checkpointer.py#L15)). Mongo's document model fits, and I get checkpointing for free. Postgres+JSONB would also work; the checkpointer integration made Mongo pragmatic.

**Q: What are you most proud of?**
A: The resumable HITL architecture, a multi-day, stateful agentic workflow that pauses for human judgment and resumes from a durable checkpoint, with strict tenant isolation throughout. It mirrors real production agentic systems.

---

## 15. Agentic-AI Concepts (role-specific theory)

**Q: Is this agentic? Defend it.**
A: Yes, in two senses. (1) The RAG layer ([memory/agentic_rag.py:211](../memory/agentic_rag.py#L211)) is an autonomous loop that reflects by grading its own retrieved results, adapts by rewriting and retrying with new terms when retrieval is weak, and acts by calling a tool (web search) when the KB fails, a self-correcting loop. (2) The pipeline is a multi-agent system where specialists hand off shared state. It is a structured (graph-orchestrated) agentic system rather than a free-roaming agent, a deliberate choice for reliability.

**Q: Structured workflow vs autonomous agent, why structured?**
A: A fully autonomous agent choosing its own steps is powerful but unpredictable and hard to checkpoint for HITL. A fixed graph gives deterministic stage boundaries, clean approval points, and debuggability. For a high-stakes process you want guardrails, not open-ended autonomy.

**Q: Which agentic patterns are present?**
A: Tool use (Pinecone retrieval, Tavily search), reflection (relevance grading), query reformulation (rewrite-and-retry), and multi-agent decomposition. (I had a routing/decide-to-retrieve step but removed it after tracing showed it misrouting grounding calls.) A future planner agent and a fairness critic are the natural next additions.

---

## 16. Rapid-Fire / Gotcha Questions

- top_k? 5 ([memory/agentic_rag.py:26](../memory/agentic_rag.py#L26)).
- Chunk size / overlap? 500 / 100 ([L29](../memory/agentic_rag.py#L29)).
- Embedding dims? 1536.
- Max RAG retries? 2 ([L28](../memory/agentic_rag.py#L28)).
- HITL checkpoints? 5 ([graph/pipeline.py:149](../graph/pipeline.py#L149)).
- Agents? 5 ([graph/pipeline.py:118](../graph/pipeline.py#L118)).
- What makes re-upload idempotent? content-hash vector IDs ([memory/agentic_rag.py:311](../memory/agentic_rag.py#L311)).
- Tenant key? sanitized full email -> namespace prefix ([L33](../memory/agentic_rag.py#L33)).
- Why temperature 0? deterministic structured output.
- How is a paused run keyed? thread_id -> Mongo checkpoint ([memory/checkpointer.py:15](../memory/checkpointer.py#L15)).
- What stops cross-tenant leaks? namespace boundary + user_id checks ([api/routes/pipeline.py:135](../api/routes/pipeline.py#L135)).
- How is email sent? Brevo HTTP API ([utils/email_client.py:18](../utils/email_client.py#L18)).
- Observability? LangSmith auto-trace + `@traceable` ([memory/agentic_rag.py:80](../memory/agentic_rag.py#L80)).

---

## 17. Questions YOU Should Ask Back

- How do you evaluate and monitor LLM output quality in production?
- Autonomous agents vs structured workflows for business-critical flows?
- How do you handle prompt versioning and regression testing when prompts change?
- What is your guardrail strategy for fairness/bias in automated decisioning?

---

## 18. Likely "Improve / Extend It" Prompts

- Stream agent output to the UI (SSE/websockets).
- Parallelize per-candidate LLM calls with asyncio.
- Add a fairness-critic agent over screening/offer decisions.
- Model-agnostic provider layer (OpenAI/Claude/Gemini).
- Cache embeddings and repeated rubric queries.
- Wire the eval harness into CI for regression on every prompt change (the harness itself is already built and run; tracing already done).
- Signed sessions (JWT) replacing the email header.
- Dynamic routing graph (skip stages for clear no-hires).
- Responsible-AI guardrails are already done at ingestion via AWS Bedrock Guardrails (prompt-injection block + PII anonymization) plus LLM summarization; next would be extending guardrails to agent outputs (offer/decision grounding).

---

## 19. Core LLM Concepts (fundamentals)

**Q: What is a large language model?**
A: A transformer neural network trained to predict the next token over huge text corpora. Every task (answer, extract, classify) is next-token prediction conditioned on the prompt. It has no memory between calls except what you put in the context window.

**Q: What is a token?**
A: The unit an LLM reads and generates, roughly 3-4 characters or 0.75 words in English. Text is tokenized into integers (tiktoken for OpenAI). Billing and context limits are measured in tokens.

**Q: What is the context window?**
A: The maximum tokens (prompt + response) a model can attend to in one call (~128k for GPT-4o). Exceeding it truncates or fails, which is why long documents are chunked.

**Q: Temperature and top_p?**
A: Temperature scales sampling randomness: 0 = greedy/deterministic, higher = more diverse. top_p (nucleus sampling) restricts sampling to the smallest token set whose cumulative probability exceeds p. I use temperature 0 for stable extraction/scoring.

**Q: System vs user prompt?**
A: The system prompt sets role, rules, and output format (persistent); the user message carries the input data. Here the JSON schema and scoring rules live in the system prompt; the JD and resume go in the user message.

**Q: Zero-shot vs few-shot?**
A: Zero-shot = instructions only. Few-shot = include example input/output pairs to steer format. The agents are mostly zero-shot with strict schemas; few-shot would harden trickier formatting.

**Q: Hallucination and how to reduce it?**
A: Confident but ungrounded output. Reduce with RAG grounding, temperature 0, strict validated schemas, "say you do not know" instructions, and a human backstop.

**Q: Fine-tuning vs RAG vs prompting?**
A: Prompt first (cheap, instant). RAG when the model needs external/changing/proprietary knowledge (my rubrics, comp data). Fine-tune to bake in consistent style/behavior with labeled data. RAG injects knowledge at inference; fine-tuning changes weights.

**Q: Structured output / function calling?**
A: Getting machine-parseable JSON instead of prose. I enforce it with schema-in-prompt + parsing + Pydantic; the more robust path is the provider's native structured-output API that constrains generation to a schema.

**Q: What is an embedding? Chat vs embedding model?**
A: An embedding is a fixed-length vector capturing text meaning (1536-d here); similar texts land near each other. A chat model generates text; an embedding model only vectorizes. RAG uses both.

---

## 20. RAG & Retrieval Concepts (deep)

**Q: What is RAG and why does it exist?**
A: Retrieval-Augmented Generation: retrieve relevant documents at query time and put them in the prompt so the model answers from current, proprietary, factual context. It solves stale knowledge, hallucination, and private-data access.

**Q: Why chunk, and the tradeoff?**
A: Embeddings represent bounded text well, and you cannot exceed the context window when stuffing results. Chunking gives focused units. Too small loses context, too large dilutes relevance and costs tokens. 500/100 is a balanced default.

**Q: How does similarity search work?**
A: Embed the query into the same space, then find chunks whose vectors are closest by a metric. Cosine similarity compares the angle (meaning/direction), ignoring magnitude, which suits text embeddings.

**Q: Cosine vs dot product vs Euclidean?**
A: Cosine = normalized dot product (orientation, length-robust). Dot product factors magnitude. Euclidean is straight-line distance. For normalized embeddings cosine and dot rank the same; cosine is the default.

**Q: What is ANN / HNSW?**
A: Approximate Nearest Neighbor search. Exact search over millions of vectors is slow, so vector DBs use index structures like HNSW (a navigable small-world graph) to find near-neighbors in roughly log time with high recall. Pinecone handles this internally.

**Q: top-k choice?**
A: Number of nearest chunks retrieved. Too low misses context, too high adds noise and cost. I use 5 then LLM-grade for relevance, so k stays modest while precision stays high.

**Q: Reranking, bi- vs cross-encoder?**
A: A bi-encoder embeds query and doc separately (fast first-stage retrieval). A cross-encoder reads query+doc together for a sharper relevance score (slower, so you run it only on the retrieved candidates). I added one ([memory/agentic_rag.py](../memory/agentic_rag.py), `_rerank`): retrieve a wide pool (12) from Pinecone, rerank with `bge-reranker-v2-m3` via Pinecone's hosted inference API (a real cross-encoder, no extra key or local model), then narrow to the top 5 before grading. On my eval set this lifted both ranking (MRR 0.742 -> 1.000) and recall (0.833 -> 0.979): retrieve-wide/rerank-narrow recovers chunks the embedding left outside the top 5, e.g. it ranked the senior salary band below the senior *definition* for a salary query and the reranker pulled it to rank 1. Falls back to the original order on any failure.

**Q: Hybrid search?**
A: Fuse dense (embedding) and sparse keyword (BM25) retrieval. Dense catches semantics, sparse catches exact terms/IDs/rare words. Mine is dense-only; hybrid would help exact-skill matching.

**Q: How do you evaluate RAG?**
A: I built a runnable eval harness ([eval/run_eval.py](../eval/run_eval.py)) over a labeled dataset of 27 rubric chunks and 20 queries tagged by failure mode ([eval/dataset.py](../eval/dataset.py)): single, distractor, multi-relevant, paraphrase, exact-term, and out-of-domain negatives. It measures retrieval (recall@k, precision@k, MRR vs the labels) and generation (faithfulness/groundedness, answer relevance via LLM judge), plus rejection/abstention on the negatives, indexing into a throwaway Pinecone namespace and cleaning up after. The first run found two weaknesses and I fixed both: (1) multi-relevant recall capped at 0.83 by top_k=5 -> fixed by retrieve-wide(12)/rerank-narrow(5), lifting overall recall 0.833 raw -> 0.979; (2) the strict "answer only from context" prompt over-abstained on paraphrases (career break vs employment gap) -> fixed by allowing synonym bridging while still abstaining on absent info, recovering paraphrase relevance 2.3 -> 3.7 without breaking the 100% out-of-domain rejection. Final: recall 0.979, MRR 1.000 with reranker, faithfulness 4.50, relevance 4.75, 100% rejection + abstention on out-of-domain.
Concept: separate retrieval metrics (did you fetch and rank the right chunks?) from generation metrics (given context, is the answer grounded and on-topic?). The paraphrase miss looked like a retrieval failure but was a generation failure - you only see that by measuring the two separately.

---

## 21. LangChain vs LangGraph & Internals

**Q: LangChain vs LangGraph?**
A: LangChain is a library of building blocks (model wrappers, prompts, tools, retrievers, chains). LangGraph is an orchestration framework for stateful, cyclic, multi-actor workflows with checkpointing and interrupts. Chains are linear/stateless; graphs are stateful and can loop, branch, and pause. I use LangChain for model calls and LangGraph for the pipeline.

**Q: Core LangGraph primitives?**
A: State (typed shared dict), Nodes (functions returning partial updates), Edges (control flow), conditional edges (branch on state), a Checkpointer (persist per thread), and interrupts (pause). My graph: linear nodes with `interrupt_before` ([graph/pipeline.py:149](../graph/pipeline.py#L149)).

**Q: How does state update across nodes?**
A: Each node returns a partial dict; LangGraph merges it. By default keys overwrite; you can define reducers (e.g. append to a list) for custom merges. Returning only changed keys keeps nodes decoupled.

**Q: What is the checkpointer and why does it matter?**
A: It persists full graph state after each step, keyed by thread_id, making runs durable and resumable across process restarts. I use `MongoDBSaver` ([memory/checkpointer.py:15](../memory/checkpointer.py#L15)).

**Q: What exactly does interrupt_before do? And invoke(None)?**
A: `interrupt_before` stops execution just before a listed node, returning control with state checkpointed. `invoke(None)` resumes the existing run from its last checkpoint instead of starting fresh ([graph/pipeline.py:180](../graph/pipeline.py#L180)).

---

## 22. Observability & Evaluation Concepts

**Q: What is observability for LLM apps and why is it different?**
A: Seeing exactly what the system did: every prompt, response, token count, latency, cost, and error as a trace tree. It differs from normal observability because the logic lives in opaque model calls and natural-language prompts, so you must capture the precise inputs/outputs of each call to debug non-deterministic, multi-step behavior.

**Q: Trace vs span/run?**
A: A trace is the full tree for one top-level invocation (a pipeline run). Each node is a run/span (an LLM call, chain, retriever, or custom function), nested to show the hierarchy, carrying timing, tokens, cost, inputs, outputs.

**Q: What is an eval, and LLM-as-judge?**
A: An eval scores outputs against expectations. With no exact ground truth you use LLM-as-judge: an LLM scores another's output against a rubric (relevance, faithfulness). Cheap and scalable, needs calibration against human labels. My relevance grader is an inline LLM-as-judge.

**Q: What would you track in production?**
A: Token cost per run/agent, latency (p50/p95), error rate, retrieval relevance rate, retry/fallback frequency, and validation-failure rate. Alert on cost spikes and failure-rate jumps.

---

## 23. Backend / Data Concepts

**Q: Why FastAPI?**
A: Async-first, automatic OpenAPI docs, and native Pydantic validation. The async model suits an I/O-bound app dominated by LLM/DB network calls. Routers are wired in [api/main.py:56](../api/main.py#L56); CORS at [L47](../api/main.py#L47).

**Q: What does Pydantic give you?**
A: Runtime validation and parsing at the boundaries. Agent outputs and API requests validate against typed models ([models/pipeline.py:77](../models/pipeline.py#L77)+), so malformed LLM JSON or bad input is caught early, and enums constrain fields to legal values.

**Q: Why stateless, and why does it matter?**
A: No per-request state in the process; everything is in Mongo/Pinecone. Any instance can serve any request, so it scales horizontally and survives restarts. The LangGraph checkpoint enables long workflows without in-memory state.

**Q: How are secrets handled?**
A: Env vars, gitignored `.env` locally, set in the host dashboard in prod, never committed. Hardening would add a secrets manager and key rotation.

---

## 24. Glossary (one-line definitions)

- LLM: transformer predicting the next token; powers the agents.
- Token: ~0.75 word; billing and context unit.
- Context window: max tokens per call (~128k for GPT-4o).
- Temperature: sampling randomness; 0 = deterministic (used here).
- Embedding: vector of text meaning (1536-d).
- Vector DB: stores embeddings, does nearest-neighbor search (Pinecone).
- Cosine similarity: angle-based closeness metric.
- ANN / HNSW: fast approximate nearest-neighbor search.
- Namespace: hard partition in a Pinecone index; the tenant boundary.
- RAG: retrieve docs, then generate grounded on them.
- Chunking: splitting docs into embeddable units (500w/100 overlap).
- Reranking: cross-encoder re-scoring of retrieved chunks.
- Agent: goal-directed system using tools and adapting.
- ReAct: reason-then-act tool loop.
- Reflection: self-evaluation and correction (the doc grader).
- LangChain: LLM building-block library.
- LangGraph: stateful graph orchestration with checkpoints + interrupts.
- Checkpointer: persists graph state per thread (MongoDBSaver).
- interrupt_before: pause before a node for human input (HITL).
- HITL: human-in-the-loop approval gates.
- Structured output: model returns schema-valid JSON.
- Hallucination: confident but ungrounded output.
- Multi-tenancy: per-user data isolation (email-scoped namespaces).
- Observability/tracing: recording every call as a structured run (LangSmith).
- Span/run: one node in a trace tree.
- LLM-as-judge: an LLM scoring another's output (the grader).
- Eval: scoring outputs against expectations, ideally in CI.
- Idempotent: same input gives same effect (content-hash vector IDs).
