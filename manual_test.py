import os
import sys

# Add the current directory to sys.path so we can import the bidvault package
sys.path.append(os.getcwd())

# We mock ONLY the database layer. 
# The Embedder will now be REAL and run locally on your machine.
class MockVectorStore:
    def store_chunks_batch(self, items): return len(items)

from bidvault.ingestion.pipeline import IngestionPipeline, IngestionRequest

def run_manual_test():
    print("🚀 Starting Manual Ingestion Test (Local Offline Mode)")
    print("💡 Note: The first run will download a small model (~100MB).\n")
    
    # Setting this to 'local' explicitly for the test
    os.environ["EMBEDDING_PROVIDER"] = "local"
    
    # Initialize the pipeline
    # VectorStore is mocked to avoid needing Postgres
    # Embedder is REAL
    pipeline = IngestionPipeline(
        vector_store=MockVectorStore(),
        dry_run=False # We want to see it actually embed!
    )
    
    # Path to your Data Protection Act PDF
    sample_path = r"C:\Users\ibrahim.fadhili\Downloads\Document Ingestion Pipeline\Data Protection Act.pdf"
    
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
