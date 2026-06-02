# BigQuery PK / FK Conventions

Conventions and patterns for primary keys, foreign keys, and type handling in
BigQuery-backed Cube.dev cube definitions.

---

## Primary key rules

### Single-column PK

Expose with `primary_key: true`:

```yaml
dimensions:
  id:
    sql: "${CUBE}.id"
    type: string
    primary_key: true
```

### Composite PK (no natural single key)

Use a synthetic `CONCAT` or string concatenation dimension:

```yaml
dimensions:
  id:
    sql: "${CUBE}.deal_id || '_' || ${CUBE}.contact_id"
    type: string
    primary_key: true
```

Use `||` (SQL string concat) not `CONCAT()` — both work in BigQuery but `||` is
more portable. Always cast non-string parts:

```yaml
sql: "${CUBE}.issue_id || '_' || CAST(${CUBE}.sprint_id AS STRING)"
```

### No natural PK

When no unique column exists, use `ROW_NUMBER()` in the cube `sql:` view or
document the absence clearly. Warn the user — Cube.js fan-out protection
depends on a correct PK.

---

## FK type casting

BigQuery enforces strict type matching in JOINs. Common mismatches:

| Situation                   | Fix                                                   |
| --------------------------- | ----------------------------------------------------- |
| `id` is STRING, FK is INT64 | `CAST(fk_col AS STRING) = id`                         |
| `id` is INT64, FK is STRING | `SAFE_CAST(id AS INT64) = fk_col`                     |
| Both sides uncertain        | `SAFE_CAST(... AS STRING) = SAFE_CAST(... AS STRING)` |
| JSON object storing ID      | `JSON_VALUE(col, '$.id')`                             |

Use `SAFE_CAST` (not `CAST`) when the FK can contain non-numeric values —
`SAFE_CAST` returns NULL on failure instead of throwing.

---

## JSON column patterns

### Extracting a scalar value

```sql
-- From a top-level field
JSON_VALUE(col, '$.fieldName')

-- From a nested object
JSON_VALUE(col, '$.parent.child.id')
```

### Extracting an array of scalars (for UNNEST)

```sql
-- Array of plain strings/numbers (association IDs):
UNNEST(JSON_VALUE_ARRAY(col)) AS element

-- Array of JSON objects (pipeline stages):
UNNEST(JSON_QUERY_ARRAY(col)) AS obj
-- then: JSON_VALUE(obj, '$.fieldName')
```

Rule of thumb: `JSON_VALUE_ARRAY` for scalar arrays, `JSON_QUERY_ARRAY` for object arrays.

---

## sql_table vs sql

| Approach                                       | When to use                            |
| ---------------------------------------------- | -------------------------------------- |
| `sql_table: "\`<dataset>.<table>\`"`           | Raw table, no transformation needed    |
| `sql: "SELECT ... FROM \`<dataset>.<table>\`"` | Derived view (UNNEST, JOIN, aggregate) |

Always wrap BigQuery table names in backticks inside YAML. In YAML double-quoted
strings you must escape backticks: `"\`dataset.table\`"`. In block scalars (`>`or`|`) no escaping needed:

```yaml
# Double-quoted — must escape backticks:
sql_table: "`my_project.my_dataset.my_table`"

# Inside sql block scalar — no escaping:
sql: >
  SELECT id FROM `my_project.my_dataset.my_table`
```

---

## refresh_key patterns

Priority order for the timestamp column:

1. `_airbyte_extracted_at` — present on all Airbyte-synced tables
2. `updated_at` / `modified_at` / `lastModifiedDate` — CDC streams
3. `created_at` — insert-only facts
4. `every: 1 hour` — only when **no timestamp column exists**, with a YAML comment

```yaml
# Pattern 1 (preferred):
refresh_key:
  sql: "SELECT MAX(_airbyte_extracted_at) FROM `<dataset>.<table>`"

# Pattern 4 (last resort):
refresh_key:
  every: 1 hour  # no timestamp column available in this table
```

For derived cubes (`sql:` based, not `sql_table:`), the refresh key should
reference the **underlying source table**, not the derived view:

```yaml
# Bridge cube derived from deals:
refresh_key:
  sql: "SELECT MAX(_airbyte_extracted_at) FROM `<dataset>.<prefix>deals`"
```

---

## Common dimension types in Cube.dev

| BigQuery type             | Cube type | Notes                                      |
| ------------------------- | --------- | ------------------------------------------ |
| STRING                    | `string`  | default for most IDs, names                |
| INT64, FLOAT64, NUMERIC   | `number`  | use for metrics                            |
| BOOL                      | `boolean` |                                            |
| TIMESTAMP, DATETIME, DATE | `time`    | enables time drill-downs                   |
| JSON                      | `string`  | expose extracted subfields individually    |
| ARRAY                     | —         | use UNNEST in a bridge cube or `sql:` view |

---

## Naming conventions

| Item                    | Convention                                |
| ----------------------- | ----------------------------------------- |
| Cube name               | `gold_` prefix stripped; snake_case       |
| File name               | same as cube name + `.yml`                |
| Dimension/measure names | snake_case                                |
| Computed dimensions     | descriptive name, not `col_json_value`    |
| Bridge cubes            | `<entity_a>_to_<entity_b>`                |
| Table aliases           | `<entity>_<role>` (e.g. `users_assignee`) |

---

## BigQuery-specific SQL tips

```sql
-- Safe division (avoid divide-by-zero)
SAFE_DIVIDE(numerator, denominator)

-- Null-safe equality
${CUBE}.col IS NOT DISTINCT FROM other_col

-- Date truncation for time series
DATE_TRUNC(${CUBE}.created_at, MONTH)

-- String aggregation
STRING_AGG(${CUBE}.name, ', ')
```
