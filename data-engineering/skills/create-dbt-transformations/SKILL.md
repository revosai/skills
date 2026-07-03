---
name: create-dbt-transformations
description: Create new dbt transformations (silver/gold models) in the RevOS dbt project. Use when asked to create a dbt model, build a transformation, add a new layer model, declare a raw source, or register a new raw table. Bronze is source-declarations only — no SQL files. Covers dbt project conventions, sources, materialization, schema.yml, and validation commands.
---

# Create dbt Transformations

Use this skill to generate SQL models, declare sources, update `schema.yml`, and validate models with `dbt run` / `dbt test`.

For BigQuery exploration (listing datasets, inspecting raw tables, previewing rows, null rates), load the `explore-lakehouse` skill. If that skill is not installed, fall back to:

```bash
bq show --format=prettyjson $REVOS_BQ_DATASET.<table>
```

Warn the user: "The `explore-lakehouse` skill is not installed — using `bq show` as a fallback. Install it for richer schema exploration."

---

# Part 1: Knowledge Base

## Layer Conventions

- **gold** — business-ready models exposed for reporting or downstream consumption.
- **silver** — cleaned, deduplicated, type-conformed intermediates. Lowest SQL layer; reads raw data via `{{ source('bronze', '<table>') }}`.
- **bronze** — **not a SQL layer**. Holds only `dbt/models/bronze/schema.yml`, which declares raw tables as dbt sources. No `.sql` files belong under `dbt/models/bronze/`.

When layer is not obvious from context, ask (see Checkpoint 1).

## Sources (bronze layer)

Raw tables loaded into the warehouse by your ingestion pipeline are not dbt models. Declare them as dbt sources so silver models can reference them with `{{ source() }}`.

Sources are declared in `dbt/models/bronze/schema.yml` under a `sources:` block using `schema` (the BigQuery dataset):

```yaml
sources:
  - name: bronze
    schema: "{{ env_var('REVOS_BQ_DATASET') }}"
    tables:
      - name: hubspot_contacts
```

Reference in silver SQL:

```sql
-- dbt/models/silver/silver_hubspot_contacts.sql
SELECT * FROM {{ source('bronze', 'hubspot_contacts') }}
```

`{{ source('bronze', 'hubspot_contacts') }}` resolves to `${REVOS_BQ_DATASET}.hubspot_contacts` — the same dataset where raw tables live — so silver has direct access without a bronze SQL view in between.

See [schema-conventions.md](references/schema-conventions.md) for the full declaration pattern.

## Materialization

Inherited globally from `dbt_project.yml` — do not add `{{ config(materialized=...) }}` unless the user explicitly asks to override.

## `schema.yml` Convention

One shared file per layer at `dbt/models/<layer>/schema.yml`. Append new models; never create per-model YAML files. See [schema-conventions.md](references/schema-conventions.md) for full examples and composite-PK / dbt-utils patterns.

## Resolving Physical BigQuery Tables

Materialized table lives at: `$REVOS_BQ_DATASET.<model_name>`

**When to use `{{ ref() }}` vs. `{{ source() }}`:**

| Context                                            | Use                                 |
| -------------------------------------------------- | ----------------------------------- |
| dbt SQL → other dbt model                          | `{{ ref('<model>') }}`              |
| dbt SQL → raw table (silver reading from `bronze`) | `{{ source('bronze', '<table>') }}` |

Silver is the lowest SQL layer — `{{ source('bronze', ...) }}` is used in silver only. Gold reads from silver via `{{ ref() }}`. There are no SQL files in `dbt/models/bronze/`.

Always declare raw tables as sources before referencing them. Do not use bare fully qualified names — that bypasses dbt's dependency graph and source freshness tracking.

## Standard dbt Commands

```bash
dbt parse                               # validate syntax (no warehouse)
dbt compile --select <model>            # resolve refs, produce compiled SQL
dbt run --select <model>                # execute against warehouse
dbt test --select <model>               # run tests
dbt build --select <model>              # run + test
dbt build --select path:models/<layer>  # entire layer
```

---

# Part 2: Workflow — Create a New dbt Transformation

## Execution Order

For each transformation (one at a time — do not batch):

1. Determine the target layer — **silver** or **gold** only (Checkpoint 1 if unclear). Refuse bronze SQL models (see Checkpoint 4).
2. Determine the model name.
3. Check if that model already exists (Checkpoint 2 if yes).
4. Gather source data and transformation logic. For bridge models, apply the bridge template ([sql-templates.md](references/sql-templates.md)).
5. If the model reads raw data, ensure each raw table is declared under the `bronze` source in `dbt/models/bronze/schema.yml`; add it if missing.
6. Generate `dbt/models/<silver|gold>/<model_name>.sql`. **Never** generate `.sql` files under `dbt/models/bronze/`.
7. Detect the primary key (Checkpoint 3 if ambiguous).
8. Add model entry to `dbt/models/<layer>/schema.yml` with PK and FK tests. See [schema-conventions.md](references/schema-conventions.md).
9. Run `dbt run --select <model_name>` and report result.
10. Run `dbt test --select <model_name>` and report result.
11. Summarize (see Final Response Format).

