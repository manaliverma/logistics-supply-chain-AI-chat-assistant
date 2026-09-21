"""Search the indexed SOP through LangChain's PineconeVectorStore."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_pinecone import PineconeVectorStore


ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def build_vector_store() -> PineconeVectorStore:
    """Build a LangChain store using the same local model as ingestion."""
    load_dotenv(ROOT / ".env")
    embeddings = HuggingFaceEmbeddings(
        model_name=MODEL_NAME,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    return PineconeVectorStore(
        index_name=os.environ["PINECONE_INDEX_NAME"],
        embedding=embeddings,
        namespace=os.getenv("PINECONE_NAMESPACE", "sop"),
        pinecone_api_key=os.environ["PINECONE_API_KEY"],
    )


def main() -> int:
    """Search the SOP with a user-provided natural-language question."""
    parser = argparse.ArgumentParser(description="Search the logistics SOP.")
    parser.add_argument("question", help="Natural-language SOP question.")
    parser.add_argument("-k", type=int, default=3, help="Number of results.")
    args = parser.parse_args()
    if args.k < 1:
        raise ValueError("k must be at least 1")

    vector_store = build_vector_store()
    documents = vector_store.similarity_search(args.question, k=args.k)
    if not documents:
        print("No matching SOP chunks found.")
        return 0

    for number, document in enumerate(documents, start=1):
        print(f"\n--- Result {number} ---")
        print(f"Section: {document.metadata.get('section', 'unknown')}")
        print(f"Source: {document.metadata.get('source', 'unknown')}")
        print(document.page_content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
