"""Embed the SOP and upsert searchable chunks into Pinecone."""

from __future__ import annotations

import os
import re
import time
import hashlib
import json
from pathlib import Path

from dotenv import load_dotenv
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_WORDS = 180
CHUNK_OVERLAP = 35
DEFAULT_BATCH_SIZE = 16
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 2


def split_sop(text: str) -> list[dict[str, str]]:
    sections = re.split(r"(?=^#{1,3} )", text, flags=re.MULTILINE)
    chunks: list[dict[str, str]] = []

    for section_number, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue

        lines = section.splitlines()
        heading = next(
            (line.lstrip("#").strip() for line in lines if line.startswith("#")),
            "SOP",
        )
        words = section.split()
        start = 0
        part = 0
        while start < len(words):
            end = min(start + CHUNK_WORDS, len(words))
            chunk_text = " ".join(words[start:end]).strip()
            if not chunk_text:
                break
            chunks.append(
                {
                    "text": chunk_text,
                    "section": heading,
                    "section_number": str(section_number),
                    "chunk_number": str(part),
                }
            )
            if end == len(words):
                break
            start = end - CHUNK_OVERLAP
            part += 1

    if not chunks:
        raise ValueError("The SOP did not contain any content to ingest")
    return chunks


def wait_until_ready(index, attempts: int = 30) -> None:
    for attempt in range(1, attempts + 1):
        try:
            index.describe_index_stats()
            return
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(2)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def retry_batch_operation(operation, description: str, max_retries: int, backoff: int):
    for attempt in range(1, max_retries + 2):
        try:
            return operation()
        except Exception:
            if attempt > max_retries:
                raise
            delay = backoff * (2 ** (attempt - 1))
            print(
                f"{description} failed on attempt {attempt}; "
                f"retrying in {delay}s..."
            )
            time.sleep(delay)


def main() -> None:
    policy_path = PROJECT_ROOT / "data/policy/Cold_Chain_Incident_SOP_v2.md"
    if not policy_path.is_file():
        raise FileNotFoundError(f"SOP not found: {policy_path}")

    client = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index_name = os.getenv("PINECONE_INDEX_NAME", "logistics-policy")
    namespace = os.getenv("PINECONE_NAMESPACE", "sop")
    batch_size = int(os.getenv("PINECONE_BATCH_SIZE", str(DEFAULT_BATCH_SIZE)))
    max_retries = int(
        os.getenv("PINECONE_MAX_RETRIES", str(DEFAULT_MAX_RETRIES))
    )
    retry_backoff = int(
        os.getenv(
            "PINECONE_RETRY_BACKOFF_SECONDS",
            str(DEFAULT_RETRY_BACKOFF_SECONDS),
        )
    )
    if batch_size < 1:
        raise ValueError("PINECONE_BATCH_SIZE must be at least 1")
    if max_retries < 0:
        raise ValueError("PINECONE_MAX_RETRIES cannot be negative")
    if retry_backoff < 1:
        raise ValueError("PINECONE_RETRY_BACKOFF_SECONDS must be positive")

    index = client.Index(index_name)
    wait_until_ready(index)

    source_hash = file_hash(policy_path)
    manifest_path = PROJECT_ROOT / "data/cache/pinecone_ingestion_manifest.json"
    manifest = load_manifest(manifest_path)
    stats = index.describe_index_stats()
    namespace_stats = stats.get("namespaces", {}).get(namespace, {})
    if (
        manifest.get(str(policy_path.relative_to(PROJECT_ROOT)), {}).get("sha256")
        == source_hash
        and namespace_stats.get("vector_count", 0) > 0
    ):
        print("SOP is unchanged and already indexed; skipping ingestion.")
        return

    chunks = split_sop(policy_path.read_text(encoding="utf-8"))
    model = SentenceTransformer(MODEL_NAME)
    source = str(policy_path.relative_to(PROJECT_ROOT))
    previous_count = manifest.get(source, {}).get("chunk_count", 0)
    if previous_count > len(chunks):
        stale_ids = [
            f"sop-{number:04d}" for number in range(len(chunks), previous_count)
        ]
        retry_batch_operation(
            lambda: index.delete(ids=stale_ids, namespace=namespace),
            "Stale-vector deletion",
            max_retries,
            retry_backoff,
        )

    total_upserted = 0
    for batch_start in range(0, len(chunks), batch_size):
        batch = chunks[batch_start : batch_start + batch_size]
        vectors = retry_batch_operation(
            lambda: model.encode(
                [chunk["text"] for chunk in batch],
                normalize_embeddings=True,
                show_progress_bar=False,
            ),
            f"Embedding batch {batch_start // batch_size + 1}",
            max_retries,
            retry_backoff,
        )
        records = []
        for offset, (chunk, vector) in enumerate(zip(batch, vectors, strict=True)):
            number = batch_start + offset
            records.append(
                {
                    "id": f"sop-{number:04d}",
                    "values": vector.tolist(),
                    "metadata": {
                        "source": source,
                        "document": "Cold_Chain_Incident_SOP_v2",
                        "global_chunk_number": number,
                        "section": chunk["section"],
                        "section_number": chunk["section_number"],
                        "section_chunk_number": chunk["chunk_number"],
                        "text": chunk["text"],
                    },
                }
            )
        retry_batch_operation(
            lambda: index.upsert(vectors=records, namespace=namespace),
            f"Pinecone upsert batch {batch_start // batch_size + 1}",
            max_retries,
            retry_backoff,
        )
        total_upserted += len(records)
        print(
            f"Upserted batch {batch_start // batch_size + 1}: "
            f"{len(records)} chunks"
        )

    manifest[source] = {
        "sha256": source_hash,
        "chunk_count": len(chunks),
        "namespace": namespace,
        "model": MODEL_NAME,
    }
    save_manifest(manifest_path, manifest)
    stats = index.describe_index_stats()
    print(
        f"Upserted {total_upserted} SOP chunks into "
        f"{index_name!r}, namespace {namespace!r}."
    )
    print(f"Index namespaces: {stats.get('namespaces', {})}")


if __name__ == "__main__":
    main()
