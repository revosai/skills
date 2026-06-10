# Cube Examples

## Table of Contents

- [Standard Cube](#standard-cube)
- [Bridge / Junction Cube](#bridge--junction-cube)
- [Composite Primary Key](#composite-primary-key)
- [Join Direction Examples](#join-direction-examples)
- [Refresh Key Variants](#refresh-key-variants)
- [Type Mapping](#type-mapping)
- [Measure Suggestions](#measure-suggestions)
- [Common Mistakes](#common-mistakes)

---

## Standard Cube

```yaml
apiVersion: revos/v1
kind: Cube
metadata:
  name: hubspot_companies
spec:
  name: hubspot_companies
  sql_table: "`<dataset>.gold_hubspot_companies`"

  meta:
    abConnectionId: conn_01HZX7K9P6QABCD
    nameDimension: properties_name
    icon: companies

  joins:
    companies_deals:
      sql: "${CUBE}.id = ${companies_deals}.company_id"
      relationship: one_to_many

  measures:
    count:
      type: count

    total_deal_value:
      sql: "${CUBE}.properties_hs_total_deal_value"
      type: sum

  dimensions:
    id:
      sql: "${CUBE}.id"
      type: string
      primary_key: true

    properties_name:
      sql: "${CUBE}.properties_name"
      type: string

    airbyte_extracted_at:
      sql: "${CUBE}._airbyte_extracted_at"
      type: time

  refresh_key:
    sql: "SELECT MAX(_airbyte_extracted_at) FROM `<dataset>.gold_hubspot_companies`"
```

Notes:

1. `spec.name` is the cube identifier (the Cube.dev `definition.name`) referenced by `${CUBE}` and joins; it is required and must be snake_case (no hyphens). `metadata.name` is the local IaC slug — the filename and address — and is never sent to the API, so hyphens or underscores are both valid there. Setting it equal to the snake_case `spec.name` (no `gold_` prefix) is the convenient default so the filename mirrors the `${…}` join token.
2. The cube identifier is `hubspot_companies` (no `gold_` prefix); `spec.sql_table` references `gold_hubspot_companies` (with `gold_` prefix), in backticks.
3. The join references `${companies_deals}` — the cube name of a bridge cube defined in `cubes/companies_deals.yml`.
4. Only `_airbyte_extracted_at` is exposed from Airbyte metadata, as `airbyte_extracted_at`.
5. `spec.refresh_key.sql` uses the same fully qualified table name as `spec.sql_table`.
6. `spec.meta.abConnectionId` ties this cube back to the Connection that ingests its raw data — get the id from `revos connections list --json`. Omit it for cubes built on purely local models with no upstream connection.
7. `spec.meta.nameDimension` is the **short** name of the dimension that represents this entity's human-readable label — here `properties_name`, referenced as `${CUBE}.properties_name`. The dimension must exist under `spec.dimensions`. The frontend reads `meta.nameDimension` to pick the "name" column when this cube is added as a table. Omit `nameDimension` for cubes that don't have a single natural label (bridges, fact tables, event logs). `meta` currently allows only `abConnectionId` and `nameDimension`; omit the whole `meta` block if neither applies.

---

## Bridge / Junction Cube

```yaml
apiVersion: revos/v1
kind: Cube
metadata:
  name: companies_deals
spec:
  name: companies_deals
  sql_table: "`<dataset>.gold_companies_deals`"
  public: false

  meta:
    abConnectionId: conn_01HZX7K9P6QABCD

  joins:
    hubspot_companies:
      relationship: many_to_one
      sql: "${CUBE}.company_id = ${hubspot_companies}.id"

    hubspot_deals:
      relationship: many_to_one
      sql: "${CUBE}.deal_id = ${hubspot_deals}.id"

  measures:
    count:
      type: count

  dimensions:
    id:
      sql: "CONCAT(${CUBE}.deal_id, '-', ${CUBE}.company_id)"
      type: string
      primary_key: true

    deal_id:
      sql: "${CUBE}.deal_id"
      type: string

    company_id:
      sql: "${CUBE}.company_id"
      type: string

    airbyte_extracted_at:
      sql: "${CUBE}._airbyte_extracted_at"
      type: time

  refresh_key:
    sql: "SELECT MAX(_airbyte_extracted_at) FROM `<dataset>.gold_companies_deals`"
```

If the bridge model lacks `_airbyte_extracted_at`, omit that dimension and use:

```yaml
spec:
  refresh_key:
    every: 1 hour
```

---

## Composite Primary Key

Cube allows exactly one `primary_key: true` per cube. For composite keys, create a synthetic dimension:

```yaml
spec:
  dimensions:
    id:
      sql: "CONCAT(${CUBE}.office_unique_id, '-', ${CUBE}.month)"
      type: string
      primary_key: true

    office_unique_id:
      sql: "${CUBE}.office_unique_id"
      type: string

    month:
      sql: "${CUBE}.month"
      type: time
```

Choose a separator that does not appear in component values. `-` is usually safe; use `||` if components may contain `-`.

Joins to this cube must reference the synthetic `id`, not individual components.

---

## Join Direction Examples

Direction is always from the perspective of the current cube.

### Direct many-to-one / one-to-many

```yaml
# In cubes/hubspot_deals.yml
spec:
  joins:
    hubspot_companies:
      sql: "${CUBE}.company_id = ${hubspot_companies}.id"
      relationship: many_to_one
```

```yaml
# In cubes/hubspot_companies.yml
spec:
  joins:
    hubspot_deals:
      sql: "${CUBE}.id = ${hubspot_deals}.company_id"
      relationship: one_to_many
```

### Connector path (products -> clients -> addresses)

```yaml
# In cubes/products.yml
spec:
  joins:
    clients:
      sql: "${CUBE}.client_id = ${clients}.id"
      relationship: many_to_one
```

```yaml
# In cubes/clients.yml
spec:
  joins:
    products:
      sql: "${CUBE}.id = ${products}.client_id"
      relationship: one_to_many
    addresses:
      sql: "${CUBE}.id = ${addresses}.client_id"
      relationship: one_to_many
```

```yaml
# In cubes/addresses.yml
spec:
  joins:
    clients:
      sql: "${CUBE}.client_id = ${clients}.id"
      relationship: many_to_one
```

### Bridge joins (both parents reference bridge)

```yaml
# In cubes/hubspot_companies.yml
spec:
  joins:
    companies_deals:
      sql: "${CUBE}.id = ${companies_deals}.company_id"
      relationship: one_to_many
```

```yaml
# In cubes/hubspot_deals.yml
spec:
  joins:
    companies_deals:
      sql: "${CUBE}.id = ${companies_deals}.deal_id"
      relationship: one_to_many
```

### Unvalidated join

```yaml
spec:
  joins:
    hubspot_companies:
      # UNVALIDATED: match rate could not be measured because gold_hubspot_companies was not yet materialized
      sql: "${CUBE}.company_id = ${hubspot_companies}.id"
      relationship: many_to_one
```

---

## Refresh Key Variants

SQL-based refresh keys are **required**. They ensure caches invalidate only when data actually changes, instead of on a fixed timer.

Priority — use the first available timestamp column:

```yaml
# 1. Airbyte timestamp (preferred — present on all Airbyte sources)
spec:
  refresh_key:
    sql: "SELECT MAX(_airbyte_extracted_at) FROM `<dataset>.<gold_model>`"

# 2. CDC / update timestamp
spec:
  refresh_key:
    sql: "SELECT MAX(updated_at) FROM `<dataset>.<gold_model>`"

# 3. Insert-only fact table
spec:
  refresh_key:
    sql: "SELECT MAX(created_at) FROM `<dataset>.<gold_model>`"

# 4. Last resort — ONLY when the table has no timestamp column at all
# Add a comment explaining why:
spec:
  refresh_key:
    every: 1 hour  # no timestamp column available in this table
```

`spec.refresh_key.sql` must reference the same fully qualified table as `spec.sql_table`.

### Common Mistakes

```yaml
# BAD — fixed cadence, ignores actual data changes.
# This forces cache rebuild every hour even when data hasn't changed.
spec:
  refresh_key:
    every: 1 hour

# GOOD — only invalidates when new rows arrive
spec:
  refresh_key:
    sql: "SELECT MAX(_airbyte_extracted_at) FROM `<dataset>.<gold_model>`"
```

```yaml
# BAD — omitting refresh_key entirely (cube uses default, which may be too aggressive)
metadata:
  name: my_cube
spec:
  name: my_cube
  sql_table: ...

# GOOD — always include an explicit refresh_key
metadata:
  name: my_cube
spec:
  name: my_cube
  sql_table: ...
  refresh_key:
    sql: "SELECT MAX(_airbyte_extracted_at) FROM `<dataset>.<gold_model>`"
```

```yaml
# BAD — refresh_key.sql references a different table than sql_table
spec:
  sql_table: "`project.dataset.gold_orders`"
  refresh_key:
    sql: "SELECT MAX(_airbyte_extracted_at) FROM `project.dataset.gold_customers`"

# GOOD — same table in both
spec:
  sql_table: "`project.dataset.gold_orders`"
  refresh_key:
    sql: "SELECT MAX(_airbyte_extracted_at) FROM `project.dataset.gold_orders`"
```

---

## Type Mapping

```text
STRING / VARCHAR / TEXT        -> string
INTEGER / FLOAT / NUMERIC      -> number
BOOLEAN / BOOL                 -> boolean
DATE / DATETIME / TIMESTAMP    -> time
JSON / ARRAY / STRUCT          -> string (or skip if not queryable)
```

---

## Measure Suggestions

Common measure patterns by column name:

```text
amount   -> total_amount (sum), average_amount (avg)
revenue  -> total_revenue (sum)
price    -> total_price or average_price
cost     -> total_cost (sum)
quantity -> total_quantity (sum)
duration -> average_duration (avg)
*_id     -> count_distinct (only in the cube that owns the FK)
created_at  -> first_created_at (min), last_created_at (max)
closed_at   -> first_closed_at (min), last_closed_at (max)
updated_at  -> last_updated_at (max)
```

`count_distinct` on FK columns: define inside the cube that owns the FK, not the parent cube. Joins can produce row fan-out that distorts distinct counts.

---

## Common Mistakes

### Wrapping with `cubes:` or `views:` at the root

RevOS expects one cube per file with the IaC format — `apiVersion`, `kind`, `metadata`, and `spec`. The Cube.dev docs show a multi-cube `cubes:` list format, but RevOS does not use it.

```yaml
# BAD — multi-cube list format
cubes:
  - name: hubspot_companies
    sql_table: "`dataset.gold_hubspot_companies`"
    dimensions:
      id:
        sql: "${CUBE}.id"
        type: string
        primary_key: true
```

```yaml
# GOOD — IaC format with spec.name as the cube identifier
apiVersion: revos/v1
kind: Cube
metadata:
  name: hubspot_companies
spec:
  name: hubspot_companies
  sql_table: "`dataset.gold_hubspot_companies`"
  dimensions:
    id:
      sql: "${CUBE}.id"
      type: string
      primary_key: true
```

Same applies to `views:` — never use it as a root key.
