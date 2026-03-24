import os
import sys

# Resolve project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bidvault.ingestion.pipeline import IngestionPipeline, IngestionRequest
from bidvault.ingestion.metadata import DocumentAnalyzer, DocumentMetadata
from bidvault.ingestion.vector_store import VectorStore

class LegalAnalyzer(DocumentAnalyzer):
    """A sample analyzer for the 'Legal' domain."""
    
    def analyze(self, text: str, initial_meta: dict) -> dict:
        print("⚖️ LegalAnalyzer: Analyzing text for legal clauses...")
        extra = {}
        
        # Simple heuristic to identify legal fields
        text_lower = text.lower()
        if "confidentiality" in text_lower or "non-disclosure" in text_lower:
            extra["legal_category"] = "NDA"
        elif "litigation" in text_lower or "dispute" in text_lower:
            extra["legal_category"] = "Litigation"
        else:
            extra["legal_category"] = "General Legal"
            
        extra["jurisdiction"] = "Kenya" # Dummy hardcoded field
        return extra

    def infer_section_type(self, hint: str) -> str:
        """Map legal-specific headings to standardized types."""
        hint_lower = hint.lower()
        if "preamble" in hint_lower:
            return "preamble"
        if "definitions" in hint_lower:
            return "definitions"
        if "governing law" in hint_lower:
            return "jurisdiction"
        return "general"

def test_generalization():
    print("🚀 Starting Generalization Test (Legal Domain)")
    
    # Initialize the pipeline with the custom LegalAnalyzer
    pipeline = IngestionPipeline(
        analyzer=LegalAnalyzer(),
        vector_store=VectorStore(),
        dry_run=False
    )
    
    # Path to a sample PDF (reusing the same one for simplicity)
    sample_path = os.path.join(ROOT, "data", "Data Protection Act.pdf")
    
    request = IngestionRequest(
        file_path=sample_path,
        source_type="legal_act",
        extra={"client_id": "LAW-123"} # Custom extra field
    )
    
    print(f"📄 Ingesting legal document: {sample_path}")
    result = pipeline.ingest(request)
    
    if result.success:
        print("\n✅ LEGAL INGESTION SUCCESS")
        print(f"Chunks stored: {result.chunks_stored}")
        
        # Verify with a quick search
        print("\n🔍 Verifying stored metadata via search...")
        from bidvault.ingestion.embedder import Embedder
        embedder = Embedder()
        vs = VectorStore()
        
        # Search for something and check metadata
        query_embedding = embedder.embed("disclosure of data")
        search_results = vs.search(query_embedding, top_k=1)
        
        if search_results:
            meta = search_results[0].metadata
            print(f"Found Chunk Metadata:")
            print(f"  - Source Type:   {meta.get('source_type')}")
            print(f"  - Legal Category: {meta.get('legal_category')}")
            print(f"  - Jurisdiction:   {meta.get('jurisdiction')}")
            print(f"  - Client ID:      {meta.get('client_id')}")
            
            if meta.get("legal_category") == "General Legal":
                print("\n🎉 META-VALIDATION PASSED: Custom fields correctly stored!")
    else:
        print(f"❌ Error: {result.error}")

if __name__ == "__main__":
    test_generalization()
