import os
import sys

# Resolve project root so bidvault package is importable regardless of CWD
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# We mock ONLY the database layer. 
# The Embedder will now be REAL and run locally on your machine.
from bidvault.ingestion.pipeline import IngestionPipeline, IngestionRequest
from bidvault.ingestion.vector_store import VectorStore

def run_manual_test():
    print("🚀 Starting Manual Ingestion Test (Local Offline Mode)")
    print("💡 Saving to real Postgres database...\n")
    
    # Setting this to 'local' explicitly for the test
    os.environ["EMBEDDING_PROVIDER"] = "local"
    
    # Initialize the pipeline with REAL VectorStore
    pipeline = IngestionPipeline(
        vector_store=VectorStore(),
        dry_run=False
    )
    
    # Path to your Data Protection Act PDF
    sample_path = os.path.join(ROOT, "data", "Data Protection Act.pdf")
    
    # DYNAMIC REQUEST: The code will now infer the rest!
    request = IngestionRequest(
        file_path=sample_path
    )
    
    print(f"📄 Ingesting file: {sample_path}")
    
    # Run the pipeline
    result = pipeline.ingest(request)
    
    # Print results
    print("\n" + "="*30)
    print("LOCAL INGESTION COMPLETE")
    print("="*30)
    print(f"Success:           {result.success}")
    if result.success:
        print(f"Chunks Embedded:   {result.chunks_stored}")
        print(f"Doc Type:          {result.doc_type}")
        print(f"Extraction Method: {result.extraction_method}")
        print(f"Dimensions:        384 (FastEmbed)")
        print(f"Duration:          {result.duration_seconds:.2f}s")
        
        if result.warnings:
            print("\n⚠️ Warnings:")
            for w in result.warnings:
                print(f"  - {w}")
    else:
        print(f"❌ Error: {result.error}")

if __name__ == "__main__":
    run_manual_test()
