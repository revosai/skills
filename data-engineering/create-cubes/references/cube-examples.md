# Cube Examples

## Table of Contents

- [Standard Cube](#standard-cube)
- [Bridge / Junction Cube](#bridge--junction-cube)
- [Composite Primary Key](#composite-primary-key)
- [Join Direction Examples](#join-direction-examples)
- [Refresh Key Variants](#refresh-key-variants)
- [Type Mapping](#type-mapping)
- [Measure Suggestions](#measure-suggestions)
- [Filtered Measures](#filtered-measures)
- [Common Mistakes](#common-mistakes)

---

## Standard Cube

```yaml
apiVersion: revos/v1
kind: Cube
metadata:
  name: contacts
spec:
  joins:
    customers:
      sql: ${CUBE}.company_id = ${customers}.hubspot_company_id
      relationship: many_to_one
  measures:
    count:
      type: count
      description: Total number of contacts.
    total_deal_value:
      sql: ${CUBE}.properties_hs_total_deal_value
      type: sum
      description: Total HubSpot deal value.
    distinct_companies:
      sql: ${CUBE}.company_id
      type: count_distinct
      description: Number of distinct companies with at least one contact.
  sql_table: "`your-project.your-dataset.gold_contacts`"
  dimensions:
    id:
      sql: ${CUBE}.id
      type: string
      public: true
      description: Unique HubSpot contact identifier. Primary key.
      primary_key: true
    properties_name:
      sql: ${CUBE}.properties_name
      type: string
      description: Contact's full name as stored in HubSpot.
    email:
      sql: ${CUBE}.email
      type: string
      description: Contact's email address as stored in HubSpot.
    company_id:
      sql: ${CUBE}.company_id
      type: string
      description: HubSpot company ID linking this contact to a customer account.
    created_at:
      sql: ${CUBE}.created_at
      type: time
      description: Timestamp when the contact record was created in HubSpot.
    airbyte_extracted_at:
      sql: ${CUBE}._airbyte_extracted_at
      type: time
      description: Timestamp when this record was last extracted by Airbyte.
  description: >
    HubSpot contacts linked to customer accounts. One row per contact.
    Source: gold_contacts.
  refresh_key:
    sql: SELECT MAX(_airbyte_extracted_at) FROM `your-project.your-dataset.gold_contacts`
```

Notes:

1. `metadata.name` is the single source of truth for the cube identifier — it's used as the filename slug, IaC address, and Cube.dev cube name referenced by `${CUBE}` and joins.
2. Cube name is `contacts` (no `gold_` prefix); `spec.sql_table` references `gold_contacts` (with `gold_` prefix).
3. Only `_airbyte_extracted_at` is exposed from Airbyte metadata, as `airbyte_extracted_at`.
4. `spec.refresh_key.sql` uses the same fully qualified table name as `spec.sql_table`.
5. Every measure and dimension includes a `description:` field (see rule 10).
6. Primary key dimension has both `primary_key: true` and `public: true` (see rule 11).
7. `spec.meta` (`abConnectionId`, `nameDimension`, `icon`) is omitted here — add it when applicable per rules 12–14.

---

## Bridge / Junction Cube

```yaml
apiVersion: revos/v1
kind: Cube
metadata:
  name: deals_contacts
spec:
  joins:
    deals:
      sql: ${CUBE}.deal_id = ${deals}.deal_id
      relationship: many_to_one
    contacts:
      sql: ${CUBE}.contact_id = ${contacts}.contact_id
      relationship: many_to_one
  measures:
    count:
      type: count
      description: Total number of deal-contact associations.
  sql_table: "`your-project.your-dataset.gold_deals_contacts`"
  public: false
  dimensions:
    id:
      sql: CONCAT(${CUBE}.deal_id, '-', ${CUBE}.contact_id)
      type: string
      public: true
      description: Synthetic primary key combining deal_id and contact_id.
      primary_key: true
    deal_id:
      sql: ${CUBE}.deal_id
      type: string
      description: HubSpot deal ID (foreign key to deals).
    contact_id:
      sql: ${CUBE}.contact_id
      type: string
      description: HubSpot contact ID (foreign key to contacts).
    airbyte_extracted_at:
      sql: ${CUBE}._airbyte_extracted_at
      type: time
      description: Timestamp when this record was last extracted by Airbyte.
  description: >
    Bridge table linking deals to contacts. One row per deal-contact association.
    Internal join model — not exposed in the UI.
  refresh_key:
    sql: SELECT MAX(_airbyte_extracted_at) FROM `your-project.your-dataset.gold_deals_contacts`
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
      public: true
      description: Synthetic primary key combining office_unique_id and month.

    office_unique_id:
      sql: "${CUBE}.office_unique_id"
      type: string
      description: Unique identifier for the office.

    month:
      sql: "${CUBE}.month"
      type: time
      description: Reporting month.
```

Choose a separator that does not appear in component values. `-` is usually safe; use `||` if components may contain `-`.

Joins to this cube must reference the synthetic `id`, not individual components.

---

## Join Direction Examples

Direction is always from the perspective of the current cube.

### Direct many-to-one / one-to-many

```yaml
# In deals.yaml
spec:
  joins:
    customers:
      sql: "${CUBE}.company_id = ${customers}.id"
      relationship: many_to_one
```

```yaml
# In customers.yaml
spec:
  joins:
    deals:
      sql: "${CUBE}.id = ${deals}.company_id"
      relationship: one_to_many
```

### Connector path (products -> clients -> addresses)

```yaml
# In products.yaml
spec:
  joins:
    clients:
      sql: "${CUBE}.client_id = ${clients}.id"
      relationship: many_to_one
```

```yaml
# In clients.yaml
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
# In addresses.yaml
spec:
  joins:
    clients:
      sql: "${CUBE}.client_id = ${clients}.id"
      relationship: many_to_one
```

### Bridge joins (both parents reference bridge)

```yaml
# In customers.yaml
spec:
  joins:
    customers_deals:
      sql: "${CUBE}.id = ${customers_deals}.company_id"
      relationship: one_to_many
```

```yaml
# In deals.yaml
spec:
  joins:
    customers_deals:
      sql: "${CUBE}.id = ${customers_deals}.deal_id"
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

# 4. Snapshot / derived table with no source timestamp
spec:
  refresh_key:
    sql: SELECT CURRENT_DATE()

# 5. Last resort — ONLY when the table has no timestamp column at all
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
  sql_table: ...

# GOOD — always include an explicit refresh_key
metadata:
  name: my_cube
spec:
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

## Filtered Measures

Use `filters:` to scope a measure to a subset of rows. Each filter is a SQL fragment evaluated per row.

```yaml
# Count of active subscriptions only
active_count:
  type: count
  filters:
    - sql: "${CUBE}.status = 'active'"
  description: Number of subscriptions currently in active status.
```

```yaml
# Deals at risk of churn within 30 days
renewal_risk_30d:
  type: count
  filters:
    - sql: "DATE_DIFF(${CUBE}.renewal_date, CURRENT_DATE(), DAY) <= 30"
    - sql: "${CUBE}.status = 'active'"
  description: Active deals with renewal date within the next 30 days.
```

```yaml
# Revenue over the trailing 12 months
revenue_last_12m:
  sql: ${CUBE}.amount
  type: sum
  filters:
    - sql: "${CUBE}.closed_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)"
  description: Sum of closed deal amounts in the trailing 12 months. USD.
```

```yaml
# ARR for active contracts only
active_arr:
  sql: ${CUBE}.arr
  type: sum
  filters:
    - sql: "${CUBE}.contract_status = 'active'"
  description: Annual recurring revenue across active contracts only. USD.
```

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
# GOOD — IaC format with metadata.name as the cube identifier
apiVersion: revos/v1
kind: Cube
metadata:
  name: hubspot_companies
spec:
  sql_table: "`dataset.gold_hubspot_companies`"
  dimensions:
    id:
      sql: "${CUBE}.id"
      type: string
      primary_key: true
      public: true
      description: Unique HubSpot company ID. Primary key.
```

Same applies to `views:` — never use it as a root key.

### Old flat format

All cubes must use the IaC manifest format. The old flat format with `name:` at root is rejected by `revos apply`.

```yaml
# BAD — old flat format (name: at root level)
name: hubspot_companies
sql_table: "`dataset.gold_hubspot_companies`"
dimensions:
  id:
    sql: "${CUBE}.id"
    type: string
    primary_key: true
```

```yaml
# GOOD — IaC manifest format
apiVersion: revos/v1
kind: Cube
metadata:
  name: hubspot_companies
spec:
  sql_table: "`dataset.gold_hubspot_companies`"
  dimensions:
    id:
      sql: "${CUBE}.id"
      type: string
      primary_key: true
      public: true
      description: Unique HubSpot company ID. Primary key.
```

### Missing descriptions

Every measure and dimension must have a `description:` field. Omitting it makes the semantic layer harder to use in the UI and in AI-generated queries.

```yaml
# BAD — no description on measure or dimension
measures:
  count:
    type: count
dimensions:
  status:
    sql: ${CUBE}.status
    type: string
```

```yaml
# GOOD — description on every field
measures:
  count:
    type: count
    description: Total number of records.
dimensions:
  status:
    sql: ${CUBE}.status
    type: string
    description: Current lifecycle status of the record (e.g. active, churned).
```

### Missing `public: true` on primary key

Primary key dimensions need both `primary_key: true` (tells Cube.dev which field is the PK) and `public: true` (makes it queryable). Without `public: true`, the PK is hidden and joins referencing it from other cubes may produce unexpected results.

```yaml
# BAD — primary_key: true but not public
dimensions:
  id:
    sql: ${CUBE}.id
    type: string
    primary_key: true
    description: Unique record ID.
```

```yaml
# GOOD — both flags set
dimensions:
  id:
    sql: ${CUBE}.id
    type: string
    primary_key: true
    public: true
    description: Unique record ID. Primary key.
```
