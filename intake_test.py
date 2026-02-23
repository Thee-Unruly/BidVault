import os
import sys
from dotenv import load_dotenv

sys.path.append(os.getcwd())

from bidvault.ingestion.extractor import extract
from bidvault.ingestion.detector  import detect
from bidvault.agents.intake       import IntakeAgent

def test_intake():
    load_dotenv()

    file_path = r"C:\Users\ibrahim.fadhili\Downloads\Document Ingestion Pipeline\TOR-BID-NCS-RFP-GIPF-01-2025_IMPLEMENTATION-OF-GIPF-FILE-PLAN 2.pdf"

    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    print(f"Analyzing: {file_path}\n")

    print("Step 1: Extracting text...")
    detection  = detect(file_path)
    extraction = extract(file_path, detection)
    print(f"         {extraction.char_count:,} characters extracted via {extraction.extraction_method}\n")

    print("Step 2: Running Intake Agent...")
    agent = IntakeAgent()
    brief = agent.extract_brief(extraction.text)

    # ── DISPLAY ───────────────────────────────────────────────────────────────
    sep = "=" * 55

    print(f"\n{sep}")
    print("  RFP BID BRIEF")
    print(sep)

    print(f"\n[IDENTITY]")
    print(f"  Project   : {brief.project_name}")
    print(f"  Client    : {brief.client}")
    print(f"  Ref #     : {brief.reference_number or 'N/A'}")

    print(f"\n[TIMELINES]")
    print(f"  Submission Deadline  : {brief.deadline or 'Not found'}")
    print(f"  Enquiries Deadline   : {brief.enquiries_deadline or 'Not found'}")

    print(f"\n[PROJECT OVERVIEW]")
    print(f"  Duration  : {brief.project_duration or 'Not specified'}")
    print(f"  Location  : {brief.project_location or 'Not specified'}")
    print(f"  Summary   : {brief.summary}")

    print(f"\n[SCOPE OF WORK]")
    if brief.scope_of_work:
        for item in brief.scope_of_work:
            print(f"  + {item}")
    else:
        print("  None extracted")

    print(f"\n[OUT OF SCOPE]")
    if brief.out_of_scope:
        for item in brief.out_of_scope:
            print(f"  - {item}")
    else:
        print("  None extracted")

    print(f"\n[EVALUATION CRITERIA]")
    if brief.evaluation_criteria:
        for crit in brief.evaluation_criteria:
            print(f"  - {crit.criterion} ({crit.weight or 'unweighted'})")
    else:
        print("  None extracted")
    print(f"  Technical Threshold : {brief.technical_threshold or 'Not specified'}")

    print(f"\n[ELIGIBILITY]")
    if brief.experience_requirements:
        for req in brief.experience_requirements:
            print(f"  - {req}")
    else:
        print("  None extracted")

    print(f"\n[CERTIFICATIONS REQUIRED]")
    if brief.certifications_required:
        for cert in brief.certifications_required:
            print(f"  - {cert}")
    else:
        print("  None extracted")

    print(f"\n[MANDATORY DOCUMENTS]")
    if brief.mandatory_documents:
        for doc in brief.mandatory_documents:
            print(f"  - {doc.document_name}: {doc.description or ''}")
    else:
        print("  None extracted")

    print(f"\n[COMMERCIAL]")
    print(f"  Currency     : {brief.currency or 'Not specified'}")
    print(f"  Preferencing : {brief.preferencing or 'None stated'}")

    print(f"\n[SUBMISSION]")
    print(f"  Method  : {brief.submission_method or 'Not specified'}")
    print(f"  Contact : {brief.contact_person or 'Not specified'}")

    print(f"\n{sep}\n")

if __name__ == "__main__":
    test_intake()
