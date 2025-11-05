#!/usr/bin/env python3
"""Validate and normalize animal bioassay evidence map intake spreadsheets."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_CSV = REPO_ROOT / "docs" / "animal_evidence_map_example.csv"

from hawc.apps.animal import constants  # noqa: E402  pylint: disable=wrong-import-position


def _choice_tuples(choices: Iterable[tuple]) -> list[tuple[Any, str]]:
    """Return an explicit list of (stored value, display label) tuples."""

    return [(value, label) for value, label in choices]


def _coerce_choice(value: object, *, field: str, choices: Sequence[tuple[Any, str]]):
    if value in ("", None) or (isinstance(value, float) and pd.isna(value)):
        return None
    normalized = str(value).strip().lower()
    for stored, label in choices:
        if normalized == str(stored).strip().lower() or normalized == str(label).strip().lower():
            return stored
    allowed = ", ".join(sorted({str(v) for v, _ in choices} | {str(l) for _, l in choices}))
    raise ValueError(f"{field} contains {value!r}, which is not a recognized option ({allowed})")


def _as_bool(raw: object, *, allow_none: bool = False) -> bool | None:
    if raw in ("", None) or (isinstance(raw, float) and pd.isna(raw)):
        return None if allow_none else False

    value = str(raw).strip().lower()
    truthy = {"true", "1", "yes", "y"}
    falsy = {"false", "0", "no", "n"}
    if allow_none:
        unknown = {"unknown", "na", "n/a", "none", "null"}
        if value in unknown:
            return None
    if value in truthy:
        return True
    if value in falsy:
        return False
    raise ValueError(f"Could not interpret boolean value: {raw!r}")


def _as_float(raw: object, field: str) -> float | None:
    if raw in ("", None) or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric; received {raw!r}") from exc


def _as_int(raw: object, field: str) -> int:
    if raw in ("", None) or (isinstance(raw, float) and pd.isna(raw)):
        raise ValueError(f"{field} is required and must be an integer")
    value = _as_float(raw, field)
    if value is None or int(value) != value:
        raise ValueError(f"{field} must be an integer; received {raw!r}")
    return int(value)


CHOICE_FIELDS = {
    "experiment.type": _choice_tuples(constants.ExperimentType.choices),
    "experiment.purity_qualifier": _choice_tuples(constants.PurityQualifier.choices),
    "animal_group.sex": _choice_tuples(constants.Sex.choices),
    "animal_group.generation": _choice_tuples(constants.Generation.choices),
    "dosing_regime.route_of_exposure": _choice_tuples(constants.RouteExposure.choices),
    "dosing_regime.negative_control": _choice_tuples(constants.NegativeControl.choices),
    "endpoint.litter_effects": _choice_tuples(constants.LitterEffect.choices),
    "endpoint.observation_time_units": _choice_tuples(constants.ObservationTimeUnits.choices),
    "endpoint.expected_adversity_direction": _choice_tuples(constants.AdverseDirection.choices),
    "endpoint.data_type": _choice_tuples(constants.DataType.choices),
    "endpoint.variance_type": _choice_tuples(constants.VarianceType.choices),
    "endpoint.monotonicity": _choice_tuples(constants.Monotonicity.choices),
    "endpoint.trend_result": _choice_tuples(constants.TrendResult.choices),
}

GROUP_CHOICE_FIELDS = {
    "treatment_effect": _choice_tuples(constants.TreatmentEffect.choices),
}

BOOLEAN_FIELDS = {
    "experiment.has_multiple_generations",
    "experiment.purity_available",
    "endpoint.data_reported",
    "endpoint.data_extracted",
    "endpoint.values_estimated",
    "dosing_regime.positive_control",
}


def _clean_payload(data: dict) -> dict:
    return {key: value for key, value in data.items() if value is not None}


def _parse_doses(raw: object) -> tuple[list[dict[str, Any]], int]:
    if raw in ("", None) or (isinstance(raw, float) and pd.isna(raw)):
        raise ValueError("dosing_regime.doses is required and must be JSON encoded")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("dosing_regime.doses must be valid JSON") from exc

    if not isinstance(parsed, list) or not parsed:
        raise ValueError("dosing_regime.doses must be a non-empty list")

    dose_lists: list[list[float]] = []
    dose_units_ids: list[int] = []
    for index, entry in enumerate(parsed):
        if not isinstance(entry, dict):
            raise ValueError(f"dosing_regime.doses[{index}] must be an object")
        if "dose_units_id" not in entry:
            raise ValueError(f"dosing_regime.doses[{index}] missing dose_units_id")
        dose_units_ids.append(_as_int(entry["dose_units_id"], "dose_units_id"))
        doses = entry.get("doses")
        if not isinstance(doses, list) or not doses:
            raise ValueError(
                f"dosing_regime.doses[{index}].doses must be a non-empty list of numbers"
            )
        normalized: list[float] = []
        for dose_index, value in enumerate(doses):
            dose_value = _as_float(value, f"dosing_regime.doses[{index}].doses[{dose_index}]")
            if dose_value is None:
                raise ValueError(
                    f"dosing_regime.doses[{index}].doses[{dose_index}] must be numeric"
                )
            normalized.append(dose_value)
        dose_lists.append(normalized)

    counts = {len(dose_list) for dose_list in dose_lists}
    if len(counts) != 1:
        raise ValueError("All dose lists must contain the same number of entries")

    num_groups = counts.pop()
    doses_payload: list[dict[str, Any]] = []
    for dose_group_id in range(num_groups):
        for unit_index, unit_id in enumerate(dose_units_ids):
            doses_payload.append(
                {
                    "dose_group_id": dose_group_id,
                    "dose_units_id": unit_id,
                    "dose": dose_lists[unit_index][dose_group_id],
                }
            )

    return doses_payload, num_groups


def _parse_groups(raw: object, *, num_dose_groups: int) -> list[dict[str, Any]]:
    if raw in ("", None) or (isinstance(raw, float) and pd.isna(raw)):
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("endpoint.groups must be valid JSON") from exc

    if not isinstance(parsed, list):
        raise ValueError("endpoint.groups must be a list")
    if len(parsed) != num_dose_groups:
        raise ValueError(
            f"endpoint.groups must contain {num_dose_groups} entries to match dose groups"
        )

    allowed = {str(option) for option in range(num_dose_groups)}
    groups: list[dict[str, Any]] = []
    observed_ids: set[int] = set()
    for index, entry in enumerate(parsed):
        if not isinstance(entry, dict):
            raise ValueError(f"endpoint.groups[{index}] must be an object")
        if "dose_group_id" not in entry:
            raise ValueError(f"endpoint.groups[{index}] missing dose_group_id")
        dose_group_id = _as_int(entry["dose_group_id"], "dose_group_id")
        if not 0 <= dose_group_id < num_dose_groups:
            raise ValueError(
                f"endpoint.groups[{index}].dose_group_id must be in {allowed}; received {dose_group_id}"
            )
        if dose_group_id in observed_ids:
            raise ValueError(
                f"endpoint.groups contains duplicate dose_group_id {dose_group_id}"
            )
        observed_ids.add(dose_group_id)

        payload: dict[str, Any] = {"dose_group_id": dose_group_id}
        for key in ("n", "incidence"):
            if key in entry and entry[key] not in ("", None):
                payload[key] = _as_int(entry[key], f"groups[{index}].{key}")
        for key in ("response", "variance", "lower_ci", "upper_ci", "significance_level", "response_low", "response_high"):
            if key in entry and entry[key] not in ("", None):
                value = _as_float(entry[key], f"groups[{index}].{key}")
                if value is not None:
                    payload[key] = value

        if "significant" in entry and entry["significant"] not in ("", None):
            payload["significant"] = _as_bool(entry["significant"])

        treatment_effect = entry.get("treatment_effect")
        if treatment_effect not in ("", None):
            payload["treatment_effect"] = _coerce_choice(
                treatment_effect,
                field=f"groups[{index}].treatment_effect",
                choices=GROUP_CHOICE_FIELDS["treatment_effect"],
            )

        groups.append(payload)

    expected = set(range(num_dose_groups))
    if observed_ids != expected:
        missing = expected - observed_ids
        raise ValueError(
            "endpoint.groups is missing dose_group_id entries for " + ", ".join(map(str, sorted(missing)))
        )
    return groups


def _normalize_noel(value: object, field: str, *, num_dose_groups: int) -> int:
    if value in ("", None) or (isinstance(value, float) and pd.isna(value)):
        return -999
    parsed = _as_int(value, field)
    if parsed != -999 and not 0 <= parsed < num_dose_groups:
        raise ValueError(f"{field} must be -999 or between 0 and {num_dose_groups - 1}")
    return parsed


def _validate_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    errors: list[str] = []

    # validate controlled vocabularies
    for field, choices in CHOICE_FIELDS.items():
        try:
            row[field] = _coerce_choice(row.get(field), field=field, choices=choices)
        except ValueError as exc:
            errors.append(str(exc))

    # boolean coercion
    for field in BOOLEAN_FIELDS:
        try:
            row[field] = _as_bool(row.get(field), allow_none=True)
        except ValueError as exc:
            errors.append(str(exc))

    try:
        study_id = _as_int(row.get("experiment.study_id"), "experiment.study_id")
        species_id = _as_int(row.get("animal_group.species_id"), "animal_group.species_id")
        strain_id = _as_int(row.get("animal_group.strain_id"), "animal_group.strain_id")
    except ValueError as exc:
        errors.append(str(exc))
        study_id = species_id = strain_id = None

    float_fields = {
        "experiment.purity": "experiment.purity",
        "dosing_regime.duration_exposure": "dosing_regime.duration_exposure",
        "dosing_regime.duration_observation": "dosing_regime.duration_observation",
        "endpoint.observation_time": "endpoint.observation_time",
        "endpoint.confidence_interval": "endpoint.confidence_interval",
        "endpoint.trend_value": "endpoint.trend_value",
    }
    numeric_values: dict[str, float | None] = {}
    for key, label in float_fields.items():
        try:
            numeric_values[key] = _as_float(row.get(key), label)
        except ValueError as exc:
            errors.append(str(exc))

    # parse doses
    try:
        doses, num_dose_groups = _parse_doses(row.get("dosing_regime.doses"))
    except ValueError as exc:
        errors.append(str(exc))
        doses = []
        num_dose_groups = 0

    # parse endpoint groups
    try:
        groups = _parse_groups(row.get("endpoint.groups"), num_dose_groups=num_dose_groups)
    except ValueError as exc:
        errors.append(str(exc))
        groups = []

    term_fields = [
        "endpoint.system_term_id",
        "endpoint.organ_term_id",
        "endpoint.effect_term_id",
        "endpoint.effect_subtype_term_id",
        "endpoint.name_term_id",
    ]
    term_values: dict[str, int] = {}
    for field in term_fields:
        raw = row.get(field)
        if raw in ("", None) or (isinstance(raw, float) and pd.isna(raw)):
            continue
        try:
            term_values[field] = _as_int(raw, field)
        except ValueError as exc:
            errors.append(str(exc))

    for field in ("endpoint.NOEL", "endpoint.LOEL", "endpoint.FEL"):
        try:
            row[field] = _normalize_noel(row.get(field), field, num_dose_groups=num_dose_groups)
        except ValueError as exc:
            errors.append(str(exc))

    # purity validation
    purity_available = row.get("experiment.purity_available")
    purity = numeric_values.get("experiment.purity")
    qualifier = row.get("experiment.purity_qualifier") or ""
    if purity_available:
        if purity is None:
            errors.append("experiment.purity must be provided when purity is available")
        if qualifier == "":
            errors.append(
                "experiment.purity_qualifier must be provided when purity is available"
            )
    elif purity_available is False:
        if purity not in (None, ""):
            errors.append("experiment.purity must be blank when purity is not available")
        if qualifier not in ("", None):
            errors.append(
                "experiment.purity_qualifier must be blank when purity is not available"
            )
    # when purity is blank ensure numeric None
    if purity_available is False:
        numeric_values["experiment.purity"] = None

    # observation time units default
    if row.get("endpoint.observation_time_units") in ("", None):
        row["endpoint.observation_time_units"] = constants.ObservationTimeUnits.NR

    if errors:
        raise ValueError(f"Row {index + 1} failed validation:\n - " + "\n - ".join(errors))

    experiment_payload = _clean_payload(
        {
            "study_id": study_id,
            "name": row.get("experiment.name") or "",
            "type": row.get("experiment.type"),
            "has_multiple_generations": row.get("experiment.has_multiple_generations"),
            "chemical": row.get("experiment.chemical") or "",
            "cas": row.get("experiment.cas") or "",
            "dtxsid": row.get("experiment.dtxsid") or None,
            "chemical_source": row.get("experiment.chemical_source") or "",
            "purity_available": row.get("experiment.purity_available"),
            "purity_qualifier": row.get("experiment.purity_qualifier") or "",
            "purity": numeric_values.get("experiment.purity"),
            "vehicle": row.get("experiment.vehicle") or "",
            "guideline_compliance": row.get("experiment.guideline_compliance") or "",
            "description": row.get("experiment.description") or "",
        }
    )

    dosing_regime_payload = _clean_payload(
        {
            "route_of_exposure": row.get("dosing_regime.route_of_exposure"),
            "duration_exposure": numeric_values.get("dosing_regime.duration_exposure"),
            "duration_exposure_text": row.get("dosing_regime.duration_exposure_text") or "",
            "duration_observation": numeric_values.get("dosing_regime.duration_observation"),
            "positive_control": row.get("dosing_regime.positive_control"),
            "negative_control": row.get("dosing_regime.negative_control"),
            "description": row.get("dosing_regime.description") or "",
            "doses": doses,
        }
    )

    animal_group_payload = _clean_payload(
        {
            "experiment_id": "<experiment_id>",
            "name": row.get("animal_group.name") or "",
            "species": species_id,
            "strain": strain_id,
            "sex": row.get("animal_group.sex"),
            "animal_source": row.get("animal_group.animal_source") or "",
            "lifestage_exposed": row.get("animal_group.lifestage_exposed") or "",
            "lifestage_assessed": row.get("animal_group.lifestage_assessed") or "",
            "generation": row.get("animal_group.generation") or "",
            "comments": row.get("animal_group.comments") or "",
            "diet": row.get("animal_group.diet") or "",
            "dosing_regime": dosing_regime_payload,
        }
    )

    endpoint_payload = _clean_payload(
        {
            "animal_group_id": "<animal_group_id>",
            "name": row.get("endpoint.name") or "",
            "system": row.get("endpoint.system") or "",
            "system_term": term_values.get("endpoint.system_term_id"),
            "organ": row.get("endpoint.organ") or "",
            "organ_term": term_values.get("endpoint.organ_term_id"),
            "effect": row.get("endpoint.effect") or "",
            "effect_term": term_values.get("endpoint.effect_term_id"),
            "effect_subtype": row.get("endpoint.effect_subtype") or "",
            "effect_subtype_term": term_values.get("endpoint.effect_subtype_term_id"),
            "litter_effects": row.get("endpoint.litter_effects"),
            "litter_effect_notes": row.get("endpoint.litter_effect_notes") or "",
            "observation_time": numeric_values.get("endpoint.observation_time"),
            "observation_time_units": row.get("endpoint.observation_time_units"),
            "observation_time_text": row.get("endpoint.observation_time_text") or "",
            "data_location": row.get("endpoint.data_location") or "",
            "expected_adversity_direction": row.get("endpoint.expected_adversity_direction"),
            "response_units": row.get("endpoint.response_units") or "",
            "data_type": row.get("endpoint.data_type"),
            "variance_type": row.get("endpoint.variance_type"),
            "confidence_interval": numeric_values.get("endpoint.confidence_interval"),
            "NOEL": row.get("endpoint.NOEL", -999),
            "LOEL": row.get("endpoint.LOEL", -999),
            "FEL": row.get("endpoint.FEL", -999),
            "data_reported": row.get("endpoint.data_reported", False),
            "data_extracted": row.get("endpoint.data_extracted", False),
            "values_estimated": row.get("endpoint.values_estimated", False),
            "monotonicity": row.get("endpoint.monotonicity"),
            "statistical_test": row.get("endpoint.statistical_test") or "",
            "trend_value": numeric_values.get("endpoint.trend_value"),
            "trend_result": row.get("endpoint.trend_result"),
            "diagnostic": row.get("endpoint.diagnostic") or "",
            "power_notes": row.get("endpoint.power_notes") or "",
            "results_notes": row.get("endpoint.results_notes") or "",
            "endpoint_notes": row.get("endpoint.endpoint_notes") or "",
            "groups": groups,
            "name_term": term_values.get("endpoint.name_term_id"),
        }
    )

    if not endpoint_payload.get("name") and not endpoint_payload.get("name_term"):
        raise ValueError(
            f"Row {index + 1} failed validation:\n - endpoint.name or endpoint.name_term_id is required"
        )

    return {
        "experiment": experiment_payload,
        "animal_group": animal_group_payload,
        "endpoint": endpoint_payload,
        "num_dose_groups": num_dose_groups,
    }


def validate_spreadsheet(path: Path) -> tuple[list[dict], list[str]]:
    """Validate and normalize the provided spreadsheet."""

    df = pd.read_csv(path, dtype=str).fillna("")
    normalized_records: list[dict] = []
    errors: list[str] = []
    for index, row in df.iterrows():
        try:
            record = _validate_row(row.to_dict(), index)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            normalized_records.append(record)
    return normalized_records, errors


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if argv:
        csv_path = Path(argv[0]).resolve()
    else:
        csv_path = DEFAULT_CSV

    if not csv_path.exists():
        print(f"Spreadsheet not found: {csv_path}", file=sys.stderr)
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

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
