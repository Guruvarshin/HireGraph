# HireGraph — 5-Minute Cheat Sheet

Read this right before the interview. Skim top to bottom.

---

## ONE-LINER
> A multi-agent AI recruiting pipeline: 5 LLM agents orchestrated as a LangGraph state machine, with 5 human-in-the-loop checkpoints, agentic self-correcting RAG over Pinecone, and per-user multi-tenancy.

## STACK (memorize the table)
| Layer | Tech |
|---|---|
| Orchestration | **LangGraph** (StateGraph + `interrupt_before`) |
| LLM | **GPT-4o** (agents), **GPT-4o-mini** (RAG grader/rewriter) |
| Vector DB | **Pinecone** (per-user namespaces) |
| Embeddings | **OpenAI text-embedding-3-small** (1536-d) |
| Reranker | **bge-reranker-v2-m3** cross-encoder (Pinecone inference) |
| Guardrails | **AWS Bedrock Guardrails** (resume injection block + PII, optional) |
| Eval | recall@k · precision@k · MRR · LLM-judge faithfulness/relevance |
| Backend | **FastAPI** |
| Frontend | **Next.js 15** |
| DB / Checkpoints | **MongoDB Atlas** (`MongoDBSaver`) |
| Auth | **Google OAuth** (sign-in only) |
| Email | **Brevo HTTP API** (was Gmail SMTP — Railway blocks SMTP) |
| Calendar | **.ics attachments** |
| Web fallback | **Tavily** |
| Observability | **LangSmith** (auto-trace + `@traceable` spans) |
| Deploy | **Railway** (backend, Docker) · **Vercel** (frontend) |

---

## THE 5 AGENTS (in order)
1. **JD Parser** → structured JD (title, skills, seniority, salary, contradictions)
2. **Resume Screener** → score 0-100 on 4 dims + bias flags + shortlist y/n
3. **Interview Planner** → 3-4 tailored rounds w/ candidate-specific questions
4. **Interview Evaluator** → synthesize feedback → hire/no-hire + confidence
5. **Offer Drafter** → salary (from comp band) + full offer letter

**4 screening dimensions:** skills_match, experience_relevance, seniority_signal, resume_quality.

---

## PIPELINE FLOW
```
jd_parser → resume_screener → [shortlist_review*] → interview_planner →
[finalist_review*] → [awaiting_feedback*] → interview_evaluator →
[offer_candidates_review*] → offer_drafter → [offer_review*] → send_offers → END
```
`*` = the **5 interrupt_before checkpoints** (human approves/edits, then resume).

---

## AGENTIC RAG LOOP (know this cold)
**Rewrite → Retrieve → Rerank → Grade → Retry → Web-fallback**
1. Rewrite: LLM makes query keyword-dense (new terms on retry)
2. Retrieve: Pinecone **wide pool top_k=12** in user's namespace
3. Rerank: **cross-encoder** `bge-reranker-v2-m3` (Pinecone inference) reorders, **narrow to top 5**
4. Grade: LLM scores each chunk relevant y/n (JSON) — **reflection**
5. Retry: if <1 relevant, rewrite w/ new terms (**max 2 attempts**)
6. Fallback: Tavily web search → **graded by same judge** → index kept ones

**Decide gate — REMOVED.** Had an LLM "need retrieval?" gate; trace showed it misrouting salary as general knowledge and skipping the offer drafter's rubric lookup. All callers are grounding calls that always need the rubric, so I dropped it → retrieval always runs. Story point: found it via the LangSmith trace.

**Still agentic?** Yes — agentic = reflection (grade) + adaptive iteration (rewrite+retry) + tool use (web fallback). All intact. Decide was a one-shot router, the weakest agentic signal.
  
**Why agentic > naive:** naive returns garbage silently → hallucination. Loop self-corrects → grounded.

**Reranker (real cross-encoder, not LLM):** bi-encoder embeddings rank query/chunk independently → can put topically-similar chunk above the answer. Cross-encoder reads query+chunk together → sharper. **Retrieve-wide(12)/rerank-narrow(5) lifts recall too, not just ranking: eval recall 0.833→0.979, MRR 0.742→1.000.** Runs only on the pool (cross-encoders slow). No extra key/dep — Pinecone hosted.

**Web fallback gating (`allow_web_fallback`):** OFF for proprietary rubric lookups (jd/screener/planner) — generic web ≠ company's bar, so score without rubric instead of being misled. ON (default) only for salary (public market data). Web results graded by the same `_grade_docs`, not trusted on Tavily ranking.

