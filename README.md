# Document Ingestion Pipeline

This pipeline is designed to ingest local and SharePoint documents (PDFs, Word docs, Scans), extract their text, split them into sections, and store them in a vector database for semantic search.

## project Structure

```
.
├── bidvault/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── ingest.py          # FastAPI endpoints for ingestion & search
│   └── ingestion/
│       ├── __init__.py
│       ├── chunker.py         # Structure-aware document splitting
│       ├── detector.py        # File type & OCR requirement detection
│       ├── embedder.py        # Azure OpenAI embedding integration
│       ├── extractor.py       # Multi-format text extraction (PDF, DOCX, OCR)
│       ├── metadata.py        # Metadata schema & auto-tagging logic
│       ├── pipeline.py        # Main orchestrator (The "Brain")
│       ├── sharepoint.py      # SharePoint / MS Graph API connector
│       └── vector_store.py    # pgvector / PostgreSQL interface
├── .env                       # Environment variables (Azure, Postgres)
├── requirements.txt           # Python dependencies
└── main.py                    # App entry point
```

## How It Works (Communication Flow)

1.  **Ingestion Request**: A call is made to the `/api/ingest/upload` (FastAPI) or triggered via `sharepoint.py`.
2.  **Orchestration (`pipeline.py`)**: The `IngestionPipeline` receives the file and initiates the 5-step process.
3.  **Step 1: Detection (`detector.py`)**: Inspects the file to see if it's a digital PDF, a Word doc, or a scan that requires OCR.
4.  **Step 2: Extraction (`extractor.py`)**: Uses `PyMuPDF`, `python-docx`, or `Tesseract OCR` to extract raw text while preserving section markers where possible.
5.  **Step 3: Chunking (`chunker.py`)**: Splits the long text into logical chunks (approx. 500-1000 tokens) based on headers or paragraphs.
6.  **Step 4: Tagging (`metadata.py`)**: Attaches metadata like `sector`, `donor`, `won/lost`, and `year`. It scans text for keywords to auto-fill missing tags.
7.  **Step 5: Embedding & Storage (`embedder.py` & `vector_store.py`)**:
    *   `embedder.py` sends text chunks to Azure OpenAI to get vector representations.
    *   `vector_store.py` saves the text, metadata, and vectors into the `document_chunks` table in PostgreSQL.

## Getting Started

### 1. Setup Environment
Copy `.env.example` to `.env` and fill in your credentials.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Initialize Database
```bash
python -c "from bidvault.ingestion.vector_store import VectorStore; VectorStore().create_table()"
```

### 4. Run the API
```bash
uvicorn bidvault.api.ingest:app --reload
```
*(Note: You'll need a main.py that imports the router, or run uvicorn pointing to the router file if it's configured as a standalone app.)*

## Key Tools Used
*   **Extraction**: PyMuPDF, pdfplumber, pytesseract (OCR)
*   **Pipeline**: LangChain (for chunking logic)
*   **Vectors**: pgvector (PostgreSQL extension)
*   **AI**: Azure OpenAI (text-embedding-3-large)
