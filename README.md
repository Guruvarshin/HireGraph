# HireGraph - AI Recruiting Pipeline

An end-to-end AI recruiting pipeline that automates resume screening, interview planning, candidate evaluation, and offer drafting, with human review at every stage.

## What it does

Upload a job description and candidate resumes. HireGraph runs a multi-agent pipeline built on LangGraph, pausing at key stages for recruiter approval before proceeding.

```
JD Parsing -> Resume Screening -> Shortlist Review (human) ->
Interview Planning -> Finalist Review (human) -> Awaiting Feedback (human) ->
Interview Evaluation -> Offer Candidates Review (human) ->
Offer Drafting -> Offer Review (human) -> Send Offers
```

## Tech Stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph (StateGraph with interrupt checkpoints) |
| LLM | GPT-4o (agents), GPT-4o-mini (RAG grader/rewriter) |
| Vector DB | Pinecone (per-user namespaces, multi-tenant) |
| Embeddings | OpenAI text-embedding-3-small |
| Reranker | Cross-encoder bge-reranker-v2-m3 (Pinecone inference) |
| Guardrails | AWS Bedrock Guardrails (resume injection + PII, optional) |
| Backend | FastAPI |
| Frontend | Next.js 15 |
| Database | MongoDB Atlas (pipeline state and LangGraph checkpoints) |
| Auth | Google OAuth 2.0 (sign-in only, non-sensitive scopes) |
| Email | Brevo HTTP API |
| Calendar invites | .ics attachments |
| Observability | LangSmith |
| Web search fallback | Tavily |

## Agents

- JD Parser: extracts structured fields from raw job description text
- Resume Screener: scores each candidate on four dimensions against the JD and company rubric
- Interview Planner: designs tailored interview rounds per candidate
- Interview Evaluator: synthesizes interviewer feedback into a hire/no-hire recommendation
- Offer Drafter: drafts an offer letter with salary justified against the company's compensation bands

## Resume Ingestion and Prompt-Injection Defense

Defense in depth across two layers:

1. **AWS Bedrock Guardrails** ([utils/guardrails.py](ai-recruiting-pipeline/utils/guardrails.py)) screens the raw resume text at upload via the `ApplyGuardrail` API (published guardrail version, with a short retry on transient errors). If a prompt-injection or manipulation attempt is detected, the resume is **not sent to any LLM at all** - it is surfaced with only the filename and a `[SECURITY: ...review manually]` flag, so attacker-controlled text never reaches the parser or the agents. Otherwise sensitive PII (SSN, card, bank, address, phone) is anonymized while name and email pass through (the pipeline needs them to contact candidates). Behavior is controlled by `GUARDRAIL_REQUIRED`: in production it is **mandatory and fail-closed** (an upload is rejected if it cannot be screened); in local dev it is optional and fail-open (skipped when no AWS credentials are present).

2. **LLM extraction + summarization** ([utils/resume_parser.py](ai-recruiting-pipeline/utils/resume_parser.py)) then pulls the candidate's name and email (which the pipeline needs to send invites and offers, and which the guardrail does not extract) and rewrites each clean resume into a neutral, factual summary the agents reason over. Restating the text in the model's own words also neutralizes any residual injection, which keeps the app safe when the optional guardrail layer is disabled. A mechanical redaction fallback is used if the parser is unavailable.

## Multi-Tenancy

Each recruiter gets an isolated Pinecone namespace scoped to their full email, so two users at the same company never share a knowledge base:

```
guruvarshinib_ai_gmail_com__company_rubrics
```

A single `company_rubrics` knowledge base per user holds everything the agents need: hiring standards, seniority levels, interview process, and salary bands. Pipeline state in MongoDB is scoped by `user_id`, and every read checks ownership.

## RAG (Agentic Retrieval)

The `AgenticRAG` class implements a self-correcting, multi-step retrieval loop:

