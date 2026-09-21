"""Validate Pinecone credentials and list available indexes."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from pinecone import Pinecone


def main() -> int:
    """Validate the Pinecone key and print indexes visible to the account."""
    load_dotenv()
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "PINECONE_API_KEY is missing. Add it to the local .env file."
        )

    client = Pinecone(api_key=api_key)
    indexes = client.list_indexes()
    names = [item["name"] for item in indexes]

    print("Pinecone authentication succeeded.")
    if names:
        print("Available indexes:")
        for name in names:
            print(f"- {name}")
    else:
        print("No indexes found.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Pinecone check failed: {error}", file=sys.stderr)
        raise
