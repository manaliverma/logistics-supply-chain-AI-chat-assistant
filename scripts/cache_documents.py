"""Extract supported documents and cache their text as hash-addressed JSON."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".xls", ".xlsx", ".pdf"}


class DocumentParser(ABC):
    """Common parser interface for every supported document type."""

    @abstractmethod
    def parse(self, path: Path) -> tuple[str, dict[str, Any]]:
        """Extract normalized text and format metadata from one source file."""
        """Return normalized text and structured metadata."""


class TextParser(DocumentParser):
    def parse(self, path: Path) -> tuple[str, dict[str, Any]]:
        """Read text or Markdown using common encodings with fallback."""
        for encoding in ("utf-8-sig", "utf-16", "cp1252"):
            try:
                text = path.read_text(encoding=encoding)
                if not text.strip():
                    raise ValueError(f"Text document is empty: {path}")
                return text, {"format": path.suffix.lower()[1:], "encoding": encoding}
            except UnicodeDecodeError:
                continue
        raise ValueError(f"Could not decode text file: {path}")


class CsvParser(DocumentParser):
    def parse(self, path: Path) -> tuple[str, dict[str, Any]]:
        """Convert CSV rows into normalized line-oriented document text."""
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        if not rows:
            raise ValueError(f"CSV has no data rows: {path}")
        text = "\n".join(
            " | ".join(f"{key}: {value}" for key, value in row.items())
            for row in rows
        )
        return text, {"format": "csv", "row_count": len(rows)}


class SpreadsheetParser(DocumentParser):
    def parse(self, path: Path) -> tuple[str, dict[str, Any]]:
        """Extract worksheet names and cell values from an Excel workbook."""
        workbook = pd.ExcelFile(path)
        sheets: dict[str, list[dict[str, Any]]] = {}
        text_parts: list[str] = []
        for sheet in workbook.sheet_names:
            dataframe = pd.read_excel(workbook, sheet_name=sheet)
            records = [
                {str(key): json_value(value) for key, value in row.items()}
                for row in dataframe.to_dict(orient="records")
            ]
            sheets[sheet] = records
            text_parts.append(
                f"Sheet: {sheet}\n"
                + "\n".join(
                    " | ".join(f"{key}: {value}" for key, value in row.items())
                    for row in records
                )
            )
        text = "\n\n".join(text_parts)
        if not text.strip():
            raise ValueError(f"Spreadsheet has no readable data: {path}")
        return text, {
            "format": path.suffix.lower()[1:],
            "sheet_names": workbook.sheet_names,
            "sheets": sheets,
        }


class PdfParser(DocumentParser):
    def parse(self, path: Path) -> tuple[str, dict[str, Any]]:
        """Extract text and page metadata from a PDF document."""
        reader = PdfReader(str(path))
        pages = [
            {"page": number, "text": page.extract_text() or ""}
            for number, page in enumerate(reader.pages, start=1)
        ]
        text = "\n\n".join(page["text"] for page in pages)
        if not text.strip():
            raise ValueError(
                f"PDF has no extractable text (it may be scanned): {path}"
            )
        return text, {"format": "pdf", "pages": pages}


PARSERS: dict[str, DocumentParser] = {
    ".txt": TextParser(),
    ".md": TextParser(),
    ".csv": CsvParser(),
    ".xls": SpreadsheetParser(),
    ".xlsx": SpreadsheetParser(),
    ".pdf": PdfParser(),
}


def sha256_file(path: Path) -> str:
    """Calculate a streaming SHA-256 hash for a source file."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_value(value: Any) -> Any:
    """Convert parser metadata into values safe to serialize as JSON."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def extract_text(path: Path) -> tuple[str, dict[str, Any]]:
    """Select the parser for a supported extension and extract its content."""
    parser = PARSERS.get(path.suffix.lower())
    if parser is None:
        raise ValueError(f"Unsupported file type: {path.suffix}")
    return parser.parse(path)


def cache_file(source: Path, input_root: Path, cache_root: Path) -> Path:
    """Write or reuse the hash-addressed JSON cache for one source file."""
    content_hash = sha256_file(source)
    output = cache_root / f"{content_hash}.json"
    if output.exists():
        try:
            cached = json.loads(output.read_text(encoding="utf-8"))
            if str(cached.get("text", "")).strip():
                return output
        except (OSError, json.JSONDecodeError):
            pass
        output.unlink()

    text, details = extract_text(source)
    if not text.strip():
        raise ValueError(f"No readable content extracted from: {source}")
    payload = {
        "source": str(source.relative_to(input_root)),
        "source_name": source.name,
        "sha256": content_hash,
        "text": text,
        "metadata": details,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


def clean_empty_cache(cache_root: Path) -> int:
    """Remove empty or invalid cached JSON files and return the count removed."""
    removed = 0
    if not cache_root.exists():
        return removed
    for path in cache_root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not str(payload.get("text", "")).strip():
                path.unlink()
                removed += 1
        except (OSError, json.JSONDecodeError):
            path.unlink()
            removed += 1
    return removed


def main() -> int:
    """Cache all supported input documents under the configured output path."""
    parser = argparse.ArgumentParser(
        description="Cache text extracted from supported documents."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/policy"),
        help="Directory containing source documents.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/cache"),
        help="Directory for hash-addressed JSON cache files.",
    )
    args = parser.parse_args()

    input_root = args.input.resolve()
    output_root = args.output.resolve()
    if not input_root.is_dir():
        raise NotADirectoryError(f"Input directory not found: {input_root}")

    removed = clean_empty_cache(output_root)
    if removed:
        print(f"Removed {removed} empty or invalid cache file(s).")

    files = sorted(
        path
        for path in input_root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not files:
        raise FileNotFoundError(
            f"No supported documents found in {input_root}"
        )

    for source in files:
        destination = cache_file(source, input_root, output_root)
        print(f"{source.relative_to(input_root)} -> {destination.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