---

## KEY NUMBERS
- top_k = **5**
- chunk = **500 words / 100 overlap**
- embeddings = **1536-d**
- retries = **2**, min relevant = **1**
- checkpoints = **5**, agents = **5**
- temperature = **0** (deterministic JSON)

---

## MULTI-TENANCY (one breath)
Full email → sanitized → Pinecone namespace prefix:
`guruvarshinib_ai_gmail_com__company_rubrics`
Namespaces = hard isolation, free, no leak. Mongo runs scoped by `user_id` + 403 check on every read. **Full email, not domain** (gmail users would collide). One unified `company_rubrics` namespace holds rubric **and** salary bands.

---

## STATE / CHECKPOINTING
- `PipelineState` = TypedDict, flows through nodes.
- **Two stores:** LangGraph checkpoint (`lg_checkpoints`, source of truth, enables pause/resume) + `pipeline_runs` doc (denormalized, for UI listing) — CQRS split. **Delete gotcha:** `DELETE /pipeline/{id}` (ownership-checked) must clear BOTH stores + `lg_checkpoint_writes`; the old helper only cleared the summary → orphaned checkpoints. Lesson: denormalized copies mean deletes fan out.
- Key = **thread_id (UUID)**.
- Resume = `update_state(edits)` then `invoke(None)` (None = continue from checkpoint).
- Pydantic validates at edges; plain dicts in state.

---

## HITL — WHY & WHERE
**Why:** decisions are consequential + legally sensitive (rejections, offers, salary). "AI proposes, human disposes."
**Where:** shortlist, finalist/plans, real interview feedback, who-gets-offers, offer/salary approval.
Durable checkpoint = can resume **days later**.

---

## SHARP "WHY" ANSWERS
- **Why LangGraph?** Typed shared state + durable checkpoint + interrupt = HITL. Raw chains can't pause/resume.
- **Why multi-agent?** Focused prompts, per-stage error handling, natural HITL boundaries, swappable.
- **Why temp 0?** Stable scores + stable JSON.
- **Why GPT-4o-mini for grading?** Cheap, high-volume, simple.
- **Why namespaces (not metadata/separate indexes)?** Free + hard isolation + no per-index cost.
- **Why full email tenant?** Domain collides personal Gmail + different teams want different rubrics.
- **Why Brevo HTTP API (not SMTP)?** Railway blocks SMTP ports; HTTP API sends over 443. Single-sender verification keeps a Gmail from-address, no domain, no Google verification.
- **Why .ics not Calendar API?** No sensitive scope, works on any calendar.
- **Why drop gmail/calendar scopes?** Restricted/sensitive → forces weeks of Google verification.
- **Why Mongo not Postgres?** Nested flexible JSON + free LangGraph checkpointer.
- **Why LangSmith?** All calls go through LangChain/LangGraph → auto-traced via env vars, zero code. Essential for debugging multi-step agentic flows.

---

