# HireGraph — AI Recruiting Pipeline

An end-to-end AI recruiting pipeline that automates resume screening, interview planning, candidate evaluation, and offer drafting — with human-in-the-loop review at every stage.

## What it does

Upload a job description and candidate resumes. HireGraph runs a multi-agent pipeline powered by GPT-4o and LangGraph, pausing at key stages for recruiter approval before proceeding.

```
JD Parsing → Resume Screening → Shortlist Review (human) →
Interview Planning → Finalist Review (human) → Awaiting Feedback (human) →
Interview Evaluation → Offer Candidates Review (human) →
Offer Drafting → Offer Review (human) → Send Offers
```

## Tech Stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph (StateGraph with interrupt checkpoints) |
| LLM | GPT-4o (agents), GPT-4o-mini (RAG grader) |
| Vector DB | Pinecone (per-user namespaced, multi-tenant) |
| Embeddings | OpenAI text-embedding-3-small |
| Backend | FastAPI + Python |
| Frontend | Next.js 15 |
| Database | MongoDB Atlas (pipeline state + LangGraph checkpoints) |
| Auth | Google OAuth 2.0 |
| Email / Calendar | Gmail API + Google Calendar API |
| Web search fallback | Tavily |

## Agents

- **JD Parser** — extracts structured fields from raw job description text
- **Resume Screener** — scores each candidate on 4 dimensions against the JD and company rubric
- **Interview Planner** — designs tailored interview rounds per candidate
- **Interview Evaluator** — synthesizes interviewer feedback into a hire/no-hire recommendation
- **Offer Drafter** — drafts a full offer letter with salary justified against company comp bands

## Multi-Tenancy

Each recruiter gets isolated Pinecone namespaces scoped to their email:

```
guruvarshini_gmail_com__company_rubrics
```

Knowledge base documents (hiring rubrics, comp bands) are private per user. Pipeline state in MongoDB is scoped by `user_id`.

## RAG (Agentic Retrieval)

The `AgenticRAG` class implements a multi-step retrieval loop:

1. **Decide** — should retrieval even happen for this query?
2. **Rewrite** — reformulate query for better vector search
3. **Retrieve** — query Pinecone top-k
4. **Grade** — LLM scores each retrieved chunk for relevance
5. **Retry** — if insufficient results, rewrite with different terminology
6. **Fallback** — web search via Tavily if vector DB has no results

## Project Structure

```
agents/          # Five LangGraph agent nodes
api/             # FastAPI routes (auth, pipeline, rag, setup)
graph/           # LangGraph pipeline definition and checkpoint config
memory/          # AgenticRAG, MongoDB checkpointer, database helpers
models/          # Pydantic models for all pipeline state types
prompts/         # System prompts for each agent
scripts/         # Setup and health check scripts
ui/              # Next.js frontend
utils/           # Resume parser, Google API client
```

## Running Locally

### Prerequisites
- Python 3.11+
- Node.js 18+
- MongoDB Atlas cluster
- Pinecone account — create a serverless index (1536 dims, cosine, `hiregraph`)
- OpenAI API key
- Google OAuth 2.0 credentials (Gmail + Calendar scopes)

### Backend

```bash
cd ai-recruiting-pipeline   # if nested, otherwise stay at root
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\python.exe -m pip install -r requirements.txt

# Verify all services
.venv\Scripts\python.exe scripts/setup.py

# Start server
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

Copy `.env.example` to `.env` and fill in:

```
OPENAI_API_KEY=
OPENAI_AGENT_MODEL=gpt-4o
OPENAI_GRADER_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

MONGODB_URI=
MONGODB_DB_NAME=recruiting_pipeline

PINECONE_API_KEY=
PINECONE_INDEX_NAME=hiregraph

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

TAVILY_API_KEY=

FRONTEND_URL=http://localhost:3000
```

## Human-in-the-Loop Checkpoints

The LangGraph pipeline uses `interrupt_before` to pause at 5 stages:

| Stage | What the recruiter does |
|---|---|
| `shortlist_review` | Approve/reject screened candidates |
| `finalist_review` | Approve interview plans, fill in interviewer emails |
| `awaiting_feedback` | Submit real interview feedback |
| `offer_candidates_review` | Select which candidates receive offers |
| `offer_review` | Approve/modify offer letters before sending |
