"""
embedder.py
───────────
Generates embeddings for text chunks using Azure OpenAI.
Handles batching, retries, and rate limiting.

ENVIRONMENT VARIABLES:
  AZURE_OPENAI_API_KEY
  AZURE_OPENAI_ENDPOINT          — e.g. https://your-resource.openai.azure.com
  AZURE_OPENAI_EMBEDDING_DEPLOYMENT — e.g. text-embedding-3-large

NOTE: If you're on regular OpenAI (not Azure), set USE_AZURE=false
and provide OPENAI_API_KEY instead. The switch is handled below.
"""

import os
import time
from typing import Optional


class Embedder:
    """
    Wraps the OpenAI embedding API.
    Supports both Azure OpenAI and regular OpenAI.
    """

    def __init__(
        self,
        deployment:     Optional[str] = None,
        use_azure:      bool = True,
        dimensions:     int = 3072,     # text-embedding-3-large max
    ):
        self.deployment = deployment or os.environ.get(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large"
        )
        self.dimensions = dimensions
        self.use_azure  = use_azure
        self._client    = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            from openai import AzureOpenAI, OpenAI
        except ImportError:
            raise ImportError("Run: pip install openai")

        if self.use_azure:
            self._client = AzureOpenAI(
                api_key       = os.environ["AZURE_OPENAI_API_KEY"],
                azure_endpoint= os.environ["AZURE_OPENAI_ENDPOINT"],
                api_version   = "2024-02-01",
            )
        else:
            self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        return self._client

    def embed(self, text: str) -> list[float]:
        """Embed a single text string. Returns a list of floats."""
        return self.embed_batch([text])[0]

    def embed_batch(
        self,
        texts:       list[str],
        batch_size:  int = 100,
        retry_limit: int = 3,
        retry_delay: float = 2.0,
    ) -> list[list[float]]:
        """
        Embed a list of texts.
        Automatically batches to avoid hitting API limits.
        Retries on rate limit errors with exponential backoff.

        Azure OpenAI limit: 2048 inputs per request, ~8192 tokens per input.
        We use batch_size=100 as a safe default.
        """
        client     = self._get_client()
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            # Clean texts — empty strings cause API errors
            batch = [t.strip() or "." for t in batch]

            for attempt in range(retry_limit):
                try:
                    response = client.embeddings.create(
                        model      = self.deployment,
                        input      = batch,
                        dimensions = self.dimensions,
                    )
                    embeddings = [item.embedding for item in sorted(
                        response.data, key=lambda x: x.index
                    )]
                    all_embeddings.extend(embeddings)
                    break

                except Exception as e:
                    error_str = str(e).lower()
                    if "rate limit" in error_str or "429" in error_str:
                        wait = retry_delay * (2 ** attempt)
                        print(f"Rate limited. Waiting {wait}s before retry {attempt+1}/{retry_limit}")
                        time.sleep(wait)
                    elif attempt == retry_limit - 1:
                        raise RuntimeError(
                            f"Embedding failed after {retry_limit} attempts: {e}"
                        ) from e
                    else:
                        time.sleep(retry_delay)

        return all_embeddings
