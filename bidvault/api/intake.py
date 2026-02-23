"""
api/intake.py
─────────────
FastAPI endpoint for the Intake Agent.
Accepts an RFP upload and returns a structured Bid Brief.

Mount in main.py:
    from bidvault.api.intake import router as intake_router
    app.include_router(intake_router, prefix="/api/intake", tags=["intake"])

Example curl:
    curl -X POST http://localhost:8000/api/intake/analyze \\
      -F "file=@GIPF-RFP.pdf"
"""

import os
import shutil
import tempfile

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from bidvault.ingestion.detector  import detect
from bidvault.ingestion.extractor import extract
from bidvault.agents.intake       import IntakeAgent, RFPBrief


router = APIRouter()


# ── RESPONSE MODEL ────────────────────────────────────────────────────────────

class EvaluationCriterionOut(BaseModel):
    criterion: str
    weight: Optional[str]

class MandatoryDocumentOut(BaseModel):
    document_name: str
    description: Optional[str]

class BidBriefResponse(BaseModel):
    project_name:         str
    client:               str
    reference_number:     Optional[str]
    deadline:             Optional[str]
    summary:              str
    evaluation_criteria:  List[EvaluationCriterionOut]
    mandatory_documents:  List[MandatoryDocumentOut]
    technical_threshold:  Optional[str]
    contact_person:       Optional[str]
    submission_method:    Optional[str]


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=BidBriefResponse)
async def analyze_rfp(file: UploadFile = File(...)):
    """
    Upload an RFP document (PDF, DOCX, or TXT) and receive a structured Bid Brief.
    The document is NOT stored in the vector database — it is analyzed in-memory only.

    Returns:
        BidBriefResponse: structured extraction of the RFP's key requirements.
    """
    allowed_extensions = {".pdf", ".docx", ".doc", ".txt"}
    file_ext = os.path.splitext(file.filename or "")[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Allowed: {allowed_extensions}"
        )

    # Save to a temp file for processing
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        # Extract text via the existing pipeline modules
        detection  = detect(tmp_path)
        extraction = extract(tmp_path, detection)

        if extraction.char_count < 100:
            raise HTTPException(
                status_code=422,
                detail="Could not extract meaningful text from document. It may be encrypted or a low-quality scan."
            )

        # Run the Intake Agent (no DB storage — analyze only)
        agent = IntakeAgent()
        brief = agent.extract_brief(extraction.text)

        return BidBriefResponse(
            project_name        = brief.project_name,
            client              = brief.client,
            reference_number    = brief.reference_number,
            deadline            = brief.deadline,
            summary             = brief.summary,
            evaluation_criteria = [
                EvaluationCriterionOut(criterion=c.criterion, weight=c.weight)
                for c in brief.evaluation_criteria
            ],
            mandatory_documents = [
                MandatoryDocumentOut(document_name=d.document_name, description=d.description)
                for d in brief.mandatory_documents
            ],
            technical_threshold = brief.technical_threshold,
            contact_person      = brief.contact_person,
            submission_method   = brief.submission_method,
        )

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
