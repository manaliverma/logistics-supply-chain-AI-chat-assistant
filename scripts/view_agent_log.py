"""Inspect the local governed agent audit log."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent_tools import get_audit_events


def main() -> None:
    """Print recent audit events or a request-specific execution timeline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-id", help="Filter to one request trace.")
    parser.add_argument("--event-type", help="Filter to one event type.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a human timeline.",
    )
    args = parser.parse_args()
    events = get_audit_events.invoke(
        {
            "request_id": args.request_id,
            "event_type": args.event_type,
            "limit": args.limit,
        }
    )
    if args.json:
        print(json.dumps(events, indent=2))
        return
    if not events:
        print("No audit events found.")
        return
    for event in reversed(events):
        print(
            f"{event['created_at']} | {event['event_type']} | "
            f"{event['event_id']} | request={event['request_id'] or '-'}"
        )
        if event["payload"]:
            print(f"  {json.dumps(event['payload'], sort_keys=True)}")


if __name__ == "__main__":
    main()
