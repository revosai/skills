---
name: create-cubes
description: >
  Create first-class Cube.dev cube definitions from existing RevOS dbt gold models.
  Use when asked to: build a semantic layer, create cubes, generate Cube definitions from dbt,
  define cube files, or create a semantic model from gold models.
---

# Create Cube

## Skill Dependencies

This skill delegates dbt-related knowledge to `create-dbt-transformations`:
project layout, finding gold models, resolving dbt model names to BigQuery table references,
creating bridge models from JSON arrays, and dbt validation commands.

If `create-dbt-transformations` is not installed: discover gold models directly via
`find dbt/models/gold -name "*.sql"` and skip bridge model delegation.
Warn the user: "The `create-dbt-transformations` skill is not installed — bridge model creation and dbt validation are limited."

If BigQuery exploration is needed (listing tables, inspecting schemas, previewing rows),
load the `explore-lakehouse` skill on demand.

---

## Purpose

Expose existing dbt gold models as queryable Cube.dev semantic models without manually writing YAML boilerplate. Gold models may be tables or views.

Each cube is a **complete, standalone definition** stored in `cubes/`. There is no patching or merging — what is in the file is what gets deployed.

This skill does not build gold models. If a needed gold model is missing, hand off to `create-dbt-transformations`.

---

## Naming Convention

Strip the `gold_` prefix for cube names and file names. Keep `gold_` in `sql_table` (physical table).

The cube identifier is **`spec.name`** (the Cube.dev `definition.name`) — the name the compiler parses and that `${CUBE}` and joins reference. It must be a valid SQL/JS identifier: snake_case (letters, digits, underscores), **never hyphens** — a hyphen in `spec.name` surfaces as a generic 500 from the compiler with no field-level message. `spec.name` is required.

`metadata.name` is the **local IaC slug** — the `cubes/<name>.yml` filename and the address other files refer to. It is **never sent to the API**, so it is *not* bound by the SQL-identifier rule: the loader accepts `^[a-z][a-z0-9_-]*$`, i.e. hyphens (the normal RevOS slug convention) or underscores. For cubes it's convenient to set `metadata.name` equal to the snake_case `spec.name` so the filename mirrors the `${…}` join token, but a hyphenated slug is equally valid.

```text
gold SQL file:     dbt/models/gold/gold_hubspot_companies.sql
BigQuery table:    gold_hubspot_companies
cube file:         cubes/hubspot_companies.yml
spec.name:         hubspot_companies     (the cube identifier — required)
metadata.name:     hubspot_companies     (local slug — same value)
join reference:    ${hubspot_companies}
sql_table:         "`<dataset>.gold_hubspot_companies`"
```

Same rule for bridge cubes: `gold_deals_companies` -> cube name `deals_companies`, file `cubes/deals_companies.yml`.

## Cube `sql_table` Reference

Reference the physical warehouse table directly. Cube does not understand Jinja — never use `dbt ref()`.

Use the literal `dataset` value resolved in Phase 2. Wrap in BigQuery backticks:

```yaml
sql_table: "`<dataset>.gold_hubspot_companies`"
```

Apply the same fully qualified format in `refresh_key.sql`.

---

## User Checkpoints

### Checkpoint 1: Gold Model Selection

After discovering gold models, show available models and ask which should participate. Do not proceed until the user selects. Exception: if the user named one specific model, treat it as selected.

### Checkpoint 2a: Connector Model Approval

When selected models are not directly connected, search remaining gold models for connectors. Present the connector path and ask approval before adding.

### Checkpoint 2b: Bridge / Support Model Approval

When a many-to-many relationship is detected and no suitable bridge model exists, ask whether to create one. If approved, delegate to `create-dbt-transformations`.

### Checkpoint 3: Relationship Confirmation

Present validated relationships with join directions, cardinality, and match rates. Ask the user to confirm before generating cube files. Do not present unvalidated joins as confirmed — mark them as `validation pending`.

### Checkpoint 4: Measures Confirmation

Generate default `count` measure, suggest additional measures, and ask the user to confirm or define custom measures.

---

# Workflow

Follow these phases in order. Do not skip ahead.

---

## Phase 1: Discover Gold Models and Select Scope

