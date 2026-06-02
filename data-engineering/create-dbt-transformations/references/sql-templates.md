# SQL Templates

## Bronze: no SQL

Bronze is **not** a SQL layer. `dbt/models/bronze/` contains only `schema.yml`,
which declares raw tables as dbt sources. See
[schema-conventions.md](schema-conventions.md). Silver models read raw data
directly via `{{ source('bronze', '<raw_table_name>') }}`.

## Silver Model (reads raw via source)

```sql
SELECT
  <pk_column>,
  <business_columns>,
  <ingestion_timestamp_column>
FROM {{ source('bronze', '<raw_table_name>') }}
WHERE <filtering_conditions>
```

The raw table must be declared under `sources: - name: bronze` in
`dbt/models/bronze/schema.yml` first (see
[schema-conventions.md](schema-conventions.md)).

## Gold Model (reads silver via ref)

```sql
SELECT
  <pk_column>,
  <business_columns>,
  <ingestion_timestamp_column>
FROM {{ ref('<silver_model>') }}
WHERE <filtering_conditions>
```

## Bridge Model (JSON Array)

When unpacking a JSON array into a many-to-many bridge table, read from the
silver model that owns the array column:

```sql
SELECT DISTINCT
  d.id              AS <entity_a>_id,
  <entity_b>_id,
  d.<ingestion_timestamp_column>
FROM {{ ref('<silver_source_model>') }} d,
UNNEST(JSON_VALUE_ARRAY(d.<json_array_column>)) AS <entity_b>_id
WHERE d.<json_array_column> IS NOT NULL
```

Concrete example (`gold_deals_companies.sql`, unpacking the `companies` array
on `silver_hubspot_deals`):

```sql
SELECT DISTINCT
  d.id                      AS deal_id,
  company_id,
  d._airbyte_extracted_at
FROM {{ ref('silver_hubspot_deals') }} d,
UNNEST(JSON_VALUE_ARRAY(d.companies)) AS company_id
WHERE d.companies IS NOT NULL
```

If the silver model for the upstream entity does not exist yet, create it
first (see edge case: missing upstream model in `edge-cases.md`).

Notes:

1. `SELECT DISTINCT` — a single source row can produce duplicate combinations under some sync patterns.
2. `WHERE d.<json_array_column> IS NOT NULL` is required — `UNNEST(JSON_VALUE_ARRAY(NULL))` is unsafe.
3. Preserve the ingestion timestamp column from upstream for downstream freshness checks.
4. Composite PK: `(<entity_a>_id, <entity_b>_id)`.

## Bridge Model Naming

Convention: `<entity_a>_<entity_b>` (no `to_`, no `bridge_` prefix). Alphabetical order unless one entity clearly owns the relationship.

Examples: `gold_deals_companies`, `gold_deals_contacts`, `gold_companies_contacts`.

## SQL Content Rules

1. No `{{ config(materialized=...) }}` unless the user asks to override the layer default.
2. `{{ source('bronze', '<table>') }}` for raw tables — used **only** in silver models.
3. `{{ ref('<model>') }}` for references to other dbt models (gold reads silver this way).
4. Never write `.sql` files in `dbt/models/bronze/`.
5. Named CTEs for non-trivial logic, explicit column lists where practical.
6. Preserve the ingestion timestamp column from raw (e.g. `_airbyte_extracted_at` if Airbyte loaded it) when present.
