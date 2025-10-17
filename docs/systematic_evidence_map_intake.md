# Systematic Evidence Map Intake

This document summarizes how HAWC ingests data from systematic evidence maps so that upstream datasets can be transformed for interoperability.

## Overview

Systematic evidence map content is managed through the epidemiology v2 ("epiv2") module. REST viewsets exposed at `/epidemiology/api/...` support create, read, update, and delete operations for every major component of a map—study populations, chemicals, exposures, exposure levels, outcomes, adjustment factors, and quantitative data extractions. External systems can therefore push fully structured data into an assessment using these endpoints.

## Core Data Structures

When preparing a dataset for import, normalize it to the epiv2 model hierarchy:

- **Design (study population)** – References an existing HAWC study and captures descriptors such as design summary text, source population, age profile, sex, race, enrollment or follow-up years, geography, inclusion criteria, susceptibility notes, and comments.
- **Chemical** – Links a design to named chemicals and optionally to DSSTox identifiers for consistent substance mapping.
- **Exposure (measurement)** – Describes how exposure was measured, including measurement type(s), biomonitoring matrix or source, timing, route, method, and comments.
- **ExposureLevel** – Connects a design, chemical, and exposure measurement to quantitative statistics (central tendency, variance, percentiles, interval bounds, units) plus metadata such as sub-population, data location, and comments.
- **Outcome** – Associates a design with health systems, effects, detailed endpoints, and comments to define analyzable outcomes.
- **AdjustmentFactor** – Stores named covariate sets and descriptive text for models used in analyses.
- **DataExtraction** – Links an outcome, exposure level, and (optionally) adjustment factor to quantitative effect estimates, intervals, sample sizes, significance flags, transforms, confidence ratings, data locations, and interpretation comments.

Because each layer relies on identifiers from the previous layer, ensure the source data maintains these relationships before import.

## Controlled Vocabularies and Metadata

Many fields accept controlled choices (for example, study design, source, age categories, measurement routes, health systems, and variance types). These enumerations live in `hawc/apps/epiv2/constants.py`, pairing short codes with human-readable labels. Align upstream data to these choices during transformation so that payloads pass validation.

To automate vocabulary discovery, query the metadata endpoint (`/epidemiology/api/metadata/`) or call the bundled `EpiV2Client.metadata()` helper. Serializers use `FlexibleChoiceField` and `FlexibleChoiceArrayField`, which accept either stored codes or display labels, but using the published vocabulary avoids ambiguity and simplifies interoperability.

## API-Based Ingestion Workflow

The Python client bundled with HAWC demonstrates the expected payload shape for each endpoint. A typical ingestion sequence is:

1. **Create or update designs** by POSTing study population descriptors, including the existing HAWC study ID plus controlled fields such as study design, source, age profile, and sex.
2. **Attach chemicals** (optionally with DSSTox identifiers) to each design.
3. **Load exposures and exposure levels**, supplying measurement metadata, quantitative statistics, and links back to the appropriate design, chemical, and exposure records.
4. **Define outcomes and adjustment factors** tied to the same design, using recognized health-system codes and harmonized covariate descriptions.
5. **Publish data extractions** that bind outcomes, exposure levels, and adjustment sets with effect estimates, interval information, transforms, and interpretation metadata.

Each POST response returns the saved object JSON so that generated identifiers can be captured for downstream relationships.

## Validation and Integrity

The serializers enforce that related objects (chemicals, exposures, outcomes, etc.) belong to the same design via the `SameDesignSerializerMixin`. Ensure every referenced identifier was created under the same study population before posting linked records. DSSTox lookups and study references must also exist beforehand, so plan the import order accordingly.

## Example Spreadsheet

The repository includes [`docs/systematic_evidence_map_example.csv`](systematic_evidence_map_example.csv), which demonstrates how to stage a single row of intake-ready content. Each column matches the payload field used by the epiv2 REST endpoints and multi-valued cells are pipe-delimited (for example, `Adults|Pregnant women`). Replace the placeholder study ID and identifiers with records that exist in your assessment before posting the data.

Run the helper script to validate and normalize the CSV:

```bash
python scripts/verify_systematic_evidence_map_example.py
```

The script checks enumerated values against the epiv2 vocabularies, ensures numeric fields contain numbers, and emits an ordered set of request bodies showing how each row maps to the Design, Chemical, Exposure, ExposureLevel, Outcome, AdjustmentFactor, and DataExtraction endpoints.

## Verifying Interoperability

After importing, verify the dataset through export endpoints such as `/epidemiology/api/assessment/<id>/export/`, `/study-export/`, and `/tabular-export/`. The Python client's `data()` method returns a flat, Pandas-ready table of all quantitative extractions for an assessment. These exports help confirm that the structured evidence map is interoperable with HAWC's visualization and analysis tools.
