#!/usr/bin/env python3
"""Validate and push animal bioassay evidence map records into a local HAWC API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.verify_animal_evidence_map_example import (  # noqa: E402  pylint: disable=wrong-import-position
    DEFAULT_CSV,
    validate_spreadsheet,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv",
        nargs="?",
        default=str(DEFAULT_CSV),
        help="Path to the intake CSV (defaults to docs/animal_evidence_map_example.csv)",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Root URL for the HAWC deployment (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("HAWC_API_TOKEN"),
        help="API token for authentication (defaults to HAWC_API_TOKEN environment variable)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and display normalized payloads without sending API requests",
    )
    return parser


def _require_token(token: str | None) -> str:
    if not token:
        raise SystemExit(
            "An API token is required. Pass --token or set the HAWC_API_TOKEN environment variable."
        )
    return token


def _api_post(session: requests.Session, url: str, payload: dict[str, Any], context: str) -> dict:
    response = session.post(url, json=payload, timeout=30)
    if response.status_code >= 400:
        try:
            detail = response.json()
        except json.JSONDecodeError:
            detail = response.text
        raise RuntimeError(f"{context} failed with status {response.status_code}: {detail}")
    return response.json()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    csv_path = Path(args.csv).resolve()
    if not csv_path.exists():
        print(f"CSV file not found: {csv_path}", file=sys.stderr)
        return 1

    records, errors = validate_spreadsheet(csv_path)
    result = {"records": records, "rows_validated": len(records)}
    if errors:
        result["validation_errors"] = errors
        print(json.dumps(result, indent=2))
        print(
            f"Validation failed for {len(errors)} row(s); see JSON output for details.",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print(json.dumps(result, indent=2))
        return 0

    token = _require_token(args.token)
    base_url = args.base_url.rstrip("/")

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Token {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    )

    experiment_url = f"{base_url}/ani/api/experiment/"
    animal_group_url = f"{base_url}/ani/api/animal-group/"
    endpoint_url = f"{base_url}/ani/api/endpoint/"

    created_records: list[dict[str, Any]] = []

    try:
        for index, record in enumerate(records, start=1):
            print(f"Processing row {index}...")

            experiment_payload = deepcopy(record["experiment"])
            experiment = _api_post(
                session, experiment_url, experiment_payload, "Experiment creation"
            )

            animal_group_payload = deepcopy(record["animal_group"])
            if animal_group_payload.get("experiment_id") == "<experiment_id>":
                animal_group_payload["experiment_id"] = experiment["id"]
            animal_group = _api_post(
                session, animal_group_url, animal_group_payload, "Animal group creation"
            )

            endpoint_payload = deepcopy(record["endpoint"])
            if endpoint_payload.get("animal_group_id") == "<animal_group_id>":
                endpoint_payload["animal_group_id"] = animal_group["id"]
            endpoint = _api_post(session, endpoint_url, endpoint_payload, "Endpoint creation")

            created_records.append(
                {
                    "experiment": experiment["id"],
                    "animal_group": animal_group["id"],
                    "endpoint": endpoint["id"],
                }
            )
            print(
                " - Created experiment {experiment_id}, animal group {animal_group_id}, endpoint {endpoint_id}".format(
                    experiment_id=experiment["id"],
                    animal_group_id=animal_group["id"],
                    endpoint_id=endpoint["id"],
                )
            )
    except RuntimeError as exc:
        print(f"Error while pushing data: {exc}", file=sys.stderr)
        return 1

    print("Successfully pushed all records:")
    print(json.dumps(created_records, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