## GOTCHAS / WAR STORIES
- **Offer date was 2023:** GPT has no "now" → inject `Today's date` into prompt.
- **JSON in markdown fences:** `_extract_json` regex strips ```` ``` ```` → `json.loads` → Pydantic.
- **One bad resume:** per-candidate try/except → partial results + error_message.
- **Bias flags:** screener flags (name/prestige/gap bias) but does NOT auto-reject; ignores gaps<threshold, bootcamps, foreign unis.
- **Idempotent upload:** vector ID = content-hash, dupes overwrite.
- **Email saga (great story):** Gmail API → tried Gmail SMTP → on Railway it hung 1 min (`Errno 101`, both 587+465 timeout) = **host blocks outbound SMTP**. Proof: yesterday's working emails were the OLD Gmail/Calendar **API** (HTTPS 443), not SMTP. Fix → **Brevo HTTP API** (port 443, single-sender verification = send from Gmail to anyone, free 300/day). *Lesson: this is why transactional-email APIs exist — clouds block SMTP.*

---

## OBSERVABILITY — LANGSMITH (know this)
- **How:** set 4 env vars (`LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`, `LANGCHAIN_ENDPOINT`) → LangChain auto-traces **every** LLM/agent/graph call via its callback system. **Zero code** for basic tracing.
- **Enriched:** `@traceable` on every stage → named nested spans: each agent (`Agent 1-5`), each per-candidate op (`Score candidate`), and the RAG loop (rewrite→retrieve→rerank→grade), incl. the **Pinecone** step LangChain wouldn't trace. No-op fallback if langsmith absent.
- **Metadata/tags** in graph config → filter traces by `thread_id` (debug one run).
- **A trace = a tree:** root (graph) → agent nodes → exact prompt+response, tokens, $, latency per LLM call.
- **Used for:** debugging ("why score 30?" → read the actual prompt), cost per run/agent, latency, RAG quality (did retrieval retry/fallback?).
- **Dev vs prod:** same API key, different `LANGCHAIN_PROJECT` (hiregraph-dev / hiregraph-prod). Traces ship over HTTPS, async/non-blocking, fail silently → never breaks the app. Works local AND on Railway.

---

## AGENTIC THEORY (if asked)
- **Is it agentic?** Yes — RAG loop = reflection (grading) + adaptive iteration (rewrite+retry) + tool use (Pinecone, Tavily). Multi-agent decomposition. (Removed the decide/route gate; reflection+iteration+tool-use are the real agentic markers, all intact.)
- **Structured vs autonomous?** Chose structured graph for reliability, checkpointing, HITL, debuggability. Autonomous = unpredictable for high-stakes flow.
- **Patterns present:** tool use, reflection, query rewrite-retry, routing, multi-agent handoff.
- **Add a planner:** orchestrator node picks stages dynamically via conditional edges.

---

## IF ASKED "HOW IMPROVE IT"
Parallelize per-candidate calls (asyncio) · model-agnostic provider layer · fairness-critic agent · wire eval harness into CI · JWT sessions (not email header) · streaming to UI · dynamic graph routing. (Already done: cross-encoder reranker, eval harness, LangSmith tracing, Bedrock Guardrails injection+PII defense, web-fallback grading.)

---

## KNOWN WEAKNESSES (own them confidently)
- `X-Recruiter-ID` email header is spoofable → would use signed JWT.
- Per-candidate LLM calls are sequential → would parallelize.
- Eval harness built + run across all failure modes; **found 2 weaknesses and fixed both** (multi-recall via retrieve-wide/rerank-narrow 0.83→0.92; paraphrase over-abstention via synonym-bridging prompt 2.3→3.7) → next is wiring it into CI.
- Prompt-injection via resume → **defended in depth at ingestion**: (1) **AWS Bedrock Guardrails** = security layer — injection detected → resume NOT sent to any LLM (filename + flag only); else PII anonymized (name/email kept). **Mandatory + fail-closed in prod** (`GUARDRAIL_REQUIRED`, published version, retries); optional/fail-open in dev. (2) **LLM parser** = extraction layer — pulls name/email (guardrail can't; needed to email candidates) + structures resume; restating in own words also neutralizes residual injection when guardrail is off. + schema validation + HITL backstop.
- Bias flags are LLM-self-reported → would add an independent guardrail/critic.

---

## MOST-PROUD-OF (closing line)
> The resumable human-in-the-loop architecture — a multi-day, stateful agentic workflow that pauses for human judgment and resumes from a durable checkpoint, with strict tenant isolation throughout. That's the part that mirrors real production agentic systems.

---

## LIVE WALKTHROUGH (full script: `docs/WALKTHROUGH.md`)
**Pre-call:** warm the Railway backend (~40s cold start), have JD + resumes ready, open live app + repo + editor + terminal + LangSmith, pre-run one clean pipeline for a fresh trace, have `python eval/run_eval.py` ready.

**Arc (30 min):** frame (2m) → live demo + HITL pause (5m) → **LangSmith trace drill-down** (9m) → AI-first process story (2m) → follow-ups (rest).

**Trace drill-down (the core):** show it as a named tree, then drill:
`Pipeline → Agent 2: Resume Screener → Score candidate` (show input resume+rubric, output score) → expand `agentic_rag.query` (rewrite→retrieve→**rerank**→grade) → click a `ChatOpenAI` span (exact prompt, tokens, cost). Progression = **stages → one candidate's I/O → RAG loop → raw LLM call**.

**Then run eval live:** metrics print → "it found 2 weaknesses, I fixed both, re-measured: recall 0.83→0.98, MRR→1.0, 100% out-of-domain abstention."

**AI-first story (their core ask):** "plan-first, AI as a reviewed junior, not autocomplete" → reranker slop I rejected + the "don't call AI on detected injection" review comment.

**On "I don't know":** "haven't done X in prod; here's how I'd find out: [measure/try]." Never bluff TTFT/streaming/fine-tuning.

**Closer:** "I don't just build agents, I build the measurement loop and guardrails that make them trustworthy, plan-first with AI as a reviewed collaborator."
