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

from typing import List, Optional, Any
from pydantic import BaseModel, Field


# ── SUB-MODELS ────────────────────────────────────────────────────────────────

class EvaluationCriterion(BaseModel):
    criterion: str   = Field(description="The name or description of the evaluation criterion")
    weight: Optional[Any] = Field(default=None, description="The weight/score (e.g., '60%', '30 points')")

class MandatoryDocument(BaseModel):
    document_name: str        = Field(description="The name of the required document")
    description: Optional[Any] = Field(default=None, description="Any specific format or details required")


# ── MAIN SCHEMA ───────────────────────────────────────────────────────────────

class RFPBrief(BaseModel):
    """Structured summary of an RFP, extracted by the Intake Agent."""

    # ── Identity ──────────────────────────────────────────────────────────────
    project_name:      Optional[Any] = Field(default="Unknown Project",      description="Name of the project or tender")
    client:            Optional[Any] = Field(default="Unknown Client",        description="Name of the issuing organisation")
    reference_number:  Optional[Any] = Field(default=None,                  description="Tender reference or bid number")
    country:           Optional[Any] = Field(default="Kenya",                 description="Country of the tender")

    # ── Timelines ─────────────────────────────────────────────────────────────
    deadline:          Optional[Any] = Field(default=None, description="Final submission deadline")
    enquiries_deadline: Optional[Any] = Field(default=None, description="Deadline for submitting clarification questions")

    # ── Overview ──────────────────────────────────────────────────────────────
    summary:           Optional[Any] = Field(default="No summary available",  description="2-3 sentence overview of the project scope")
    project_duration:  Optional[Any] = Field(default=None,                  description="How long the project must take")
    project_location:  Optional[Any] = Field(default=None,                  description="Where work must be performed")

    # ── Scope ─────────────────────────────────────────────────────────────────
    scope_of_work:     List[Any]    = Field(default_factory=list,            description="Key deliverables")
    out_of_scope:      List[Any]    = Field(default_factory=list,            description="Items explicitly excluded")

    # ── Evaluation ────────────────────────────────────────────────────────────
    evaluation_criteria:  List[EvaluationCriterion] = Field(default_factory=list, description="How the bid will be scored")
    technical_threshold:  Optional[Any]             = Field(default=None,         description="Min tech score")

    # ── Eligibility ───────────────────────────────────────────────────────────
    experience_requirements: List[Any] = Field(default_factory=list, description="Exp requirements")
    certifications_required: List[Any] = Field(default_factory=list, description="Specific certs")

    # ── Administrative ────────────────────────────────────────────────────────
    mandatory_documents: List[MandatoryDocument] = Field(default_factory=list, description="Docs that MUST be submitted")
    submission_method:   Optional[Any]           = Field(default=None,         description="How to submit")
    contact_person:      Optional[Any]           = Field(default=None,         description="Point of contact")

    # ── Commercial ────────────────────────────────────────────────────────────
    currency:       Optional[Any] = Field(default=None, description="Currency (KES, USD, etc)")
    preferencing:   Optional[Any] = Field(default=None, description="Local content policies")


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
        self.model  = "meta-llama/llama-4-scout-17b-16e-instruct"

    def extract_brief(self, text: str) -> RFPBrief:
        """
        Analyzes RFP text in batches to handle large documents (>40k chars).
        Splits text, extracts info from each part, and merges the results.
        """
        # Step 0: Cleanup
        text = "".join(char for char in text if char.isprintable() or char in "\n\r\t")
        
        # Define chunking parameters
        # 15,000 chars is ~3.7k tokens. llama-3.1-8b-instant has a 6,000 TPM limit on Groq free tier.
        CHUNK_SIZE = 15000 
        OVERLAP = 1000 
        
        chunks = []
        for i in range(0, len(text), CHUNK_SIZE - OVERLAP):
            chunks.append(text[i : i + CHUNK_SIZE])
            if i + CHUNK_SIZE >= len(text):
                break

        print(f"DEBUG: Processing document in {len(chunks)} batches...")
        import time

        master_brief = RFPBrief()

        for idx, chunk_text in enumerate(chunks):
            print(f"       -> Analyzing batch {idx+1}/{len(chunks)}...")
            chunk_brief = self._extract_chunk(chunk_text, batch_index=idx+1, total_batches=len(chunks))
            master_brief = self._merge_briefs(master_brief, chunk_brief)
            
            # Wait 10 seconds between batches to avoid TPM rate limit on Groq
            if idx < len(chunks) - 1:
                time.sleep(10)

        return master_brief

    def _extract_chunk(self, text: str, batch_index: int, total_batches: int) -> RFPBrief:
        """Helper to run LLM extraction on a single chunk of text."""
        system_prompt = (
            "You are an expert Bid Strategy Analyst. You are analyzing PART of a large RFP document.\n"
            f"CONTEXT: This is batch {batch_index} of {total_batches}.\n\n"
            "Extract a structured Bid Brief from this text. If information is NOT present in this specific part, "
            "return null or empty lists. Do not hallucinate.\n\n"
            "CRITICAL FIELDS TO FIND:\n"
            "1. PROJECT NAME / CLIENT / REF #\n"
            "2. DEADLINES (Submission vs Enquiries)\n"
            "3. EVALUATION CRITERIA (Weights %)\n"
            "4. SCOPE OF WORK & EXCLUSIONS\n"
            "5. ELIGIBILITY & CERTIFICATIONS\n"
            "6. MANDATORY DOCUMENTS\n\n"
            "Return ONLY a JSON object using these exact lowercase keys:\n"
            "project_name, client, reference_number, deadline, enquiries_deadline, summary,\n"
            "project_duration, project_location, scope_of_work (list), out_of_scope (list),\n"
            "evaluation_criteria (list of {criterion, weight}), technical_threshold,\n"
            "experience_requirements (list), certifications_required (list),\n"
            "mandatory_documents (list of {document_name, description}),\n"
            "submission_method, contact_person, currency, preferencing."
        )

        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": f"Analyze this text part:\n\n{text}"}
                ],
                model=self.model,
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            raw_json = chat_completion.choices[0].message.content
            return RFPBrief.model_validate_json(raw_json)
        except Exception as e:
            print(f"Error in batch {batch_index}: {e}")
            return RFPBrief() # Return empty brief on failure for this chunk

    def _merge_briefs(self, master: RFPBrief, new: RFPBrief) -> RFPBrief:
        """Merges a new chunk's data into the master brief."""
        
        def update_field(current, incoming, default_vals=["Unknown Project", "Unknown Client", "No summary available", "Kenya", None]):
            # If the incoming is a dict or list (LLM structure), serialize it to a clean string
            if isinstance(incoming, (dict, list)):
                import json
                try:
                    # If it's a simple dict with one key, just take the value
                    if isinstance(incoming, dict) and len(incoming) == 1:
                        incoming = list(incoming.values())[0]
                    # If it's a dict like {'submission': '18 Feb', 'enquiries': None}, join them
                    elif isinstance(incoming, dict):
                        parts = [f"{k}: {v}" for k, v in incoming.items() if v]
                        incoming = " | ".join(parts)
                    else:
                        incoming = str(incoming)
                except:
                    incoming = str(incoming)

            if incoming and incoming not in default_vals:
                return incoming
            return current

        # Update Single Fields (Keep existing if new is null/default)
        master.project_name    = update_field(master.project_name, new.project_name)
        master.client          = update_field(master.client, new.client)
        master.reference_number = update_field(master.reference_number, new.reference_number)
        master.country         = update_field(master.country, new.country)
        master.deadline        = update_field(master.deadline, new.deadline)
        master.enquiries_deadline = update_field(master.enquiries_deadline, new.enquiries_deadline)
        master.summary         = update_field(master.summary, new.summary)
        master.project_duration = update_field(master.project_duration, new.project_duration)
        master.project_location = update_field(master.project_location, new.project_location)
        master.technical_threshold = update_field(master.technical_threshold, new.technical_threshold)
        master.submission_method = update_field(master.submission_method, new.submission_method)
        master.contact_person  = update_field(master.contact_person, new.contact_person)
        master.currency        = update_field(master.currency, new.currency)
        master.preferencing    = update_field(master.preferencing, new.preferencing)

        # Merge Lists (Append and Deduplicate)
        master.scope_of_work = list(set(master.scope_of_work + new.scope_of_work))
        master.out_of_scope  = list(set(master.out_of_scope + new.out_of_scope))
        master.experience_requirements = list(set(master.experience_requirements + new.experience_requirements))
        master.certifications_required = list(set(master.certifications_required + new.certifications_required))

        # Merge List of Objects (Deduplicate by name)
        existing_crits = {c.criterion.lower(): c for c in master.evaluation_criteria}
        for c in new.evaluation_criteria:
            if c.criterion.lower() not in existing_crits:
                master.evaluation_criteria.append(c)

        existing_docs = {d.document_name.lower(): d for d in master.mandatory_documents}
        for d in new.mandatory_documents:
            if d.document_name.lower() not in existing_docs:
                master.mandatory_documents.append(d)

        return master
