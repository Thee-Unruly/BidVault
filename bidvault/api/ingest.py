"""
api/ingest.py
─────────────
FastAPI endpoints for document ingestion.
Mount this router in your main FastAPI app:

    from api.ingest import router as ingest_router
    app.include_router(ingest_router, prefix="/api/ingest", tags=["ingestion"])
"""

import os
import tempfile
import shutil
from typing import Optional, Annotated

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from pydantic import BaseModel

from bidvault.ingestion.pipeline   import IngestionPipeline, IngestionRequest, IngestionResult
from bidvault.ingestion.sharepoint import SharePointConnector
from bidvault.ingestion.vector_store import VectorStore


router   = APIRouter()
pipeline = IngestionPipeline()


# ── REQUEST / RESPONSE MODELS ─────────────────────────────────────────────────

class IngestResponse(BaseModel):
    success:            bool
    chunks_stored:      int
    doc_type:           str
    page_count:         int
    extraction_method:  str
    warnings:           list[str]
    error:              str = ""
    duration_seconds:   float


class SearchRequest(BaseModel):
    query:          str
    source_type:    Optional[str] = None
    sector:         Optional[str] = None
    donor:          Optional[str] = None
    section_type:   Optional[str] = None
    won_only:       bool = False
    top_k:          int = 8


class SearchResult(BaseModel):
    id:           str
    text:         str
    similarity:   float
    source_type:  str
    sector:       str
    section_type: str
    year:         int
    won:          Optional[bool]
    client:       str
    sharepoint_url: str


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=IngestResponse)
async def ingest_upload(
    file:        UploadFile    = File(...),
    source_type: str           = Form("other"),
    sector:      str           = Form(""),
    donor:       str           = Form(""),
    year:        int           = Form(0),
    client:      str           = Form(""),
    won:         Optional[bool]= Form(None),
    document_id: str           = Form(""),
):
    """
    Upload a document file and ingest it into the vector store.
    Accepts PDF, DOCX, DOC, TXT.

    Example curl:
    curl -X POST http://localhost:8000/api/ingest/upload \\
      -F "file=@proposal.pdf" \\
      -F "source_type=proposal" \\
      -F "sector=health" \\
      -F "donor=usaid" \\
      -F "year=2023" \\
      -F "won=true"
    """
    # Validate file type
    allowed_extensions = {".pdf", ".docx", ".doc", ".txt"}
    file_ext = os.path.splitext(file.filename or "")[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Allowed: {allowed_extensions}"
        )

    # Save to temp file
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        request = IngestionRequest(
            file_path   = tmp_path,
            source_type = source_type,
            sector      = sector,
            donor       = donor,
            year        = year,
            client      = client,
            won         = won,
            document_id = document_id,
        )

        result = pipeline.ingest(request)

        return IngestResponse(
            success           = result.success,
            chunks_stored     = result.chunks_stored,
            doc_type          = result.doc_type,
            page_count        = result.page_count,
            extraction_method = result.extraction_method,
            warnings          = result.warnings,
            error             = result.error,
            duration_seconds  = result.duration_seconds,
        )

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/sync-sharepoint")
async def sync_sharepoint(background_tasks: BackgroundTasks):
    """
    Trigger a SharePoint sync in the background.
    Downloads all documents from the SharePoint library and ingests them.

    Returns immediately — sync runs in the background.
    Check /api/ingest/stats to monitor progress.
    """
    connector = SharePointConnector(pipeline=pipeline)
    background_tasks.add_task(connector.sync_to_vector_store)
    return {"message": "SharePoint sync started in background"}


@router.post("/search", response_model=list[SearchResult])
async def search_documents(request: SearchRequest):
    """
    Semantic search across all ingested documents.
    Returns chunks ranked by relevance to the query.

    Example:
    POST /api/ingest/search
    {
      "query": "M&E methodology for health sector",
      "source_type": "proposal",
      "sector": "health",
      "won_only": true,
      "top_k": 5
    }
    """
    from bidvault.ingestion.embedder     import Embedder
    from bidvault.ingestion.vector_store import VectorStore, SearchFilters

    embedder     = Embedder()
    vector_store = VectorStore()

    query_embedding = embedder.embed(request.query)

    filters = SearchFilters(
        source_type  = request.source_type,
        sector       = request.sector,
        donor        = request.donor,
        section_type = request.section_type,
        won_only     = request.won_only,
    )

    chunks = vector_store.search(query_embedding, filters=filters, top_k=request.top_k)

    return [
        SearchResult(
            id            = c.id,
            text          = c.text,
            similarity    = c.similarity,
            source_type   = c.metadata.source_type,
            sector        = c.metadata.sector,
            section_type  = c.metadata.section_type,
            year          = c.metadata.year or 0,
            won           = c.metadata.won,
            client        = c.metadata.client,
            sharepoint_url= c.metadata.sharepoint_url,
        )
        for c in chunks
    ]


@router.get("/stats")
async def ingestion_stats():
    """Return counts of indexed documents by source type and sector."""
    vector_store = VectorStore()
    return vector_store.stats()