1. Retrieve on the original query first (the caller's own wording matches the corpus best); rewrite with different terminology only on a retry, after tracing showed rewrites drifting toward vocabulary absent from the rubric
2. Retrieve: query Pinecone for a wide candidate pool (top-k 20)
3. Rerank: reorder with a cross-encoder (`bge-reranker-v2-m3`, served by Pinecone inference) and narrow to the top 5. Measured effect: this significantly improves **ranking** (MRR +0.096, 95% CI [0.047, 0.146]); on the eval corpus it does **not** measurably improve recall, because the embedding already retrieves the gold chunk into the top 5 ~97% of the time (see Evaluation)
4. Grade: an LLM scores each retained chunk for relevance (reflection)
5. Retry: if results are weak, rewrite with different terminology (capped at 2 attempts)
6. Fallback: web search via Tavily if the vector DB returns nothing (also graded; gated per query so proprietary rubric lookups never fall back to generic web data)

Chunking is recursive: documents are split on structural boundaries (`SECTION` headers, rule lines, paragraphs) rather than a fixed word window, and each sub-chunk carries its section header so the tail of a long section is still attributable to it.

Every caller is a grounding call that has already decided it needs the rubric, so retrieval always runs. An earlier "decide whether to retrieve" gate was removed — not because it was buggy, but because it was **redundant**: every call site into the RAG layer needs the rubric, so the gate's correct answer is always "yes". A component whose correct output is a constant can only add an LLM call, latency, and a false-negative failure mode (tracing caught it skipping the offer drafter's pay-band lookup). The loop stays agentic through its defining traits: reflection (grading its own results), adaptive iteration (rewrite-and-retry), and tool use (web-search fallback).

## Evaluation

The `eval/` folder contains a runnable RAG evaluation against a labeled dataset of **60 chunks and 200 queries** spanning six failure modes (single, distractor, multi-relevant, paraphrase, exact-term, out-of-domain). It indexes the corpus into a temporary Pinecone namespace, measures retrieval quality (recall@k, MRR vs ground-truth ids) and generation quality (faithfulness, answer relevance via an LLM judge), then cleans up.

```
python eval/run_eval.py          # reports the held-out TEST split
python eval/run_eval.py --dev    # DEV split, for tuning
python eval/run_eval.py --all    # both + the full set
```

**Methodology.** Config (`TOP_K`, `RETRIEVE_K`) is imported from the app so the eval cannot drift from what production runs. Queries are split **dev/test, stratified by failure mode with a fixed seed** — tuning happens on dev, the test split is reported once with the config frozen. Every aggregate carries a **95% bootstrap CI**, and rerank deltas use a **paired** bootstrap, so no improvement is claimed without error bars.

Held-out TEST split (n=99: 89 answerable, 10 out-of-domain):

```
Recall@5 (raw):      0.968  [0.930, 0.997]
Recall@5 (+rerank):  0.985  [0.966, 1.000]
  -> rerank delta:   +0.017 [-0.014, 0.056]   no effect (CI spans 0)
MRR (raw):           0.885  [0.828, 0.940]
MRR (+rerank):       0.980  [0.955, 1.000]
  -> MRR delta:      +0.096 [0.047, 0.146]    SIGNIFICANT
Faithfulness/5:      4.15   [3.83, 4.46]
Answer relevance/5:  4.65   [4.42, 4.87]
Out-of-domain:       100% rejection, 100% abstention (no hallucination)
```

**What this shows, honestly.** The cross-encoder significantly improves **ranking** (MRR +0.096), but on this corpus it does **not** measurably improve recall — the delta's confidence interval spans zero. That is a ceiling effect: retrieving 20 of 60 chunks, the bi-encoder already lands the gold chunk in the top 5 about 97% of the time, leaving no headroom. The reranker earns its place in the two places the corpus is genuinely hard: **paraphrase** recall (0.867 → 1.000) and **distractor** MRR (0.782 → 0.943, ordering among near-duplicate India/USA/UK bands). It has a real cost too — on multi-gold queries reranking can evict a relevant chunk (recall 0.942 → 0.908). Out-of-domain queries are rejected and abstained on 100% of the time; for a grounded system, correctly declining is the metric that matters most.

`Precision@5` is reported by the harness but is not meaningful here: it is mechanically capped (a single-gold query at k=5 maxes out at 0.2), so it measures gold-set size, not quality.

