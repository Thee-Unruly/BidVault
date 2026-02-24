import os
import sys
from dotenv import load_dotenv

# Resolve project root so bidvault package is importable regardless of CWD
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bidvault.ingestion.extractor import extract
from bidvault.ingestion.detector  import detect
from bidvault.agents.intake       import IntakeAgent

def test_intake():
    load_dotenv()

    file_path = os.path.join(ROOT, "data", "Microsoft-Unified-Support-9.2.2026 1.pdf")

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

    # ── DISPLAY (Professional Bid Brief Template) ──────────────────────────────
    
    print("\n" + "="*80)
    print("REQUEST FOR PROPOSAL (RFP) – BID BRIEF")
    print("="*80)

    print("\n1. Tender Identification")
    print(f"{'Item':<20} | {'Details'}")
    print("-" * 60)
    print(f"{'Project Title':<20} | {brief.project_name}")
    print(f"{'Client':<20} | {brief.client}")
    print(f"{'Reference Number':<20} | {brief.reference_number or 'N/A'}")
    print(f"{'Country':<20} | {brief.country or 'Kenya'}")

    print("\n2. Key Timelines")
    print(f"{'Milestone':<25} | {'Date'}")
    print("-" * 60)
    print(f"{'Enquiries Deadline':<25} | {brief.enquiries_deadline or 'Not specified'}")
    print(f"{'Submission Deadline':<25} | {brief.deadline or 'Not specified'}")
    print(f"{'Contract Duration':<25} | {brief.project_duration or 'Not specified'}")

    print("\n3. Project Overview")
    print(f"{'Item':<20} | {'Description'}")
    print("-" * 60)
    print(f"{'Location':<20} | {brief.project_location or 'Not specified'}")
    print(f"{'Duration':<20} | {brief.project_duration or 'Not specified'}")
    print(f"{'Project Summary':<20} | {brief.summary}")

    print("\n4. Scope of Work")
    print("\nThe successful bidder will provide:")
    if brief.scope_of_work:
        for idx, item in enumerate(brief.scope_of_work, 1):
            print(f"  4.{idx} {item}")
    else:
        print("  None specified in the tender document.")

    print("\n5. Out of Scope")
    if brief.out_of_scope:
        for item in brief.out_of_scope:
            print(f"  - {item}")
    else:
        print("  None specified in the tender document.")

    print("\n6. Evaluation Criteria")
    print(f"{'Criteria':<25} | {'Details'}")
    print("-" * 60)
    print(f"{'Technical Threshold':<25} | {brief.technical_threshold or 'Not specified'}")
    if brief.evaluation_criteria:
        for crit in brief.evaluation_criteria:
            print(f"{crit.criterion:<25} | {crit.weight or 'Not weighted'}")
    else:
        print(f"{'Evaluation Framework':<25} | Not extracted")

    print("\n7. Eligibility Requirements")
    print("\nBidders must demonstrate:")
    if brief.experience_requirements:
        for req in brief.experience_requirements:
            print(f"  - {req}")
    else:
        print("  None specified.")

    print("\n8. Certifications Required")
    if brief.certifications_required:
        for cert in brief.certifications_required:
            print(f"  - {cert}")
    else:
        print("  None specified.")

    print("\n9. Mandatory Documents")
    print("\nThe following documents must be submitted:")
    if brief.mandatory_documents:
        # Grouping logic could be added here, but for now we list them nicely
        for idx, doc in enumerate(brief.mandatory_documents, 1):
            print(f"  9.{idx} {doc.document_name}: {doc.description or ''}")
    else:
        print("  None specified.")

    print("\n10. Commercial Details")
    print(f"{'Item':<20} | {'Details'}")
    print("-" * 60)
    print(f"{'Currency':<20} | {brief.currency or 'Not specified'}")
    print(f"{'Preferencing':<20} | {brief.preferencing or 'None stated'}")

    print("\n11. Submission Details")
    print(f"{'Item':<20} | {'Details'}")
    print("-" * 60)
    print(f"{'Submission Method':<20} | {brief.submission_method or 'Not specified'}")
    print(f"{'Submission Contact':<20} | {brief.contact_person or 'Not specified'}")

    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    test_intake()
