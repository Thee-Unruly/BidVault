# Document Ingestion Pipeline

A **generalized, AI-powered document ingestion pipeline** that can be adapted to any domain.
Originally built for [BidVault](https://github.com/Thee-Unruly/BidVault) (proposal automation), it is now a reusable engine for ingesting, embedding, and semantically searching any document type.

## Architecture

The pipeline separates the **core ingestion engine** from **domain-specific logic** using a plugin pattern.

```
.
├── bidvault/
│   ├── ingestion/           # Core Engine (domain-agnostic)
│   │   ├── pipeline.py      # Orchestrator: Detect → Extract → Chunk → Analyze → Embed → Store
│   │   ├── metadata.py      # BaseMetadata + DocumentAnalyzer interface
│   │   ├── chunker.py       # Structure-aware, paragraph, and token splitting
│   │   ├── extractor.py     # PDF, DOCX, OCR text extraction
│   │   ├── detector.py      # File type detection
│   │   ├── embedder.py      # FastEmbed / Azure OpenAI embeddings
│   │   ├── vector_store.py  # pgvector read/write/search
│   │   └── sharepoint.py    # Microsoft Graph API integration
│   │
│   ├── domains/             # Domain Adapters (plug in your own!)
│   │   └── bids/            # Bid & Proposal documents (BidVault)
│   │       └── analyzer.py  # Sector, donor, won-status auto-tagging
│   │
│   ├── agents/              # AI Agents
│   │   └── intake.py        # IntakeAgent: RFP → structured Bid Brief (via Groq/Llama-3)
│   └── api/                 # FastAPI Endpoints
│       ├── ingest.py        # /api/ingest/upload, /search, /stats
│       └── intake.py        # /api/intake/analyze-rfp
│
├── data/                    # Sample documents for testing
├── tests/                   # Test suites
├── scripts/                 # Utility & CLI scripts
├── .env                     # Environment variables
├── requirements.txt
├── main.py                  # App entry point
└── docker-compose.yml       # Infrastructure (Postgres + pgvector)
```

## How It Works

### 1. Ingestion Pipeline
Orchestrates: **Detect → Extract → Chunk → Analyze → Embed → Store**.

| Step | What it does |
|---|---|
| **Detect** | Identifies file type (PDF, DOCX, scanned image) and OCR needs |
| **Extract** | Pulls text using pdfplumber, python-docx, or Tesseract OCR |
| **Chunk** | Structure-aware splitting at headings, then paragraphs, then tokens |
| **Analyze** | Domain adapter enriches metadata (sector, donor, year, etc.) |
| **Embed** | FastEmbed (local, default) or Azure OpenAI text-embedding-3-large |
| **Store** | pgvector — embedding + full metadata stored together |

### 2. Domain Adapters
The pipeline is extended by implementing a `DocumentAnalyzer`:

```python
from bidvault.ingestion.metadata import DocumentAnalyzer

class LegalAnalyzer(DocumentAnalyzer):
    def analyze(self, text: str, initial_meta: dict) -> dict:
        return {
            "jurisdiction": detect_jurisdiction(text),
            "document_type": detect_legal_type(text),
        }

    def infer_section_type(self, hint: str) -> str:
        # map "WHEREAS", "RECITALS", etc.
        return map_legal_headings(hint)

# Use with the pipeline:
pipeline = IngestionPipeline(analyzer=LegalAnalyzer())
```

The **default analyzer is `BidAnalyzer`**, preserving full compatibility with the existing BidVault bidding workflow.

### 3. Intake Agent
*(BidVault-specific)*
Reads raw RFP text, calls an LLM (Llama-3 via Groq), and returns a structured `RFPBrief` with deadlines, evaluation criteria, mandatory documents, and eligibility requirements.

## Getting Started

### 1. Setup Environment
Copy `.env.example` to `.env` and fill in your credentials.

```bash
# Required for vector storage
DATABASE_URL=postgresql://user:pass@localhost:5432/bidvault

# Required for the Intake Agent
GROQ_API_KEY=your_key_here

# Optional: Azure OpenAI for higher-quality embeddings
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Infrastructure
```bash
docker-compose up -d
```

### 4. Running Tests
```bash
python tests/test_ingest.py   # Test core pipeline
python tests/test_intake.py   # Test RFP analysis agent
```

## Key Tools
| Purpose | Tool |
|---|---|
| LLM | Llama-3 (via Groq) |
| Embeddings | FastEmbed (default, local) or Azure OpenAI |
| OCR | Tesseract + Poppler |
| Vector DB | pgvector (PostgreSQL extension) |
| SharePoint | Microsoft Graph API |
| API | FastAPI |
