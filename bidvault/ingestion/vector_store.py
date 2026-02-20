"""
vector_store.py
───────────────
Handles all interactions with pgvector.
Stores chunks + their embeddings + metadata.
Provides semantic search.

REQUIRES:
  PostgreSQL with pgvector extension enabled:
    CREATE EXTENSION IF NOT EXISTS vector;

  Table creation (run once):
    python -c "from bidvault.ingestion.vector_store import create_table; create_table()"

ENVIRONMENT VARIABLES:
  DATABASE_URL         — postgresql://user:pass@host:5432/bidvault
  AZURE_OPENAI_API_KEY — for generating embeddings
  AZURE_OPENAI_ENDPOINT
  AZURE_OPENAI_EMBEDDING_DEPLOYMENT — e.g. "text-embedding-3-large"
"""

import os
import json
import uuid
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from .metadata import DocumentMetadata


# Default to 384 for local fastembed (bge-small-en-v1.5)
# If using Azure text-embedding-3-large, you would use 3072
EMBEDDING_DIMENSIONS = 384  


# ── SCHEMA ────────────────────────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS document_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID,                           -- FK to documents table
    chunk_index     INTEGER NOT NULL,
    text            TEXT NOT NULL,
    embedding       vector(384),                   -- matching local model
    metadata        JSONB,                          -- all metadata fields
    source_type     VARCHAR(50),                    -- denormalised for fast filtering
    sector          VARCHAR(50),
    donor           VARCHAR(50),
    section_type    VARCHAR(50),
    year            INTEGER,
    won             BOOLEAN,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Indexes for fast filtering before vector search
CREATE INDEX IF NOT EXISTS idx_chunks_source_type  ON document_chunks (source_type);
CREATE INDEX IF NOT EXISTS idx_chunks_sector       ON document_chunks (sector);
CREATE INDEX IF NOT EXISTS idx_chunks_donor        ON document_chunks (donor);
CREATE INDEX IF NOT EXISTS idx_chunks_section_type ON document_chunks (section_type);
CREATE INDEX IF NOT EXISTS idx_chunks_year         ON document_chunks (year);
CREATE INDEX IF NOT EXISTS idx_chunks_won          ON document_chunks (won);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id  ON document_chunks (document_id);

