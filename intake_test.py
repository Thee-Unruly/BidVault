import os
import sys
from dotenv import load_dotenv

# Add current dir to path
sys.path.append(os.getcwd())

from bidvault.ingestion.extractor import extract
from bidvault.ingestion.detector  import detect
from bidvault.agents.intake       import IntakeAgent

def test_intake():
    load_dotenv()
    
    # Path to a document (using the Data Protection Act as a test case)
    # In a real scenario, this would be a new RFP PDF
    file_path = r"C:\Users\ibrahim.fadhili\Downloads\Document Ingestion Pipeline\TOR-BID-NCS-RFP-GIPF-01-2025_IMPLEMENTATION-OF-GIPF-FILE-PLAN 2.pdf"
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    print(f"Analyzing Document: {file_path}")
    
    # 1. Extract text using the existing pipeline's extractor
    print("Step 1: Extracting text...")
    detection = detect(file_path)
    extraction = extract(file_path, detection)
    
    # 2. Run the Intake Agent
    print("Step 2: Running Intake Agent (Consulting the AI)...")
    agent = IntakeAgent()
    brief = agent.extract_brief(extraction.text)
    
    # 3. Display the results
    print("\n" + "="*50)
    print("RFP BID BRIEF")
    print("="*50)
    print(f"Project:    {brief.project_name}")
    print(f"Client:     {brief.client}")
    print(f"Ref #:      {brief.reference_number}")
    print(f"Deadline:   {brief.deadline}")
    print(f"\nSummary:\n{brief.summary}")
    
    print("\nEvaluation Criteria:")
    for crit in brief.evaluation_criteria:
        print(f"- {crit.criterion} ({crit.weight or 'No weight specified'})")
        
    print("\nMandatory Documents:")
    for doc in brief.mandatory_documents:
        print(f"- {doc.document_name}: {doc.description or 'No extra details'}")
        
    print("\nSubmission:")
    print(f"Method: {brief.submission_method}")
    print(f"Contact: {brief.contact_person}")
    print("="*50)

if __name__ == "__main__":
    test_intake()
