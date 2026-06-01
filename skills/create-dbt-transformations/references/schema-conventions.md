# schema.yml Conventions

## Contents

- [Declaring Sources (bronze layer)](#declaring-sources-bronze-layer)
- [Standard Model Entry](#standard-model-entry)
- [Composite Primary Keys (Bridge Models)](#composite-primary-keys-bridge-models)
- [Description Guidelines](#description-guidelines)
- [Foreign Key Tests](#foreign-key-tests)

---

Each SQL layer (silver, gold) has one shared `schema.yml` at
`dbt/models/<layer>/schema.yml`. Append new models; do not create per-model
files.

The bronze directory is **not** a SQL layer — its `schema.yml` contains only
source declarations, no `models:` block.

If a layer's `schema.yml` does not exist, create it with:

```yaml
version: 2

models:
```

## Declaring Sources (bronze layer)

`dbt/models/bronze/schema.yml` is the only file in `dbt/models/bronze/`. It
declares raw tables as dbt sources so that silver models can reference them
with `{{ source('bronze', '<table>') }}`.

`schema` maps to the BigQuery dataset (`REVOS_BQ_DATASET`):

```yaml
version: 2

sources:
  - name: bronze
    schema: "{{ env_var('REVOS_BQ_DATASET') }}"
    tables:
      - name: hubspot_contacts
      - name: hubspot_deals
      - name: stripe_charges
```

The corresponding silver model entry lives in `dbt/models/silver/schema.yml`:

```yaml
version: 2

models:
  - name: silver_hubspot_contacts
    ...
```

Rules:

- Use `bronze` as the source name for all raw tables.
- Each raw table referenced in silver SQL needs a corresponding entry under `tables:`.
- If the source block already exists, append to the `tables:` list only.
- Do **not** add a `models:` block to `dbt/models/bronze/schema.yml` — bronze contains source declarations only.

## Standard Model Entry

```yaml
- name: <model_name>
  description: |
    <1–2 sentences: what entity/relationship, what source, any non-obvious logic>
  columns:
    - name: <pk_column>
      description: "Primary key."
      tests:
        - not_null
        - unique

    - name: <fk_column>
      description: "Foreign key to <target_entity>."
      tests:
        - not_null
```

## Composite Primary Keys (Bridge Models)

If `dbt-utils` is available:

```yaml
- name: <model_name>
  description: |
    <description>
  tests:
    - dbt_utils.unique_combination_of_columns:
        combination_of_columns:
          - <pk_col_1>
          - <pk_col_2>
  columns:
    - name: <pk_col_1>
      description: "Composite key part."
      tests:
        - not_null
    - name: <pk_col_2>
      description: "Composite key part."
      tests:
        - not_null
```

If `dbt-utils` is not available, omit `unique_combination_of_columns` and note it in the description:

```yaml
description: |
  <description>
  Note: composite uniqueness on (<pk_col_1>, <pk_col_2>) is not enforced —
  dbt-utils is not installed in this project.
```

Check availability:

```bash
grep -A2 "packages:" dbt/packages.yml 2>/dev/null | grep dbt-utils || echo "dbt-utils not found"
```

## Description Guidelines

Answer in 1–2 sentences:

1. What entity or relationship this model represents.
2. What source(s) it reads from.
3. Any non-obvious filtering or transformation.

Example:

```yaml
description: |
  Bridge table linking HubSpot deals to companies, unpacked from the
  `companies` JSON array on `hubspot_deals`. Excludes deals with no
  associated companies.
```

## Foreign Key Tests

Add `not_null` only. Do not add `relationships` tests by default — they require knowing the target model and column, which needs explicit user input.
