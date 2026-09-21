"""Create the Pinecone index for the local sentence-transformer embeddings."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec


def main() -> None:
    """Create the configured 384-dimensional cosine Pinecone index if absent."""
    load_dotenv(".env")
    client = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index_name = os.getenv("PINECONE_INDEX_NAME", "logistics-policy")

    if client.has_index(index_name):
        print(f"Index already exists: {index_name}")
        return

    client.create_index(
        name=index_name,
        dimension=384,
        metric="cosine",
        spec=ServerlessSpec(
            cloud=os.getenv("PINECONE_CLOUD", "aws"),
            region=os.getenv("PINECONE_REGION", "us-east-1"),
        ),
    )
    print(f"Created index: {index_name}")


if __name__ == "__main__":
    main()
