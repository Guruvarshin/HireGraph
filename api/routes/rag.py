from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form

from utils.jwt_auth import current_recruiter

router = APIRouter()


@router.get("/rubrics-status")
def rubrics_status(
    x_recruiter_id: str = Depends(current_recruiter),
):
    """Check whether company rubric vectors exist in Pinecone for this tenant."""
    try:
        from memory.agentic_rag import rag, tenant_namespace
        tenant_ns = tenant_namespace(x_recruiter_id, "company_rubrics")
        stats = rag._index.describe_index_stats()
        ns = stats.namespaces or {}
        count = 0
        for key, val in ns.items():
            if key == tenant_ns:
                count = getattr(val, "vector_count", 0)
                break
        return {"loaded": count > 0, "vector_count": count, "namespace": tenant_ns}
    except Exception as exc:
        return {"loaded": False, "vector_count": 0, "error": str(exc)}


@router.get("/search")
def search_rag(
    namespace: str = Query("company_rubrics", description="Only 'company_rubrics' is supported"),
    query: str = Query(..., description="Search query"),
    x_recruiter_id: str = Depends(current_recruiter),
):
    if namespace != "company_rubrics":
        raise HTTPException(status_code=400, detail="namespace must be 'company_rubrics'")

    from memory.agentic_rag import rag, TOP_K, tenant_namespace

    tenant_ns = tenant_namespace(x_recruiter_id, namespace)
    embeddings = rag.embeddings
    index = rag._index

    query_vector = embeddings.embed_query(query)
    results = index.query(
        vector=query_vector,
        top_k=TOP_K,
        namespace=tenant_ns,
        include_metadata=True,
    )

    return {
        "namespace": tenant_ns,
        "results": [
            {
                "score": round(m.score, 4),
                "text": m.metadata.get("text", ""),
                "metadata": m.metadata,
                "chunk_index": m.id,
            }
            for m in results.matches
        ],
    }


@router.post("/index")
async def index_document(
    namespace: str = Form(...),
    document_file: UploadFile = File(...),
    document_name: str = Form(None),
    x_recruiter_id: str = Depends(current_recruiter),
):


    from memory.agentic_rag import rag, tenant_namespace


    if namespace != "company_rubrics":
        raise HTTPException(
            status_code=400,
            detail="namespace must be 'company_rubrics'",
        )


    try:
        content = await document_file.read()
        content_str = content.decode("utf-8")
    except UnicodeDecodeError:

        try:
            from utils.resume_parser import _extract_pdf

            await document_file.seek(0)
            raw_bytes = await document_file.read()
            content_str = _extract_pdf(raw_bytes)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Could not read file {document_file.filename}: {exc}",
            )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"File read error: {exc}",
        )

    if not content_str.strip():
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty",
        )


    doc_name = document_name or document_file.filename
    tenant_ns = tenant_namespace(x_recruiter_id, namespace)

    try:
        rag.index_company_rubrics(content_str, {"source": doc_name}, user_id=x_recruiter_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Indexing failed: {exc}",
        )


    return {
        "indexed": True,
        "namespace": tenant_ns,
        "document_name": doc_name,
        "message": (
            f"Indexed '{doc_name}' to {tenant_ns}. "
            f"Agents will use this knowledge in subsequent pipeline runs."
        ),
    }