1. Discover gold models via `find dbt/models/gold -name "*.sql"`.
2. If none exist, stop and tell the user to create gold models first via `create-dbt-transformations`.
3. Inspect 1-2 existing cube files in `cubes/` to detect conventions (`extends:`, `public:`, `refresh_key` style). Apply detected conventions to new cubes. Always use flat single-cube YAML (never `cubes:` or `views:` root).
4. If the user named a specific model, find it. If not found, stop.
5. Otherwise list all discovered gold models and ask which should participate (Checkpoint 1).
6. Keep the full discovered list available for connector search in Phase 3.

---

## Phase 2: Analyze Selected Model Schemas and Keys

### Resolve Environment Variables First

Before any SQL or YAML generation, resolve `$REVOS_BQ_DATASET` to a literal:

```bash
echo "DATASET=$REVOS_BQ_DATASET"
```

If empty, stop and ask the user to set it. Use this literal everywhere downstream.

### Schema Discovery

For each selected gold model, inspect columns and types. Use `explore-lakehouse` if needed.

Check whether `_airbyte_extracted_at` exists (needed for `refresh_key` and as the only Airbyte dimension to expose).

### Key Detection

Detect primary keys, secondary keys, foreign keys, and JSON/array keys.
See [references/key-patterns.md](references/key-patterns.md) for common patterns and detection rules.

Validate primary key uniqueness with SQL. See [references/validation-queries.md](references/validation-queries.md), section 1.

Output a schema summary for each model (format in key-patterns.md).

---

## Phase 3: Detect Candidate Relationships

Build a candidate relationship graph. These are candidates only — they must be validated in Phase 4.

### Single-Model Case

If only one model was selected and it has no JSON/array relationship columns, skip to Phase 6. If it has JSON/array columns, check for bridge/junction needs.

### Relationship Types and Direction

Use Cube types: `one_to_one`, `one_to_many`, `many_to_one`, `many_to_many`. Direction is always from the perspective of the current cube.

### Cardinality Rules

1. Source FK can repeat, target key unique -> `many_to_one` / reverse `one_to_many`.
2. Both sides unique -> `one_to_one`.
3. Both can repeat or through bridge -> `many_to_many`.
4. If unclear, validate before proposing.

### Direct Join Detection

Look for FK-to-PK matches, secondary key matches, existing bridge models, and JSON/array relationship fields.

### Connector Model Search

When selected models are disconnected:

1. Search all discovered gold models for connector paths (length 2, then 3).
2. Inspect non-selected models for relationship discovery only — this does not add them to the scope.
3. Present connector path and ask user approval (Checkpoint 2a).
4. If approved, add to scope and run full schema discovery. If rejected, document disconnected models.

### Bridge / Junction Detection

If an existing bridge model is found in `dbt/models/gold/`:

1. Inspect its schema and verify it has the expected key columns.
2. If it fits, use it. If it doesn't fit cleanly, present the mismatch and offer options (use as-is, create new, or abort).

If no bridge exists and user approves creating one (Checkpoint 2b), delegate to `create-dbt-transformations`. Once built, generate a bridge cube with `public: false`.

---

## Phase 4: Validate Candidate Relationships

Verify with SQL against BigQuery that candidate joins work and direction is correct.

For each candidate relationship, validate:

- Key uniqueness
- FK match rates (LEFT JOIN + match percentage)
- Reverse direction aggregation counts
- Bridge edge integrity (both sides)
- JSON array extraction match rates
- Type compatibility via INFORMATION_SCHEMA

See [references/validation-queries.md](references/validation-queries.md) for all SQL templates.

Validate both directions of every candidate relationship where possible.

Do not present unvalidated joins as confirmed. If validation cannot run, mark as `validation pending`.

---

## Phase 5: Present Validated Relationships

Present all validated relationships to the user: selected models, approved connectors, keys, joins with cardinality, match rates, and validation evidence.

Ask user to confirm or modify (Checkpoint 3). Do not generate files until confirmed.

If a relationship could not be validated but user proceeds, tag it with `# UNVALIDATED: <reason>` in the generated YAML.

---

## Phase 6: Generate Dimensions

Expose all business columns from each selected gold model as Cube dimensions.

