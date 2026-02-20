"""
pipeline.py
───────────
The main entry point for the Document Ingestion Pipeline.
Orchestrates: detect → extract → chunk → embed → store.

USAGE:
    from bidvault.ingestion.pipeline import IngestionPipeline, IngestionRequest

    pipeline = IngestionPipeline()

    # Ingest a past proposal
    result = pipeline.ingest(IngestionRequest(
        file_path   = "/path/to/proposal.pdf",
        source_type = "proposal",
        sector      = "health",
        donor       = "usaid",
        year        = 2023,
        won         = True,
        client      = "Ministry of Health Kenya",
        document_id = "uuid-from-postgresql",
    ))

    print(result.chunks_stored)  # e.g. 24
    print(result.warnings)       # any issues encountered

SHAREPOINT USAGE:
    # After downloading a file from SharePoint via Graph API:
    result = pipeline.ingest(IngestionRequest(
        file_path            = local_temp_path,
        source_type          = "proposal",
        sector               = item["fields"].get("Sector", "general"),
        year                 = 2024,
        sharepoint_item_id   = item["id"],
        sharepoint_url       = item["webUrl"],
        document_id          = db_record_id,
    ))
"""

import os
import time
from dataclasses import dataclass, field
from typing import Optional

from .detector    import detect
from .extractor   import extract
from .chunker     import chunk, infer_section_type
from .metadata    import DocumentMetadata, enrich_metadata
from .embedder    import Embedder
from .vector_store import VectorStore


# ── REQUEST / RESULT SCHEMA ───────────────────────────────────────────────────

@dataclass
class IngestionRequest:
    """Everything you need to tell the pipeline about a document."""

    file_path:      str                         # local path to the file

    # Document classification — set what you know, pipeline infers the rest
    source_type:    str     = "other"           # proposal | rfp | cv | project | etc.
    sector:         str     = ""               # auto-tagged if empty
    donor:          str     = ""               # auto-tagged if empty
    year:           int     = 0                 # defaults to current year if 0

    # Provenance
    document_id:    str     = ""               # UUID from your PostgreSQL documents table
    client:         str     = ""
    country:        str     = "Kenya"
    won:            Optional[bool] = None       # True / False / None(unknown)
    tender_value_usd: Optional[float] = None
    bid_reference:  str     = ""

    # SharePoint (if sourced from there)
    sharepoint_item_id: str = ""
    sharepoint_url:     str = ""


@dataclass
class IngestionResult:
    success:            bool
    chunks_stored:      int     = 0
    extraction_method:  str     = ""
    doc_type:           str     = ""
    page_count:         int     = 0
    warnings:           list[str] = field(default_factory=list)
    error:              str     = ""
    duration_seconds:   float   = 0.0


# ── PIPELINE ─────────────────────────────────────────────────────────────────

