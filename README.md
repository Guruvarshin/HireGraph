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

1. Rewrite: reformulate the query for better vector search (different terms on a retry)
2. Retrieve: query Pinecone for a wide candidate pool (top-k 12)
3. Rerank: reorder with a cross-encoder (`bge-reranker-v2-m3`, served by Pinecone inference) and narrow to the top 5, so chunks the embedding ranked lower but that actually answer the query are pulled in
4. Grade: an LLM scores each retained chunk for relevance (reflection)
5. Retry: if results are weak, rewrite with different terminology (capped at 2 attempts)
6. Fallback: web search via Tavily if the vector DB returns nothing (also graded; gated per query so proprietary rubric lookups never fall back to generic web data)

Every caller is a grounding call that has already decided it needs the rubric, so retrieval always runs. (An earlier "decide whether to retrieve" gate was removed after tracing showed it wrongly classifying salary as general knowledge and skipping the offer drafter's pay-band lookup.) The loop stays agentic through its defining traits: reflection (grading its own results), adaptive iteration (rewrite-and-retry), and tool use (web-search fallback).

## Evaluation

The `eval/` folder contains a runnable RAG evaluation against a labeled dataset. It indexes a small corpus into a temporary Pinecone namespace, measures retrieval quality (recall@k, precision@k, MRR vs ground-truth relevant ids) and generation quality (faithfulness and answer relevance via an LLM judge), then cleans up.

```
python eval/run_eval.py
```

Latest run over 27 documents and 20 queries spanning all failure modes (single, distractor, multi-relevant, paraphrase, exact-term, out-of-domain):

```
Recall@5 (raw):      0.833
Recall@5 (+ rerank): 0.979
MRR (raw):           0.742
MRR (+ reranker):    1.000
Faithfulness/5:      4.50
Answer relevance/5:  4.75
Out-of-domain:       100% rejection, 100% abstention (no hallucination)
```

Retrieving a wide pool then reranking improves recall (not just ranking) by pulling in relevant chunks the embedding left outside the top 5; out-of-domain queries are correctly rejected rather than answered.

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