Key rules:

1. Include PKs with `primary_key: true`. For composite PKs, use a synthetic `CONCAT` dimension — see [references/cube-examples.md](references/cube-examples.md), Composite Primary Key section.
2. Include secondary keys, names, statuses, timestamps, and numeric attributes as dimensions.
3. From `_airbyte_*` columns, include only `_airbyte_extracted_at` as dimension `airbyte_extracted_at` (reference as `${CUBE}._airbyte_extracted_at`). Exclude all other `_airbyte_*` columns.
4. Do not remove business columns just because they don't look immediately useful.
5. JSON/array columns used for relationships should be represented through bridge models.
6. If a model has >50 business columns, ask user before generating.

See [references/cube-examples.md](references/cube-examples.md) for type mapping and dimension examples.

---

## Phase 7: Suggest and Confirm Measures

1. Always include a default `count` measure.
2. Suggest useful additional measures based on column names. See [references/cube-examples.md](references/cube-examples.md), Measure Suggestions section.
3. `count_distinct` on FK columns: define inside the cube that owns the FK, not the parent cube. Joins produce fan-out that distorts distinct counts.
4. Ask user to confirm suggested measures or define custom ones (Checkpoint 4).
5. If custom measure definition is unclear, ask for clarification.

---

## Phase 8: Generate Cube Files

Create Cube.dev YAML files in `cubes/`. Follow the existing style detected in Phase 1.

Key rules:

1. **One cube per file, IaC format.** Each cube file is a single document — `apiVersion` / `kind: Cube` / `metadata` / `spec` — with the cube definition flat under `spec` (and `spec.name` set to the identifier). Never wrap with `cubes:` or `views:` at the root.
2. File name = cube identifier (`metadata.name` = `spec.name`, no `gold_` prefix) + `.yml`.
3. `sql_table` uses fully qualified BigQuery reference with `gold_` prefix.
4. Every confirmed relationship gets joins in both directions.
5. Bridge/junction cubes use `public: false`.
6. Every cube **must** include a SQL-based `refresh_key`. Use `SELECT MAX(<timestamp_col>)` with columns in this priority: `_airbyte_extracted_at` (present on all Airbyte sources), `updated_at`/`modified_at` (CDC streams), `created_at` (insert-only facts). Only use `every: <interval>` as absolute last resort when **no timestamp column exists in the table** — add a YAML comment explaining why (e.g. `# no timestamp column available`).
7. `refresh_key.sql` references the same table as `sql_table`.
8. Tag unvalidated joins with `# UNVALIDATED: <reason>`.
9. For cubes derived from data ingested by a Connection (i.e. the gold model traces back to bronze tables produced by `revos apply` on a `Connection`), set `meta.abConnectionId: <connection-id>`. This groups cubes by their originating connection in the UI. Resolve the connection id with `revos connections list --json` — match by `spec.prefix` against the bronze table prefix the gold model reads from. Bridge / junction cubes built on top of connection-sourced models inherit the same `abConnectionId`. Cubes derived from purely local data (e.g. hand-written silver/gold models with no upstream connection) omit `abConnectionId`.
10. For cubes whose rows have a natural human-readable label (companies, contacts, deals, tickets, users, projects, …), set `meta.nameDimension: <short-dimension-name>`. The value is the **short** dimension key (no `${CUBE}.` prefix and no cube-name prefix) — e.g. `properties_name`, `displayName`, `dealname`. The frontend uses this to pick the column shown as the entity's name when the cube is added as a table (see `useCubeFromMeta` in the frontend). Pick the dimension that a user would recognize as "the name of this thing"; if no such single column exists (pure join / bridge cubes, fact tables, event logs), omit `nameDimension`. The dimension must exist on this cube under `dimensions:`.
11. Set `meta.icon` only when needed — see the decision rule in **"Choose an icon for each cube"** below.
12. `meta` is closed: only `abConnectionId`, `nameDimension`, and `icon` are allowed. Omit the whole `meta` block if none apply.

See [references/cube-examples.md](references/cube-examples.md) for canonical standard cube, bridge cube, join direction examples, and refresh key variants.

---

## Choose an icon for each cube

Bridge/junction cubes (`public: false`) always omit `meta.icon`.

