from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from memory.database import ensure_indexes
from api.routes import auth, setup, pipeline, rag


@asynccontextmanager
async def lifespan(app: FastAPI):


    ensure_indexes()
    print("[HireGraph] MongoDB indexes verified.")
    print("[HireGraph] Server ready.")

    yield


    print("[HireGraph] Server shutting down.")


app = FastAPI(
    title="HireGraph — AI Recruiting Pipeline",
    description=(
        "Multi-agent recruiting pipeline with human-in-the-loop checkpoints. "
        "Automates JD parsing, resume screening, interview planning, "
        "evaluation, and offer drafting."
    ),
    version="1.0.0",
    lifespan=lifespan,


)


import os

_frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[_frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router,     prefix="/auth",     tags=["Auth"])
app.include_router(setup.router,    prefix="/setup",    tags=["Setup"])
app.include_router(pipeline.router, prefix="/pipeline", tags=["Pipeline"])
app.include_router(rag.router,      prefix="/rag",      tags=["RAG"])


@app.get("/health", tags=["Health"])
def health_check():
    """Returns 200 OK if the server is running."""
    return {"status": "ok", "service": "HireGraph API"}
