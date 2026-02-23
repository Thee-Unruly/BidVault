from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import date

class EvaluationCriterion(BaseModel):
    criterion: str = Field(description="The name or description of the evaluation criterion")
    weight: Optional[str] = Field(description="The weight or score assigned to this criterion (e.g., '20%', '30 points')")

class MandatoryDocument(BaseModel):
    document_name: str = Field(description="The name of the required document")
    description: Optional[str] = Field(description="Any specific details or formats required for this document")

class RFPBrief(BaseModel):
    """The structured summary of an RFP extracted by the Intake Agent."""
    project_name: str = Field(default="Unknown Project", description="The name of the project or tender")
    client: str = Field(default="Unknown Client", description="The name of the issuing client or organization")
    reference_number: Optional[str] = Field(default=None, description="The tender reference or ID number")
    deadline: Optional[str] = Field(default=None, description="The submission deadline as stated in the document")
    summary: str = Field(default="No summary available", description="A brief 2-3 sentence overview of the project scope")
    
    evaluation_criteria: List[EvaluationCriterion] = Field(default_factory=list, description="List of how the bid will be scored")
    mandatory_documents: List[MandatoryDocument] = Field(default_factory=list, description="List of administrative/technical documents that MUST be submitted")
    technical_threshold: Optional[str] = Field(description="The minimum technical score required to pass to financial evaluation")
    
    contact_person: Optional[str] = Field(description="Point of contact for inquiries")
    submission_method: Optional[str] = Field(description="How to submit (e.g., 'Via Portal', 'Physical Copy', 'Email')")

class IntakeAgent:
    """
    The Intake Agent analyzes new RFPs to extract structured requirements.
    It feeds the Drafting Agent with the context needed to write the proposal.
    """
    def __init__(self, api_key: Optional[str] = None):
        import os
        from groq import Groq
        
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found in environment")
            
        self.client = Groq(api_key=self.api_key)
        self.model = "llama-3.3-70b-versatile" # Powerful model for extraction

    def extract_brief(self, text: str) -> RFPBrief:
        """
        Uses LLM to extract structured RFPBrief from raw text.
        We typically only need the first 20-30 pages of an RFP to find these details.
        """
        import json
        
        # System prompt to enforce structure
        system_prompt = (
            "You are a Senior Bid Manager. Your task is to analyze the provided RFP text "
            "and extract a structured Bid Brief. Focus on administrative requirements, "
            "evaluation criteria, and deadlines. If a field is not found, leave it empty or null. "
            "Return the result strictly as a JSON object matching the requested schema."
        )
        
        # Truncate text to fit context window (RFPs can be long)
        # 15,000 characters is usually enough for the intro/instructions sections
        context_text = text[:20000] 

        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract the Bid Brief from this RFP text:\n\n{context_text}"}
                ],
                model=self.model,
                response_format={"type": "json_object"},
                temperature=0.1, # Low temperature for extraction accuracy
            )
            
            raw_json = chat_completion.choices[0].message.content
            return RFPBrief.model_validate_json(raw_json)
            
        except Exception as e:
            print(f"Error in Intake Agent extraction: {e}")
            raise