For all other cubes, decide whether `meta.icon` is needed:

1. **Cube has `meta.abConnectionId`** — check whether the source behind this connection has a branded icon.
   The `abConnectionId` value is the RevOS connection ID (same one you resolved in rule 9).
   Run `revos connections get <abConnectionId> --json | jq '.spec.source.id'` to get the source id,
   then `revos sources get <source-id> --json | jq '.icon'`.
   - **`icon` is a non-empty string** → the UI will automatically show the integration logo. **Skip `meta.icon`.**
   - **`icon` is null, empty, or the field is absent** → set `meta.icon` using the catalog below.

2. **Cube has no `meta.abConnectionId`** → always set `meta.icon` using the catalog below.

### Catalog keys

| Key         | Meaning                               | Typical cube names                             |
| ----------- | ------------------------------------- | ---------------------------------------------- |
| `users`     | End-users, customers, account holders | `*users*`, `*customers*`, `*accounts*`         |
| `orders`    | Purchase orders, transactions         | `*orders*`, `*purchases*`, `*transactions*`    |
| `events`    | Behavioral events, activity logs      | `*events*`, `*activity*`, `*logs*`             |
| `products`  | Products, SKUs, items                 | `*products*`, `*items*`, `*skus*`              |
| `sessions`  | Web/app sessions                      | `*sessions*`, `*visits*`                       |
| `revenue`   | Revenue, payments, invoices           | `*revenue*`, `*payments*`, `*invoices*`        |
| `companies` | B2B companies, organizations          | `*companies*`, `*organizations*`, `*accounts*` |
| `contacts`  | Individual people / CRM contacts      | `*contacts*`, `*people*`, `*persons*`          |
| `deals`     | Sales deals, opportunities            | `*deals*`, `*opportunities*`                   |
| `tickets`   | Support tickets, issues               | `*tickets*`, `*issues*`, `*cases*`             |
| `campaigns` | Marketing campaigns                   | `*campaigns*`, `*ads*`                         |
| `emails`    | Email messages                        | `*emails*`, `*messages*`                       |
| `leads`     | Sales leads                           | `*leads*`                                      |
| `tasks`     | Tasks, to-dos                         | `*tasks*`, `*todos*`                           |

### Three accepted forms

```yaml
meta:
  icon: "users"                                # catalog key (preferred)
  # — or —
  icon: "url:https://cdn.example.com/icon.svg" # explicit external URL
  # — or —
  icon: "data:image/svg+xml;base64,…"          # inline SVG data URI
```

Use a catalog key whenever possible. Fall back to `url:` or `data:` only for
custom brand icons the catalog does not cover. Malformed values cause
`revos apply` to reject the file with a clear error.

---

## Phase 9: Validate Generated Files

1. If `create-dbt-transformations` was invoked (bridge model), it already validated dbt models. Otherwise run `dbt parse`.
2. Verify physical tables exist in BigQuery: `bq show <dataset>.<table_name>`. If missing, document as pending.
3. Verify generated cube files match conventions: flat YAML, correct naming, correct `sql_table`, all dimensions present, `refresh_key` included, joins in both directions.

---

## Final Response Format

```text
Created cube definitions.

Selected gold models:
- dbt/models/gold/<gold_model_1>.sql

Approved connector models:
- dbt/models/gold/<connector_model>.sql

Bridge/support models created (via create-dbt-transformations):
- dbt/models/gold/<bridge_model>.sql

Cube files:
- cubes/<entity_1>.yml         (cube name: <entity_1>)
- cubes/<bridge_entity>.yml    (cube name: <bridge_entity>, public: false)

Validated relationships:
- <entity_a>.<key> -> <entity_b>.<key> (<relationship_type>)

Measures:
- count
- <approved_measure_1>

Validation:
- dbt: <passed / pending / not run>
- physical tables: <passed / pending>
- join validation: <passed / pending>
- semantic validation: <passed / pending>

Unvalidated joins (tagged with # UNVALIDATED):
- <cube>.<join_target>: <reason>

Assumptions:
- <assumption>

Pending items:
- <pending_item>

Next step:
  revos apply
```

If validation is incomplete, say exactly what remains pending.
