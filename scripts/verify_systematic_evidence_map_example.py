#!/usr/bin/env python3
"""Validate and normalize the example systematic evidence map intake spreadsheet."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
DEFAULT_CSV = REPO_ROOT / "docs" / "systematic_evidence_map_example.csv"
from hawc.apps.epiv2 import constants  # noqa: E402  pylint: disable=wrong-import-position


def _choice_labels(choices: Iterable[tuple]) -> set[str]:
    """Return the union of stored values and display labels for a TextChoices/IntegerChoices."""

    normalized: set[str] = set()
    for value, label in choices:
        normalized.add(str(value))
        normalized.add(str(label))
    return normalized


CHOICE_FIELDS = {
    "design.study_design": _choice_labels(constants.StudyDesign.choices),
    "design.source": _choice_labels(constants.Source.choices),
    "design.sex": _choice_labels(constants.Sex.choices),
    "outcome.system": _choice_labels(constants.HealthOutcomeSystem.choices),
    "exposure_level.variance_type": _choice_labels(constants.VarianceType.choices),
    "exposure_level.ci_type": _choice_labels(constants.ConfidenceIntervalType.choices),
    "data_extraction.ci_type": _choice_labels(constants.ConfidenceIntervalType.choices),
    "data_extraction.variance_type": _choice_labels(constants.VarianceType.choices),
    "data_extraction.significant": _choice_labels(constants.Significant.choices),
    "data_extraction.adverse_direction": _choice_labels(constants.AdverseDirection.choices),
    "data_extraction.effect_estimate_type": _choice_labels(constants.EffectEstimateType.choices),
    "data_extraction.exposure_transform": _choice_labels(constants.DataTransforms.choices),
    "exposure.exposure_route": _choice_labels(constants.ExposureRoute.choices),
    "exposure.biomonitoring_matrix": _choice_labels(constants.BiomonitoringMatrix.choices) | {""},
    "exposure.biomonitoring_source": _choice_labels(constants.BiomonitoringSource.choices) | {""},
}

ARRAY_FIELDS = {
    "design.age_profile": _choice_labels(constants.AgeProfile.choices),
    "exposure.measurement_type": None,  # free text, but still parsed as a list
}

COUNTRY_FIELD = "design.countries"


def _as_list(value: object) -> list[str]:
    """Split pipe-delimited cell values into a list of trimmed strings."""

    if pd.isna(value):  # type: ignore[arg-type]
        return []
    return [item.strip() for item in str(value).split("|") if item.strip()]


def _expect_numeric(raw: object, field: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric; received {raw!r}") from exc


def _expect_int(raw: object, field: str) -> int:
    value = _expect_numeric(raw, field)
    if int(value) != value:
        raise ValueError(f"{field} must be an integer; received {raw!r}")
    return int(value)


def _validate_row(row: dict, index: int) -> dict:
    errors: list[str] = []

    for field, allowed in CHOICE_FIELDS.items():
        value = row.get(field)
        if pd.isna(value) or value == "":
            continue
        if str(value) not in allowed:
            errors.append(f"{field} contains {value!r}, which is not a recognized option")

    for field, allowed in ARRAY_FIELDS.items():
        values = _as_list(row.get(field))
        if allowed is None:
            row[field] = values
            continue
        for value in values:
            if value not in allowed:
                errors.append(f"{field} contains {value!r}, which is not a recognized option")
        row[field] = values

    countries = _as_list(row.get(COUNTRY_FIELD))
    for value in countries:
        if len(value) != 2 or not value.isalpha():
            errors.append(f"{COUNTRY_FIELD} contains {value!r}, expected ISO country codes")
    row[COUNTRY_FIELD] = [value.upper() for value in countries]

    try:
        row["design.study_id"] = _expect_int(row["design.study_id"], "design.study_id")
        row["design.participant_n"] = _expect_int(row["design.participant_n"], "design.participant_n")
        row["exposure_level.mean"] = _expect_numeric(row["exposure_level.mean"], "exposure_level.mean")
        if row.get("exposure_level.variance") not in ("", None) and not pd.isna(row.get("exposure_level.variance")):
            row["exposure_level.variance"] = _expect_numeric(
                row["exposure_level.variance"], "exposure_level.variance"
            )
        row["data_extraction.effect_estimate"] = _expect_numeric(
            row["data_extraction.effect_estimate"], "data_extraction.effect_estimate"
        )
        if row.get("data_extraction.ci_lcl") not in ("", None) and not pd.isna(
            row.get("data_extraction.ci_lcl")
        ):
            row["data_extraction.ci_lcl"] = _expect_numeric(
                row["data_extraction.ci_lcl"], "data_extraction.ci_lcl"
            )
        if row.get("data_extraction.ci_ucl") not in ("", None) and not pd.isna(
            row.get("data_extraction.ci_ucl")
        ):
            row["data_extraction.ci_ucl"] = _expect_numeric(
                row["data_extraction.ci_ucl"], "data_extraction.ci_ucl"
            )
        if row.get("data_extraction.variance") not in ("", None) and not pd.isna(
            row.get("data_extraction.variance")
        ):
            row["data_extraction.variance"] = _expect_numeric(
                row["data_extraction.variance"], "data_extraction.variance"
            )
        if row.get("data_extraction.n") not in ("", None) and not pd.isna(row.get("data_extraction.n")):
            row["data_extraction.n"] = _expect_int(row["data_extraction.n"], "data_extraction.n")
        if row.get("data_extraction.exposure_rank") not in ("", None) and not pd.isna(
            row.get("data_extraction.exposure_rank")
        ):
            row["data_extraction.exposure_rank"] = _expect_int(
                row["data_extraction.exposure_rank"], "data_extraction.exposure_rank"
            )
    except ValueError as exc:
        errors.append(str(exc))

    if errors:
        raise ValueError(f"Row {index + 1} failed validation:\n - " + "\n - ".join(errors))

    # Build a normalized payload skeleton demonstrating API bodies.
    design_payload = {
        "study_id": row["design.study_id"],
        "study_design": row.get("design.study_design"),
        "source": row.get("design.source"),
        "sex": row.get("design.sex"),
        "age_profile": row.get("design.age_profile", []),
        "countries": row.get(COUNTRY_FIELD, []),
        "summary": row.get("design.summary"),
        "study_name": row.get("design.study_name"),
        "age_description": row.get("design.age_description"),
        "race": row.get("design.race"),
        "participant_n": row.get("design.participant_n"),
        "years_enrolled": row.get("design.years_enrolled"),
        "years_followup": row.get("design.years_followup"),
        "criteria": row.get("design.criteria"),
        "susceptibility": row.get("design.susceptibility"),
        "comments": row.get("design.comments"),
    }

    chemical_payload = {
        "design": "<design_id>",
        "name": row.get("chemical.name"),
        "dsstox_id": row.get("chemical.dsstox_id") or None,
    }

    exposure_payload = {
        "design": "<design_id>",
        "name": row.get("exposure.name"),
        "measurement_type": row.get("exposure.measurement_type", []),
        "biomonitoring_matrix": row.get("exposure.biomonitoring_matrix") or "",
        "biomonitoring_source": row.get("exposure.biomonitoring_source") or "",
        "measurement_timing": row.get("exposure.measurement_timing") or "",
        "exposure_route": row.get("exposure.exposure_route"),
        "measurement_method": row.get("exposure.measurement_method") or "",
        "comments": row.get("exposure.comments") or "",
    }

    exposure_level_payload = {
        "design": "<design_id>",
        "chemical_id": "<chemical_id>",
        "exposure_measurement_id": "<exposure_id>",
        "name": row.get("exposure_level.name"),
        "sub_population": row.get("exposure_level.sub_population") or "",
        "mean": row.get("exposure_level.mean"),
        "variance_type": row.get("exposure_level.variance_type"),
        "variance": row.get("exposure_level.variance"),
        "units": row.get("exposure_level.units"),
        "ci_type": row.get("exposure_level.ci_type"),
        "ci_lcl": row.get("exposure_level.ci_lcl"),
        "ci_ucl": row.get("exposure_level.ci_ucl"),
        "negligible_exposure": row.get("exposure_level.negligible_exposure") or "",
        "data_location": row.get("exposure_level.data_location") or "",
        "comments": row.get("exposure_level.comments") or "",
    }

    outcome_payload = {
        "design": "<design_id>",
        "system": row.get("outcome.system"),
        "effect": row.get("outcome.effect"),
        "endpoint": row.get("outcome.endpoint"),
        "comments": row.get("outcome.comments") or "",
    }

    adjustment_payload = {
        "design": "<design_id>",
        "name": row.get("adjustment.name"),
        "description": row.get("adjustment.description") or "",
    }

    data_extraction_payload = {
        "design": "<design_id>",
        "outcome_id": "<outcome_id>",
        "exposure_level_id": "<exposure_level_id>",
        "factors_id": "<adjustment_factor_id>",
        "sub_population": row.get("data_extraction.sub_population") or "",
        "outcome_measurement_timing": row.get("data_extraction.outcome_measurement_timing") or "",
        "effect_estimate_type": row.get("data_extraction.effect_estimate_type"),
        "effect_estimate": row.get("data_extraction.effect_estimate"),
        "ci_lcl": row.get("data_extraction.ci_lcl"),
        "ci_ucl": row.get("data_extraction.ci_ucl"),
        "ci_type": row.get("data_extraction.ci_type"),
        "units": row.get("data_extraction.units") or "",
        "variance_type": row.get("data_extraction.variance_type"),
        "variance": row.get("data_extraction.variance"),
        "n": row.get("data_extraction.n"),
        "significant": row.get("data_extraction.significant"),
        "group": row.get("data_extraction.group") or "",
        "exposure_rank": row.get("data_extraction.exposure_rank"),
        "exposure_transform": row.get("data_extraction.exposure_transform") or "",
        "outcome_transform": row.get("data_extraction.outcome_transform") or "",
        "confidence": row.get("data_extraction.confidence") or "",
        "data_location": row.get("data_extraction.data_location") or "",
        "effect_description": row.get("data_extraction.effect_description") or "",
        "statistical_method": row.get("data_extraction.statistical_method") or "",
        "adverse_direction": row.get("data_extraction.adverse_direction"),
        "comments": row.get("data_extraction.comments") or "",
    }

    return {
        "design": design_payload,
        "chemical": chemical_payload,
        "exposure": exposure_payload,
        "exposure_level": exposure_level_payload,
        "outcome": outcome_payload,
        "adjustment_factor": adjustment_payload,
        "data_extraction": data_extraction_payload,
    }


def validate_spreadsheet(path: Path) -> list[dict]:
    """Validate and normalize the provided spreadsheet."""

    df = pd.read_csv(path, dtype=str).fillna("")
    normalized_records: list[dict] = []
    for index, row in df.iterrows():
        record = _validate_row(row.to_dict(), index)
        normalized_records.append(record)
    return normalized_records


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if argv:
        csv_path = Path(argv[0]).resolve()
    else:
        csv_path = DEFAULT_CSV

    if not csv_path.exists():
        print(f"Spreadsheet not found: {csv_path}", file=sys.stderr)
        return 1

    records = validate_spreadsheet(csv_path)
    print(json.dumps({"records": records, "rows_validated": len(records)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
