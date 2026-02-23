"""
intake.py
─────────
The Intake Agent — BidVault's "eyes" on a new RFP.

Reads raw RFP text, sends it to an LLM, and returns a structured RFPBrief
that feeds directly into the Drafting Agent.

Usage:
    from bidvault.agents.intake import IntakeAgent, RFPBrief

    agent = IntakeAgent()
    brief = agent.extract_brief(rfp_text)
    print(brief.deadline)
    print(brief.evaluation_criteria)
"""

from typing import List, Optional
from pydantic import BaseModel, Field


# ── SUB-MODELS ────────────────────────────────────────────────────────────────

class EvaluationCriterion(BaseModel):
    criterion: str   = Field(description="The name or description of the evaluation criterion")
    weight: Optional[str] = Field(default=None, description="The weight/score (e.g., '60%', '30 points')")

class MandatoryDocument(BaseModel):
    document_name: str        = Field(description="The name of the required document")
    description: Optional[str] = Field(default=None, description="Any specific format or details required")


# ── MAIN SCHEMA ───────────────────────────────────────────────────────────────

class RFPBrief(BaseModel):
    """Structured summary of an RFP, extracted by the Intake Agent."""

    # ── Identity ──────────────────────────────────────────────────────────────
    project_name:      str          = Field(default="Unknown Project",      description="Name of the project or tender")
    client:            str          = Field(default="Unknown Client",        description="Name of the issuing organisation")
    reference_number:  Optional[str] = Field(default=None,                  description="Tender reference or bid number")

    # ── Timelines ─────────────────────────────────────────────────────────────
    deadline:          Optional[str] = Field(default=None, description="Final submission deadline")
    enquiries_deadline: Optional[str] = Field(default=None, description="Deadline for submitting clarification questions (often earlier than submission deadline)")

    # ── Overview ──────────────────────────────────────────────────────────────
    summary:           str          = Field(default="No summary available",  description="2-3 sentence overview of the project scope")
    project_duration:  Optional[str] = Field(default=None,                  description="How long the project must take (e.g., '10 months')")
    project_location:  Optional[str] = Field(default=None,                  description="Where work must be performed (on-site/remote/city)")

    # ── Scope ─────────────────────────────────────────────────────────────────
    scope_of_work:     List[str]    = Field(default_factory=list,            description="Key deliverables and activities in scope")
    out_of_scope:      List[str]    = Field(default_factory=list,            description="Items explicitly excluded from scope")

    # ── Evaluation ────────────────────────────────────────────────────────────
    evaluation_criteria:  List[EvaluationCriterion] = Field(default_factory=list, description="How the bid will be scored (categories + weights)")
    technical_threshold:  Optional[str]             = Field(default=None,         description="Minimum technical score to pass to financial evaluation")

    # ── Eligibility ───────────────────────────────────────────────────────────
    experience_requirements: List[str] = Field(default_factory=list, description="Minimum years of experience or domain expertise required to bid")
    certifications_required: List[str] = Field(default_factory=list, description="Specific certifications required (e.g., PMP, SharePoint Admin, ISO)")

    # ── Administrative ────────────────────────────────────────────────────────
    mandatory_documents: List[MandatoryDocument] = Field(default_factory=list, description="Documents that MUST be submitted with the bid")
    submission_method:   Optional[str]           = Field(default=None,         description="How to submit (e.g., 'Physical Copy', 'Via Portal', 'Email')")
    contact_person:      Optional[str]           = Field(default=None,         description="Point of contact for inquiries")

    # ── Commercial ────────────────────────────────────────────────────────────
    currency:       Optional[str] = Field(default=None, description="Currency of the bid (e.g., 'NAD', 'USD', 'KES')")
    preferencing:   Optional[str] = Field(default=None, description="Any local content or nationality preference policies (e.g., 'Namibian bidders preferred')")


# ── AGENT ─────────────────────────────────────────────────────────────────────

class IntakeAgent:
    """
    The Intake Agent analyzes new RFPs to extract structured requirements.
    It feeds the Drafting Agent with the context needed to write the proposal.

    Key design decisions:
    - Does NOT store anything to the database (analyze-only).
    - Cleans extracted text before sending to the LLM to remove null bytes.
    - Uses explicit JSON key names in the prompt to prevent schema mismatch.
    """

    def __init__(self, api_key: Optional[str] = None):
        import os
        from groq import Groq

        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found in environment")

        self.client = Groq(api_key=self.api_key)
        self.model  = "llama-3.3-70b-versatile"

    def extract_brief(self, text: str) -> RFPBrief:
        """
        Uses LLM to extract a structured RFPBrief from raw RFP text.
        Cleans the text first, then sends up to 40,000 characters to the LLM.
        """
        # Step 0: Remove null bytes and non-printable chars that confuse LLMs
        text = "".join(char for char in text if char.isprintable() or char in "\n\r\t")

        system_prompt = (
            "You are an expert Bid Strategy Analyst specialising in public sector tenders. "
            "Extract a structured Bid Brief from the provided RFP/Terms of Reference text.\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. PROJECT NAME: Look for the title after 'Terms of Reference for...', 'Provision of...', or on the cover page.\n"
            "2. CLIENT: The organisation issuing the bid.\n"
            "3. DEADLINE: The final submission date/time. Look for 'Closing Date', 'Submission Deadline'.\n"
            "4. ENQUIRIES DEADLINE: A separate, earlier date for submitting questions. Different from submission deadline.\n"
            "5. EVALUATION CRITERIA: Sections titled 'Evaluation', 'Selection Criteria', 'Award Criteria'. Capture category + weight.\n"
            "6. MANDATORY DOCUMENTS: Required admin docs (Tax certificates, company registration, SSC, etc.).\n"
            "7. PROJECT DURATION & LOCATION: Look for 'completion period', 'implementation period', 'project timeline', site requirements.\n"
            "8. ELIGIBILITY: Look for 'experience requirements', 'minimum qualifications', 'bidder must have'. List each requirement.\n"
            "9. CERTIFICATIONS: Any specific certifications required (PMP, PRINCE2, SharePoint Admin, ISO). List each one.\n"
            "10. SCOPE vs EXCLUSIONS: Capture 'Scope of Work' deliverables as a list AND any 'Out of Scope' / 'Exclusions' separately.\n"
            "11. PREFERENCING: Note any local content, nationality, or preference policy (e.g., 'Namibian suppliers preferred').\n"
            "12. CURRENCY: The bid currency (NAD, USD, KES, etc.).\n\n"
            "Return ONLY a JSON object using these exact lowercase keys:\n"
            "project_name, client, reference_number, deadline, enquiries_deadline, summary,\n"
            "project_duration, project_location, scope_of_work (list of strings), out_of_scope (list of strings),\n"
            "evaluation_criteria (list of {criterion, weight}), technical_threshold,\n"
            "experience_requirements (list of strings), certifications_required (list of strings),\n"
            "mandatory_documents (list of {document_name, description}),\n"
            "submission_method, contact_person, currency, preferencing.\n"
            "Use null for missing optional fields, empty lists [] for missing list fields."
        )

        # 40,000 chars ≈ 60+ pages — enough to capture most RFP key sections
        context_text = text[:40000]

        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": f"Extract the Bid Brief from this RFP text:\n\n{context_text}"}
                ],
                model=self.model,
                response_format={"type": "json_object"},
                temperature=0.1,  # Low temperature for extraction accuracy
            )

            raw_json = chat_completion.choices[0].message.content
            return RFPBrief.model_validate_json(raw_json)

        except Exception as e:
            print(f"Error in Intake Agent extraction: {e}")
            raise
