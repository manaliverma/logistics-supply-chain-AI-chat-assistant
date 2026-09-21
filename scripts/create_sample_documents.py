"""Create synthetic logistics documents for parser and RAG testing."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/input"


def create_pdf(path: Path) -> None:
    """Write a minimal text PDF used to exercise the PDF parser."""
    """Create a small text PDF without requiring an external PDF generator."""
    lines = [
        "Synthetic logistics learning document",
        "Emergency action: keep reefer cargo powered during a port delay.",
        "Escalate when temperature or customer promise limits are threatened.",
    ]
    content_lines = ["BT", "/F1 14 Tf", "72 720 Td"]
    for index, line in enumerate(lines):
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if index:
            content_lines.append("0 -24 Td")
        content_lines.append(f"({escaped}) Tj")
    content_lines.append("ET")
    content = "\n".join(content_lines).encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n"
        + content
        + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii"))
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(pdf)


def main() -> None:
    """Generate representative TXT, CSV, XLSX, and PDF input documents."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "warehouse_playbook.txt").write_text(
        "Synthetic logistics learning document.\n"
        "If a refrigerated shipment loses power, move it to validated cold storage "
        "and notify the Area Manager.\n"
        "If a receiving appointment is unavailable, confirm capacity before dispatch.",
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "shipment_id": "SYN-1001",
                "product_type": "chilled seafood",
                "weather": "heat_wave",
                "action": "move to powered cold storage",
            },
            {
                "shipment_id": "SYN-1002",
                "product_type": "consumer electronics",
                "weather": "clear",
                "action": "continue standard routing",
            },
        ]
    ).to_csv(OUTPUT / "shipment_events.csv", index=False)
    with pd.ExcelWriter(OUTPUT / "warehouse_capacity.xlsx") as writer:
        pd.DataFrame(
            [
                {"facility": "ONT8", "capacity_pct": 82, "status": "available"},
                {"facility": "SAN-BERNARDINO-OVERFLOW", "capacity_pct": 94, "status": "constrained"},
            ]
        ).to_excel(writer, sheet_name="Capacity", index=False)
        pd.DataFrame(
            [
                {"route": "Long Beach to Inland Empire", "road_status": "open"},
                {"route": "Flood zone alternate", "road_status": "monitor"},
            ]
        ).to_excel(writer, sheet_name="Routes", index=False)
    create_pdf(OUTPUT / "carrier_emergency_contacts.pdf")
    print(f"Created synthetic documents in {OUTPUT}")


if __name__ == "__main__":
    main()
