"""
embedder.py
───────────
High-performance embedding module.
Default: Local offline embeddings via FastEmbed (Free, Fast, No Keys).
Optional: Azure OpenAI or standard OpenAI.

ENVIRONMENT VARIABLES:
  EMBEDDING_PROVIDER — "local" (default), "azure", or "openai"
  
  # For Azure:
  AZURE_OPENAI_API_KEY
  AZURE_OPENAI_ENDPOINT
  
  # For OpenAI:
  OPENAI_API_KEY
"""

import os
import time
from typing import Optional, List


class Embedder:
    """
    Wraps multiple embedding providers.
    Optimized for local-first use to save costs and work offline.
    """

    def __init__(
        self,
        provider:   Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.provider = provider or os.environ.get("EMBEDDING_PROVIDER", "local").lower()
        
        # Default models for each provider
        if self.provider == "local":
            self.model_name = model_name or "BAAI/bge-small-en-v1.5"
            self.dimensions = 384
        else:
            self.model_name = model_name or "text-embedding-3-large"
            self.dimensions = 3072

        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        if self.provider == "local":
            try:
                from fastembed import TextEmbedding
                self._client = TextEmbedding(model_name=self.model_name)
            except ImportError:
                raise ImportError("Run: pip install fastembed")
        
        elif self.provider == "azure":
            from openai import AzureOpenAI
            self._client = AzureOpenAI(
                api_key       = os.environ["AZURE_OPENAI_API_KEY"],
                azure_endpoint= os.environ["AZURE_OPENAI_ENDPOINT"],
                api_version   = "2024-02-01",
            )
        
        else: # Standard OpenAI
            from openai import OpenAI
            self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        return self._client

    def embed(self, text: str) -> List[float]:
        """Embed a single string."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of strings."""
        client = self._get_client()
        
        if self.provider == "local":
            # fastembed returns a generator of numpy arrays
            embeddings = list(client.embed(texts))
            # Convert to list of lists for JSON/Postgres compatibility
            return [e.tolist() for e in embeddings]

        # Cloud Providers (OpenAI/Azure)
        all_embeddings = []
        batch_size = 100
        
        for i in range(0, len(texts), batch_size):
            batch = [t.strip() or "." for t in texts[i : i + batch_size]]
            
            response = client.embeddings.create(
                model      = self.model_name,
                input      = batch,
                dimensions = self.dimensions if self.provider != "azure" else None
            )
            
            batch_embeddings = [item.embedding for item in sorted(
                response.data, key=lambda x: x.index
            )]
            all_embeddings.extend(batch_embeddings)
            
        return all_embeddings