class IngestionPipeline:

    def __init__(
        self,
        embedder:       Optional[Embedder]      = None,
        vector_store:   Optional[VectorStore]   = None,
        dry_run:        bool = False,   # if True, skips storing — useful for testing
    ):
        self.embedder     = embedder     or Embedder()
        self.vector_store = vector_store or VectorStore()
        self.dry_run      = dry_run

    def ingest(self, request: IngestionRequest) -> IngestionResult:
        """
        Full pipeline: detect → extract → chunk → embed → store.
        Returns a result object with counts and any warnings.
        """
        start_time = time.time()

        try:
            return self._run(request, start_time)
        except Exception as e:
            return IngestionResult(
                success          = False,
                error            = str(e),
                duration_seconds = time.time() - start_time,
            )

    def _run(self, request: IngestionRequest, start_time: float) -> IngestionResult:
        warnings = []

        # ── STEP 1: DETECT ────────────────────────────────────────────────────
        print(f"[1/5] Detecting document type: {request.file_path}")
        detection = detect(request.file_path)
        print(f"      → {detection.doc_type} ({detection.page_count} pages, OCR={detection.needs_ocr})")

        if detection.notes:
            warnings.append(f"Detection: {detection.notes}")

        # ── STEP 2: EXTRACT ───────────────────────────────────────────────────
        print(f"[2/5] Extracting text...")
        extraction = extract(request.file_path, detection)
        print(f"      → {extraction.char_count:,} characters via {extraction.extraction_method}")

        warnings.extend(extraction.warnings)

        if extraction.char_count < 200:
            warnings.append(
                "Extracted text is very short — document may be empty, password-protected, or corrupt"
            )

        # ── STEP 3: CHUNK ─────────────────────────────────────────────────────
        print(f"[3/5] Chunking...")
        chunks = chunk(extraction.text, source_type=request.source_type)
        print(f"      → {len(chunks)} chunks")

        if not chunks:
            return IngestionResult(
                success          = False,
                error            = "No chunks produced — text may be too short or extraction failed",
                doc_type         = detection.doc_type,
                page_count       = detection.page_count,
                extraction_method= extraction.extraction_method,
                warnings         = warnings,
                duration_seconds = time.time() - start_time,
            )

        # ── STEP 4: BUILD METADATA ────────────────────────────────────────────
        print(f"[4/5] Building metadata...")
        year = request.year or _current_year()

        base_metadata = DocumentMetadata(
            source_type          = request.source_type,
            sector               = request.sector,
            donor                = request.donor,
            year                 = year,
            document_id          = request.document_id,
            file_name            = os.path.basename(request.file_path),
            client               = request.client,
            country              = request.country,
            won                  = request.won,
            tender_value_usd     = request.tender_value_usd,
            bid_reference        = request.bid_reference,
            sharepoint_item_id   = request.sharepoint_item_id,
            sharepoint_url       = request.sharepoint_url,
        )

        # Auto-fill missing sector/donor from the document text
        base_metadata = enrich_metadata(base_metadata, extraction.text[:5000])
        print(f"      → sector={base_metadata.sector}, donor={base_metadata.donor}")

        # ── STEP 5: EMBED + STORE ─────────────────────────────────────────────
        print(f"[5/5] Embedding {len(chunks)} chunks...")

        if self.dry_run:
            print("      → DRY RUN: skipping embed and store")
            return IngestionResult(
                success           = True,
                chunks_stored     = len(chunks),
                doc_type          = detection.doc_type,
                page_count        = detection.page_count,
                extraction_method = extraction.extraction_method,
                warnings          = warnings,
                duration_seconds  = time.time() - start_time,
            )

        # Prepare per-chunk metadata
        chunk_texts     = [c.text for c in chunks]
        chunk_metadatas = []

        for c in chunks:
            meta = DocumentMetadata(
                **{k: v for k, v in base_metadata.__dict__.items()},
            )
            meta.chunk_index    = c.index
            meta.chunk_method   = c.chunk_method
            meta.section_hint   = c.section_hint
            meta.section_type   = infer_section_type(c.section_hint)
            chunk_metadatas.append(meta)

        # Embed all chunks in one batched call
        embeddings = self.embedder.embed_batch(chunk_texts)
        print(f"      → {len(embeddings)} embeddings generated")

        # Store to pgvector
        items  = list(zip(chunk_texts, embeddings, chunk_metadatas))
        stored = self.vector_store.store_chunks_batch(items)
        print(f"      → {stored} chunks stored in vector DB")

        duration = time.time() - start_time
        print(f"\n✓ Ingestion complete in {duration:.1f}s")

        return IngestionResult(
            success           = True,
            chunks_stored     = stored,
            doc_type          = detection.doc_type,
            page_count        = detection.page_count,
            extraction_method = extraction.extraction_method,
            warnings          = warnings,
            duration_seconds  = duration,
        )

    # ── BULK INGEST ───────────────────────────────────────────────────────────

    def ingest_folder(
        self,
        folder_path:    str,
        default_meta:   dict,
        extensions:     list[str] = [".pdf", ".docx", ".txt"],
    ) -> list[IngestionResult]:
        """
        Ingest all documents in a folder.
        Useful for bulk-loading historical proposals.

        default_meta: dict with source_type, sector, etc. to apply to all files.
        Per-file metadata (year, client, won) should be set by the caller
        via a metadata CSV or SharePoint columns.
        """
        import glob

        results = []
        files   = []

        for ext in extensions:
            files.extend(glob.glob(os.path.join(folder_path, f"**/*{ext}"), recursive=True))

        print(f"Found {len(files)} files in {folder_path}")

        for i, file_path in enumerate(files, 1):
            print(f"\n[{i}/{len(files)}] {os.path.basename(file_path)}")
            request = IngestionRequest(file_path=file_path, **default_meta)
            result  = self.ingest(request)
            results.append(result)

            if not result.success:
                print(f"  ✗ Failed: {result.error}")
            else:
                print(f"  ✓ {result.chunks_stored} chunks")

        success_count = sum(1 for r in results if r.success)
        total_chunks  = sum(r.chunks_stored for r in results)
        print(f"\n{'─'*50}")
        print(f"Bulk ingest complete: {success_count}/{len(files)} files, {total_chunks} total chunks")

        return results


def _current_year() -> int:
    from datetime import datetime
    return datetime.now().year
