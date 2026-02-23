"""
ask_ai.py
─────────
The 'Final Boss' of our pipeline.
It takes a natural language question, searches the local vector store,
and uses Groq (Llama 3) to provide a human-like answer based on the retrieved context.
"""

import os
import sys
from groq import Groq
from dotenv import load_dotenv
from bidvault.ingestion.vector_store import VectorStore
from bidvault.ingestion.embedder import Embedder

# Load environment variables (GROQ_API_KEY)
load_dotenv()

def ask_bidvault(question: str):
    print(f"\n🤔 Question: {question}")
    
    # 1. Initialize our local components
    store = VectorStore()
    embedder = Embedder()
    
    # 2. Get Search Results (Retrieval)
    print("⏳ Searching local knowledge base...")
    query_vector = embedder.embed(question)
    results = store.search(query_vector, top_k=3)
    
    if not results:
        print("❌ No relevant information found in the local database.")
        return

    # 3. Prepare Context for the LLM
    context_text = "\n\n".join([
        f"--- FROM DOCUMENT: {res.metadata.file_name} (Year: {res.metadata.year}) ---\n{res.text}"
        for res in results
    ])
    
    print(f"✅ Found {len(results)} relevant sections. Consulting Llama 3 on Groq...")

    # 4. Prompt Engineering
    system_prompt = (
        "You are an expert legal and proposal assistant for a Kenyan firm. "
        "Your task is to answer the user's question using ONLY the provided context snippets. "
        "If the answer is not in the context, say you don't know based on the current data. "
        "Always cite the document name and year in your answer. "
        "Keep your tone professional and helpful."
    )
    
    user_prompt = f"CONTEXT:\n{context_text}\n\nUSER QUESTION: {question}"

    # 5. Call Groq
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("\n⚠️ ERROR: GROQ_API_KEY not found in .env file.")
        print("Please add: GROQ_API_KEY=your_key_here")
        return

    client = Groq(api_key=api_key)
    
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model="llama-3.3-70b-versatile", # Or your preferred Groq model
            temperature=0.2, # Lower temperature for factual accuracy
        )
        
        answer = chat_completion.choices[0].message.content
        
        print("\n" + "="*50)
        print("🤖 AI RESPONSE:")
        print("="*50)
        print(answer)
        print("="*50 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error calling Groq: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Ask the question passed as argument
        ask_bidvault(" ".join(sys.argv[1:]))
    else:
        # Default test question
        ask_bidvault("What are the rights of a data subject under the Kenya Data Protection Act?")
