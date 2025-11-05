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


def _normalize(value: str) -> str:
    return value.strip().lower()


class MetadataResolver:
    """Resolve human-friendly labels in the CSV to concrete database IDs."""

    def __init__(self, metadata: dict[str, Any]):
        animal_group_meta = metadata.get("animal_group", {})
        dose_group_meta = metadata.get("dose_group", {})

        self.species_by_id = {
            int(item["id"]): item
            for item in animal_group_meta.get("species", [])
            if "id" in item and "name" in item
        }
        self.species_by_name = {
            _normalize(item["name"]): int(item["id"])
            for item in animal_group_meta.get("species", [])
            if "id" in item and "name" in item
        }

        self.strains_by_id = {
            int(item["id"]): item
            for item in animal_group_meta.get("strains", [])
            if "id" in item and "name" in item
        }
        self.strains_by_name = {}
        for item in animal_group_meta.get("strains", []):
            if "id" not in item or "name" not in item:
                continue
            key = _normalize(item["name"])
            self.strains_by_name.setdefault(key, []).append(item)

        self.dose_units_by_id = {
            int(item["id"]): item
            for item in dose_group_meta.get("dose_units", [])
            if "id" in item and "name" in item
        }
        self.dose_units_by_name = {
            _normalize(item["name"]): int(item["id"])
            for item in dose_group_meta.get("dose_units", [])
            if "id" in item and "name" in item
        }

    def resolve_species(self, species_id: int | None, species_name: str | None) -> int:
        if species_id is not None:
            if species_id in self.species_by_id:
                return species_id
            raise RuntimeError(
                f"Unknown species id {species_id}. Available ids: "
                + ", ".join(map(str, sorted(self.species_by_id)))
            )
        if species_name:
            key = _normalize(species_name)
            if key in self.species_by_name:
                return self.species_by_name[key]
            raise RuntimeError(
                f"Unknown species name {species_name!r}. Available names: "
                + ", ".join(sorted(item["name"] for item in self.species_by_id.values()))
            )
        raise RuntimeError("Species must be identified by ID or name.")

    def resolve_strain(
        self,
        strain_id: int | None,
        strain_name: str | None,
        *,
        species_id: int | None,
    ) -> int | None:
        if strain_id is not None:
            if strain_id in self.strains_by_id:
                return strain_id
            raise RuntimeError(
                f"Unknown strain id {strain_id}. Available ids: "
                + ", ".join(map(str, sorted(self.strains_by_id)))
            )
        if not strain_name:
            return None

        key = _normalize(strain_name)
        candidates = self.strains_by_name.get(key, [])
        if not candidates:
            raise RuntimeError(
                f"Unknown strain name {strain_name!r}. Available names: "
                + ", ".join(sorted(item["name"] for item in self.strains_by_id.values()))
            )
        if species_id is not None:
            species_matches = [c for c in candidates if c.get("species_id") == species_id]
            if len(species_matches) == 1:
                return int(species_matches[0]["id"])
            if len(species_matches) > 1:
                raise RuntimeError(
                    f"Strain name {strain_name!r} is ambiguous for species {species_id}."
                )
        if len(candidates) == 1:
            return int(candidates[0]["id"])
        raise RuntimeError(
            f"Strain name {strain_name!r} is ambiguous; specify strain id explicitly."
        )

    def resolve_dose_unit(self, unit_id: int | None, unit_name: str | None) -> int:
        if unit_id is not None:
            if unit_id in self.dose_units_by_id:
                return unit_id
            raise RuntimeError(
                f"Unknown dose unit id {unit_id}. Available ids: "
                + ", ".join(map(str, sorted(self.dose_units_by_id)))
            )
        if unit_name:
            key = _normalize(unit_name)
            if key in self.dose_units_by_name:
                return self.dose_units_by_name[key]
            raise RuntimeError(
                f"Unknown dose unit name {unit_name!r}. Available names: "
                + ", ".join(sorted(item["name"] for item in self.dose_units_by_id.values()))
            )
        raise RuntimeError("Dose units must be identified by ID or name.")

    def apply_animal_group(self, payload: dict[str, Any], lookup: dict[str, Any]) -> None:
        species_name = lookup.get("species_name")
        strain_name = lookup.get("strain_name")

        species_id = payload.get("species")
        strain_id = payload.get("strain")

        resolved_species_id = self.resolve_species(species_id, species_name)
        payload["species"] = resolved_species_id

        resolved_strain_id = self.resolve_strain(
            strain_id, strain_name, species_id=resolved_species_id
        )
        if resolved_strain_id is not None:
            payload["strain"] = resolved_strain_id
        elif "strain" in payload:
            payload.pop("strain", None)

    def apply_dose_units(
        self, dosing_regime: dict[str, Any], unit_infos: list[dict[str, Any]]
    ) -> None:
        doses = dosing_regime.get("doses") or []
        if not doses:
            return
        if not unit_infos:
            raise RuntimeError("Dose information is missing unit metadata from the CSV.")

        resolved_units = [
            self.resolve_dose_unit(info.get("id"), info.get("name")) for info in unit_infos
        ]

        unit_count = len(unit_infos)
        for index, dose in enumerate(doses):
            if "dose_units_id" in dose and dose["dose_units_id"] is not None:
                # already resolved
                continue
            unit_index = index % unit_count
            dose["dose_units_id"] = resolved_units[unit_index]

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


def _fetch_metadata(session: requests.Session, base_url: str) -> MetadataResolver:
    url = f"{base_url}/ani/api/metadata/"
    response = session.get(url, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Metadata lookup failed with status {response.status_code}: {response.text}"
        )
    data = response.json()
    return MetadataResolver(data)


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

    resolver = _fetch_metadata(session, base_url)

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
            lookups = record.get("lookups", {})
            resolver.apply_animal_group(
                animal_group_payload, lookups.get("animal_group", {})
            )
            dosing_regime = animal_group_payload.get("dosing_regime", {})
            resolver.apply_dose_units(
                dosing_regime, lookups.get("dosing_regime", {}).get("dose_units", [])
            )
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
