"""
search_test.py
──────────────
Demonstrates how to differentiate documents and perform semantic search.
"""

import os
import sys
from bidvault.ingestion.vector_store import VectorStore, SearchFilters
from bidvault.ingestion.embedder import Embedder

def run_search_demo():
    print("🔍 Semantic Search & Document Differentiation Demo\n")
    
    store = VectorStore()
    embedder = Embedder()
    
    # 1. Ask a question related to the Data Protection Act we just ingested
    query = "What are the rights of a data subject?"
    print(f"Question: '{query}'")
    
    # 2. Convert question to vector
    print("⏳ Embedding query...")
    query_vector = embedder.embed(query)
    
    # 3. Search high-similarity chunks
    print("⏳ Searching database...")
    results = store.search(query_vector, top_k=3)
    
    if not results:
        print("❌ No results found. Did you run manual_test.py first?")
        return

    print(f"\n✅ Found {len(results)} matching chunks:\n")
    
    for i, res in enumerate(results, 1):
        print(f"--- Result {i} (Similarity: {res.similarity:.2%}) ---")
        print(f"📄 DOCUMENT:  {res.metadata.file_name}")
        print(f"🆔 DOC ID:    {res.metadata.document_id}")
        print(f"📂 SECTOR:    {res.metadata.sector}")
        print(f"📅 YEAR:      {res.metadata.year}")
        print(f"📝 SNIPPET:   {res.text[:150]}...")
        print("-" * 40 + "\n")

    # 4. Demonstrate differentiation by searching ONLY in a specific file
    # (Assuming we have the ID for the Data Protection Act)
    doc_id = results[0].metadata.document_id
    if doc_id:
        print(f"🎯 Filtering search to specifically target Document ID: {doc_id}")
        filtered_results = store.search(
            query_vector, 
            filters=SearchFilters(document_id=doc_id),
            top_k=1
        )
        if filtered_results:
            print(f"✅ Re-verified chunk from: {filtered_results[0].metadata.file_name}")

if __name__ == "__main__":
    run_search_demo()