For multiple transformations in one request: repeat steps 1–11 per model in order.

---

## Mandatory User Checkpoints

### Checkpoint 1: Layer Selection

Ask if the layer is not obvious:

```text
Which layer should this transformation live in?

- gold: business-ready, exposed for reporting or downstream consumption
- silver: cleaned/intermediate, reads raw via `{{ source('bronze', ...) }}`

(bronze is not a SQL layer — it only holds `schema.yml` source declarations.)
```

Layer is obvious when the user explicitly names it.

### Checkpoint 2: Existing Model Conflict

If `dbt/models/<layer>/<model_name>.sql` exists:

```text
A model named <model_name> already exists at dbt/models/<layer>/<model_name>.sql.

Options:
- overwrite: replace with new transformation
- edit:      modify existing (describe the change)
- rename:    use a different name
```

If found in a different layer, mention it too.

### Checkpoint 3: Ambiguous Primary Key

If PK detection produces no clear result:

```text
I could not unambiguously detect the primary key. Candidates:
- <candidate_1>
- <candidate_2>

Which column(s) should be the primary key?
```

### Checkpoint 4: Bronze SQL Model Refused

If the user explicitly asks to create a bronze SQL model:

```text
Bronze is not a SQL layer in this project — it only holds source
declarations in `dbt/models/bronze/schema.yml`. Silver reads raw data
directly via `{{ source('bronze', '<raw_table>') }}`.

Would you like to create this as a silver model instead?
```

Do not generate any file under `dbt/models/bronze/` other than
`schema.yml`.

---

## Primary Key Detection

Apply in order; stop at first clear result:

1. `ROW_NUMBER() OVER (PARTITION BY <cols>) = 1` → partition columns are PK.
2. `SELECT DISTINCT` over a small column set → all selected columns form composite PK.
3. `GROUP BY <cols>` at outermost level → grouping columns are PK.
4. Single column named `id` → PK.
5. Single column named `<entity>_id` matching the model name stem → PK.
6. Bridge naming `<entity_a>_<entity_b>` → `(<entity_a>_id, <entity_b>_id)` composite PK.

If none produce a clear answer → Checkpoint 3.

## Foreign Key Detection

A column is a FK candidate if it matches `<entity>_id` where `<entity>` ≠ model's own entity, is not part of the PK, and is not nullable by design. Add `not_null` test only (no `relationships` tests by default).

## Timestamp Column Propagation (Gold Models)

Every gold model **must** propagate at least one timestamp column so downstream cubes can use SQL-based `refresh_key` (see `create-cubes` skill). Priority:

1. An ingestion-time column on the raw table (e.g. Airbyte writes `_airbyte_extracted_at`) — propagate when present.
2. `updated_at` / `modified_at` — CDC-friendly streams.
3. `created_at` — insert-only fact tables.

If the upstream source has none of these, document it in a SQL comment: `-- no timestamp column available from source`.

## SQL File Generation

See [sql-templates.md](references/sql-templates.md) for:

- Standard silver model template (reads raw via `{{ source('bronze', ...) }}`)
- Standard gold model template (reads silver via `{{ ref() }}`)
- Bridge model (JSON array) template with concrete example
- Bridge model naming convention and SQL content rules

## schema.yml Update

See [schema-conventions.md](references/schema-conventions.md) for full examples including sources declaration, composite PK, and dbt-utils patterns.

## Edge Cases

See [edge-cases.md](references/edge-cases.md) for: missing SQL details, missing upstream model, undeclared source, run/test failure handling.

---

## Final Response Format

```text
Created dbt transformation: <model_name>

Layer:           <silver | gold>
File:            dbt/models/<layer>/<model_name>.sql
Materialization: <inherited: table | overridden: <type>>
Primary key:     <pk_column>  (or composite: <col_1>, <col_2>)
Foreign keys:    <fk_1>, <fk_2>  (or "none detected")
schema.yml:      dbt/models/<layer>/schema.yml (entry added)

Tests:
- not_null on <pk>: added
- unique on <pk>: added | skipped: dbt-utils unavailable
- not_null on <fk>: added

Validation:
- dbt run:  passed | failed
- dbt test: passed | failed

Physical table after run:
`<resolved_dataset>.<model_name>`
```
