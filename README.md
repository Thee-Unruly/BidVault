# BidVault - Document Ingestion & Bid Agent Pipeline

BidVault is a powerful, AI-driven proposal automation system. It manages the entire lifecycle of a bid, from ingesting historical win data to analyzing new RFPs and drafting winning responses.

## Project Structure

```
.
├── bidvault/              # Core Logic
│   ├── agents/            # AI Agents (Intake, Drafting, Review)
│   ├── api/               # FastAPI Endpoints
│   └── ingestion/         # Document Processing Pipeline
├── data/                  # Sample RFPs and Proposals (for testing)
├── tests/                 # Test Suites (Ingestion, Search, Agents)
├── scripts/               # Utility & CLI scripts
├── .env                   # Environment variables
├── requirements.txt       # Python dependencies
├── main.py                # App entry point
└── docker-compose.yml     # Infrastructure (Postgres + pgvector)
```

## How It Works

### 1. Ingestion Pipeline
Orchestrates: **Detect → Extract → Chunk → Embed → Store**.
*   **Detection**: Identifies file type and OCR needs.
*   **Extraction**: Handles PDF, DOCX, and Scanned images (OCR).
*   **Chunking**: Splits text into semantic sections using headers.
*   **Embedding**: Uses FastEmbed (local) or Azure OpenAI for vectorisation.
*   **Storage**: Hybrid storage using PostgreSQL for metadata and **pgvector** for vectors.

### 2. Intake Agent
The "Eyes" of the system.
*   Analyzes new RFPs to extract structured **Bid Briefs**.
*   Identifies deadlines, evaluation criteria, mandatory documents, and eligibility requirements.
*   Provides a go/no-go summary for bid managers.

### 3. Drafting Agent (Next)
The "Writer" of the system.
*   Combines the **Bid Brief** with historical context from the **Vector Store**.
*   Generates initial drafts for technical methodologies, executive summaries, and company profiles.

## Getting Started

### 1. Setup Environment
Copy `.env.example` to `.env` and fill in your credentials (including `GROQ_API_KEY`).

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
# Test the Ingestion Pipeline
python tests/test_ingest.py

# Test the Intake Agent (RFP Analysis)
python tests/test_intake.py
```

## Key Tools Used
*   **LLM**: Llama-3 (via Groq)
*   **Embeddings**: FastEmbed (Default) or Azure OpenAI
*   **OCR**: Tesseract + Poppler
*   **Vectors**: pgvector (PostgreSQL extension)
*   **API**: FastAPI