**Limitations.** This is a synthetic, self-authored benchmark — the corpus and queries share lexical priors with the chunker, so absolute numbers are optimistic. It is a **regression benchmark**, not evidence of real-world generalization. Making it defensible would mean sourcing queries from real usage traces and having relevance labeled by someone who did not build the retrieval. An earlier version of this README quoted `recall 0.833 -> 0.979` from a 20-query set that had been tuned against; that number did not survive a held-out split and has been retracted.

## Email and Calendar

Email is sent through the Brevo HTTP API over HTTPS, which works on cloud hosts that block outbound SMTP ports. A verified Brevo sender lets the app send from a Gmail address to any recipient without owning a domain. Interview invites go to both the candidate and each interviewer, with one `.ics` calendar attachment per scheduled round that recipients can add to any calendar. Replies route back to the recruiter via the Reply-To header.

Google OAuth is used only for sign-in (non-sensitive scopes), so the app needs no Google verification.

## Observability

The pipeline is instrumented with LangSmith. Because all calls run on LangChain and LangGraph, every LLM, agent, and graph call is traced automatically once the `LANGCHAIN_*` environment variables are set. Every stage is additionally annotated with named `@traceable` spans so a single run reads as a readable tree: each agent (`Agent 1: JD Parser` ... `Agent 5: Offer Drafter`), each per-candidate operation (`Score candidate`, `Plan candidate interview`, `Draft offer`), and each step of the agentic RAG loop (`rag.decide_retrieve`, `rag.rewrite_query`, `rag.pinecone_retrieve`, `rag.rerank`, `rag.grade_docs`). Every span exposes its inputs and outputs, and each run is tagged with its `thread_id` so traces can be filtered to a single pipeline.

## Project Structure

```
agents/          Five LangGraph agent nodes
api/             FastAPI routes (auth, pipeline, rag, setup)
eval/            RAG evaluation harness (recall@k, precision@k, MRR, LLM-judge)
graph/           LangGraph pipeline definition and checkpoint config
memory/          AgenticRAG, MongoDB checkpointer, database helpers
models/          Pydantic models for all pipeline state types
prompts/         System prompts for each agent
scripts/         Setup and health check scripts
ui/              Next.js frontend
utils/           Resume parser (summarize + injection defense), email client
```

## Running Locally

### Prerequisites
- Python 3.11+
- Node.js 18+
- MongoDB Atlas cluster
- Pinecone serverless index (1536 dims, cosine)
- OpenAI API key
- Google OAuth 2.0 credentials (sign-in only)
- A Brevo account with a verified sender and an API key
- A LangSmith API key (optional, for tracing)

### Backend

```bash
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\python.exe -m pip install -r requirements.txt

# Verify services
.venv\Scripts\python.exe scripts/setup.py

# Start the server
.venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd ui
npm install
npm run dev
```

Open `http://localhost:3000`. Sign in with Google, upload your company rubric, then start a pipeline.

### Environment Variables

Copy `.env.example` to `.env` and fill in the values. Key groups: OpenAI, LangSmith, MongoDB, Pinecone, Google OAuth, Brevo email, and Tavily.

## Deployment

- Backend: Railway (Docker, builds from the `Dockerfile`; `railway.toml` defines the health check). Set all environment variables in the Railway dashboard, including `BREVO_API_KEY`, `GMAIL_ADDRESS`, and the `LANGCHAIN_*` keys. `GOOGLE_REDIRECT_URI` must point to the deployed URL and be registered in the Google Cloud Console.
- Frontend: Vercel. Set `NEXT_PUBLIC_API_URL` to the backend URL.

A `render.yaml` blueprint is also included as an alternative Docker deployment on Render.

## Human-in-the-Loop Checkpoints

The LangGraph pipeline uses `interrupt_before` to pause at five stages:

| Stage | What the recruiter does |
|---|---|
| `shortlist_review` | Approve or reject screened candidates |
| `finalist_review` | Approve interview plans, fill in interviewer emails |
| `awaiting_feedback` | Submit real interview feedback |
| `offer_candidates_review` | Select which candidates receive offers |
| `offer_review` | Approve or modify offer letters before sending |