-- pgvector HNSW index for fast approximate nearest-neighbour search
-- Build AFTER data is loaded for best performance
-- CREATE INDEX ON document_chunks USING hnsw (embedding vector_cosine_ops)
--     WITH (m = 16, ef_construction = 64);
"""


# ── DATA CLASSES ──────────────────────────────────────────────────────────────

@dataclass
class StoredChunk:
    id:           str
    text:         str
    metadata:     DocumentMetadata
    similarity:   float = 0.0    # populated during search results


@dataclass
class SearchFilters:
    """
    Narrow the vector search before running similarity scoring.
    Pre-filtering on indexed columns is much faster than post-filtering.
    """
    source_type:    Optional[str]  = None   # e.g. "proposal"
    sector:         Optional[str]  = None   # e.g. "health"
    donor:          Optional[str]  = None   # e.g. "usaid"
    section_type:   Optional[str]  = None   # e.g. "methodology"
    year_min:       Optional[int]  = None
    year_max:       Optional[int]  = None
    won_only:       bool           = False  # restrict to winning proposals
    document_id:    Optional[str]  = None   # search within a specific document


# ── CLIENT ────────────────────────────────────────────────────────────────────

class VectorStore:
    """
    Wraps pgvector operations. One instance per application.
    Call VectorStore() and reuse — it manages its own connection pool.
    """

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.environ["DATABASE_URL"]
        self._conn = None

    def _get_conn(self):
        """Lazy connection — only connects when first used."""
        if self._conn is None or self._conn.closed:
            try:
                import psycopg2
                import psycopg2.extras
            except ImportError:
                raise ImportError("Run: pip install psycopg2-binary")
            self._conn = psycopg2.connect(self.database_url)
            psycopg2.extras.register_uuid(self._conn)
        return self._conn

    def create_table(self):
        """Run once to set up the schema. Safe to call multiple times."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
        conn.commit()
        print("✓ document_chunks table ready")

    # ── WRITE ─────────────────────────────────────────────────────────────────

    def store_chunk(self, text: str, embedding: list[float], metadata: DocumentMetadata) -> str:
        """Store a single chunk. Returns the new chunk ID."""
        chunk_id = str(uuid.uuid4())
        conn     = self._get_conn()

        meta_dict = metadata.to_dict()

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO document_chunks
                    (id, document_id, chunk_index, text, embedding, metadata,
                     source_type, sector, donor, section_type, year, won)
                VALUES
                    (%s, %s, %s, %s, %s::vector, %s,
                     %s, %s, %s, %s, %s, %s)
            """, (
                chunk_id,
                metadata.document_id or None,
                metadata.chunk_index,
                text,
                embedding,      # psycopg2 serialises list → pgvector format
                json.dumps(meta_dict),
                metadata.source_type,
                metadata.sector,
                metadata.donor,
                metadata.section_type,
                metadata.year or None,
                metadata.won,
            ))
        conn.commit()
        return chunk_id

    def store_chunks_batch(self, items: list[tuple]) -> int:
        """
        Batch insert for performance.
        items: list of (text, embedding, DocumentMetadata)
        Returns count of inserted chunks.
        """
        if not items:
            return 0

        conn = self._get_conn()
        rows = []

        for text, embedding, metadata in items:
            meta_dict = metadata.to_dict()
            rows.append((
                str(uuid.uuid4()),
                metadata.document_id or None,
                metadata.chunk_index,
                text,
                embedding,
                json.dumps(meta_dict),
                metadata.source_type,
                metadata.sector,
                metadata.donor,
                metadata.section_type,
                metadata.year or None,
                metadata.won,
            ))

        with conn.cursor() as cur:
            import psycopg2.extras
            psycopg2.extras.execute_values(cur, """
                INSERT INTO document_chunks
                    (id, document_id, chunk_index, text, embedding, metadata,
                     source_type, sector, donor, section_type, year, won)
                VALUES %s
            """, rows, template="""
                (%s, %s, %s, %s, %s::vector, %s, %s, %s, %s, %s, %s, %s)
            """)
        conn.commit()
        return len(rows)

    def delete_by_document(self, document_id: str) -> int:
        """Remove all chunks for a document (e.g. when re-indexing)."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM document_chunks WHERE document_id = %s",
                (document_id,)
            )
            count = cur.rowcount
        conn.commit()
        return count

    # ── SEARCH ────────────────────────────────────────────────────────────────

    def search(
        self,
        query_embedding:    list[float],
        filters:            Optional[SearchFilters] = None,
        top_k:              int = 8,
        min_similarity:     float = 0.5,
    ) -> list[StoredChunk]:
        """
        Semantic search using cosine similarity.
        Apply pre-filters before vector search for performance.

        Returns top_k chunks sorted by similarity (highest first).
        """
        conn    = self._get_conn()
        filters = filters or SearchFilters()

        # Build WHERE clause from filters
        conditions = []
        params     = []

        if filters.source_type:
            conditions.append("source_type = %s")
            params.append(filters.source_type)

        if filters.sector:
            conditions.append("sector = %s")
            params.append(filters.sector)

        if filters.donor:
            conditions.append("donor = %s")
            params.append(filters.donor)

        if filters.section_type:
            conditions.append("section_type = %s")
            params.append(filters.section_type)

        if filters.year_min:
            conditions.append("year >= %s")
            params.append(filters.year_min)

        if filters.year_max:
            conditions.append("year <= %s")
            params.append(filters.year_max)

        if filters.won_only:
            conditions.append("won = TRUE")

        if filters.document_id:
            conditions.append("document_id = %s")
            params.append(filters.document_id)

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        # pgvector cosine similarity: 1 - (embedding <=> query)
        # <=> is the cosine distance operator
        query = f"""
            SELECT
                id,
                text,
                metadata,
                1 - (embedding <=> %s::vector) AS similarity
            FROM document_chunks
            {where_clause}
            HAVING 1 - (embedding <=> %s::vector) >= %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """

        # Note: query_embedding appears 3 times in the query
        all_params = [query_embedding] + params + [query_embedding, min_similarity, query_embedding, top_k]

        with conn.cursor() as cur:
            cur.execute(query, all_params)
            rows = cur.fetchall()

        results = []
        for row_id, text, meta_json, similarity in rows:
            meta = DocumentMetadata.from_dict(meta_json if meta_json else {})
            results.append(StoredChunk(
                id         = str(row_id),
                text       = text,
                metadata   = meta,
                similarity = float(similarity),
            ))

        return results

    def search_by_section(
        self,
        query_embedding: list[float],
        section_type:    str,
        sector:          Optional[str] = None,
        donor:           Optional[str] = None,
        won_only:        bool = True,
        top_k:           int = 5,
    ) -> list[StoredChunk]:
        """
        Convenience method for the most common retrieval pattern:
        'Find similar [section_type] chunks from [sector] proposals for [donor]'.
        Used by the Drafting Agent.
        """
        filters = SearchFilters(
            source_type  = "proposal",
            section_type = section_type,
            sector       = sector,
            donor        = donor,
            won_only     = won_only,
        )
        return self.search(query_embedding, filters=filters, top_k=top_k)

    # ── STATS ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return counts by source_type and sector — useful for monitoring."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT source_type, sector, COUNT(*) as count
                FROM document_chunks
                GROUP BY source_type, sector
                ORDER BY count DESC
            """)
            rows = cur.fetchall()

        return {
            "by_source_and_sector": [
                {"source_type": r[0], "sector": r[1], "count": r[2]}
                for r in rows
            ],
            "total": sum(r[2] for r in rows),
        }
