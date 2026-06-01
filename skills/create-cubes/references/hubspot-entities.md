# HubSpot Entities Reference

## Table naming

Airbyte syncs HubSpot tables with a configurable prefix (default: `hubspot_`).
Inspect the BigQuery dataset to identify the actual prefix:

```sql
SELECT table_name FROM `<dataset>.INFORMATION_SCHEMA.TABLES`
WHERE table_name LIKE '%companies%' OR table_name LIKE '%deals%'
ORDER BY table_name LIMIT 20;
```

Throughout this document `<prefix>` is a placeholder for that prefix (e.g. `hubspot_`).

---

## Primary entities

| Cube name                | BigQuery table           | PK           | Notes                                              |
| ------------------------ | ------------------------ | ------------ | -------------------------------------------------- | --- | --- | --- | --------- |
| `<prefix>companies`      | `<prefix>companies`      | `id`         | `properties_name` is the display name              |
| `<prefix>contacts`       | `<prefix>contacts`       | `id`         | `properties_hs_full_name_or_email` is display name |
| `<prefix>deals`          | `<prefix>deals`          | `id`         | `properties_dealname` is display name              |
| `<prefix>tickets`        | `<prefix>tickets`        | `id`         | —                                                  |
| `<prefix>owners`         | `<prefix>owners`         | `id`         | Display name: `firstName                           |     | ' ' |     | lastName` |
| `<prefix>engagements`    | `<prefix>engagements`    | `id`         | See engagement sub-types below                     |
| `<prefix>deal_pipelines` | `<prefix>deal_pipelines` | `pipelineId` | Stages stored as JSON array                        |
| `<prefix>line_items`     | `<prefix>line_items`     | `id`         | `properties_name`                                  |
| `<prefix>products`       | `<prefix>products`       | `id`         | `properties_name`                                  |

**Owner join pattern (shared by companies, contacts, deals, tickets):**

```yaml
joins:
  <prefix>owners:
    relationship: many_to_one
    sql: "${CUBE}.properties_hubspot_owner_id = ${<prefix>owners.id}"
```

---

## Bridge / junction cubes (public: false)

HubSpot stores many-to-many associations as JSON arrays on the primary object.
Bridge cubes are required to join across these associations. They must be
`public: false` and use a composite PK.

### Association columns

| Source table          | Column                    | Contains                                |
| --------------------- | ------------------------- | --------------------------------------- |
| `<prefix>deals`       | `companies`               | JSON array of company IDs               |
| `<prefix>deals`       | `contacts`                | JSON array of contact IDs               |
| `<prefix>deals`       | `line_items`              | JSON array of line item IDs             |
| `<prefix>deals`       | `deals`                   | JSON array (for tickets→deals)          |
| `<prefix>tickets`     | `companies`               | JSON array of company IDs               |
| `<prefix>tickets`     | `contacts`                | JSON array of contact IDs               |
| `<prefix>tickets`     | `deals`                   | JSON array of deal IDs (CAST to STRING) |
| `<prefix>companies`   | `contacts`                | JSON array of contact IDs               |
| `<prefix>engagements` | `associations.contactIds` | JSON array of contact IDs               |
| `<prefix>engagements` | `associations.companyIds` | JSON array of company IDs               |
| `<prefix>engagements` | `associations.dealIds`    | JSON array of deal IDs                  |

### Bridge cube: companies_to_deals

```yaml
name: <prefix>companies_to_deals
sql: >
  SELECT DISTINCT d.id as deal_id, company_id
  FROM `<dataset>.<prefix>deals` d,
  UNNEST(JSON_VALUE_ARRAY(d.companies)) company_id
public: false
dimensions:
  id:
    sql: "${CUBE.company_id} || ${CUBE.deal_id}"
    type: string
    primary_key: true
  company_id:
    sql: "${CUBE}.company_id"
    type: string
  deal_id:
    sql: "${CUBE}.deal_id"
    type: string
joins:
  <prefix>companies:
    relationship: many_to_one
    sql: "${CUBE}.company_id = ${<prefix>companies.id}"
  <prefix>deals:
    relationship: many_to_one
    sql: "${CUBE}.deal_id = ${<prefix>deals.id}"
refresh_key:
  sql: "SELECT MAX(_airbyte_extracted_at) FROM `<dataset>.<prefix>deals`"
```

### Bridge cube: companies_to_tickets

Same pattern — UNNEST `tickets.companies`:

```yaml
name: <prefix>companies_to_tickets
sql: >
  SELECT DISTINCT t.id as ticket_id, company_id
  FROM `<dataset>.<prefix>tickets` t,
  UNNEST(JSON_VALUE_ARRAY(t.companies)) company_id
```

### Bridge cube: deals_to_tickets

Note: ticket `deals` column values are numbers — cast to STRING:

```yaml
name: <prefix>deals_to_tickets
sql: >
  SELECT DISTINCT t.id AS ticket_id, CAST(deal_id AS STRING) AS deal_id
  FROM `<dataset>.<prefix>tickets` t,
  UNNEST(JSON_VALUE_ARRAY(t.deals)) AS deal_id
```

### Bridge cube: deals_to_line_items

```yaml
name: <prefix>deals_to_line_items
sql: >
  SELECT DISTINCT d.id AS deal_id, line_item_id
  FROM `<dataset>.<prefix>deals` d,
  UNNEST(JSON_VALUE_ARRAY(d.line_items)) AS line_item_id
```

### Bridge cube: contacts_to_deals

```yaml
name: <prefix>contacts_to_deals
sql: >
  SELECT DISTINCT d.id AS deal_id, contact_id
  FROM `<dataset>.<prefix>deals` d,
  UNNEST(JSON_VALUE_ARRAY(d.contacts)) contact_id
```

### Bridge cube: contacts_to_tickets

```yaml
name: <prefix>contacts_to_tickets
sql: >
  SELECT DISTINCT t.id AS ticket_id, contact_id
  FROM `<dataset>.<prefix>tickets` t,
  UNNEST(JSON_VALUE_ARRAY(t.contacts)) contact_id
```

### Bridge cube: contacts_to_companies

Note: this uses `SAFE_CAST` on both sides — IDs can have type mismatches:

```yaml
name: <prefix>contacts_to_companies
sql: >
  SELECT DISTINCT c.id AS company_id, contact_id
  FROM `<dataset>.<prefix>companies` c,
  UNNEST(JSON_VALUE_ARRAY(c.contacts)) AS contact_id
joins:
  <prefix>contacts:
    relationship: many_to_one
    sql: "SAFE_CAST(${CUBE}.contact_id AS STRING) = SAFE_CAST(${<prefix>contacts.id} AS STRING)"
  <prefix>companies:
    relationship: many_to_one
    sql: "SAFE_CAST(${CUBE}.company_id AS STRING) = SAFE_CAST(${<prefix>companies.id} AS STRING)"
```

### Bridge cubes: engagements_to_contacts / companies / deals

Engagement IDs are integers — always CAST to STRING:

```yaml
name: <prefix>engagements_to_contacts
sql: >
  SELECT DISTINCT
    CAST(e.id AS STRING) AS engagement_id,
    CAST(contact_id AS STRING) AS contact_id
  FROM `<dataset>.<prefix>engagements` e,
  UNNEST(JSON_VALUE_ARRAY(e.associations.contactIds)) AS contact_id
```

Same pattern for `companyIds` → `engagements_to_companies` and `dealIds` → `engagements_to_deals`.

Engagement join:

```yaml
joins:
  <prefix>engagements:
    relationship: many_to_one
    sql: "CAST(${CUBE}.engagement_id AS STRING) = CAST(${<prefix>engagements.id} AS STRING)"
```

---

## Special cubes

### deal_pipeline_stages

Derived from `deal_pipelines.stages` JSON array. Not a raw table — uses `sql:` not `sql_table:`.

```yaml
name: <prefix>deal_pipeline_stages
sql: >
  SELECT
    JSON_VALUE(elem, '$.stageId') AS stage_id,
    JSON_VALUE(elem, '$.label') AS label
  FROM `<dataset>.<prefix>deal_pipelines`,
  UNNEST(JSON_QUERY_ARRAY(stages)) AS elem
dimensions:
  stage_id:
    sql: "${CUBE}.stage_id"
    type: string
    primary_key: true
  label:
    sql: "${CUBE}.label"
    type: string
joins:
  <prefix>deals:
    relationship: one_to_many
    sql: "${CUBE}.stage_id = ${<prefix>deals.properties_dealstage}"
refresh_key:
  sql: "SELECT MAX(_airbyte_extracted_at) FROM `<dataset>.<prefix>deal_pipelines`"
```

Deals join to stages and pipelines:

```yaml
joins:
  <prefix>deal_pipeline_stages:
    relationship: many_to_one
    sql: "${CUBE}.properties_dealstage = ${<prefix>deal_pipeline_stages.stage_id}"
  <prefix>deal_pipelines:
    relationship: many_to_one
    sql: "${CUBE}.properties_pipeline = ${<prefix>deal_pipelines.pipelineId}"
```

### engagements sub-types

`engagements` table has sub-type tables: `engagements_calls`, `engagements_emails`,
`engagements_meetings`, `engagements_tasks`, `engagements_notes`.

Join pattern (one-to-one by ID with CAST):

```yaml
# On the engagements cube:
joins:
  <prefix>engagements_calls:
    relationship: one_to_one
    sql: "CAST(${CUBE}.id AS STRING) = ${<prefix>engagements_calls.id}"

# On each sub-type cube:
joins:
  <prefix>engagements:
    relationship: many_to_one
    sql: "${CUBE}.id = CAST(${<prefix>engagements.id} AS STRING)"
```

---

## Deals measures

```yaml
measures:
  count_closed:
    type: count
    filters:
      - sql: "${CUBE}.properties_hs_is_closed = TRUE"
  count_closed_won:
    type: count
    filters:
      - sql: "${CUBE}.properties_hs_is_closed_won = TRUE"
  count_closed_lost:
    type: count
    filters:
      - sql: >
          ${CUBE}.properties_hs_is_closed = TRUE
          AND ${CUBE}.properties_hs_is_closed_won = FALSE
```

---

## Common pitfalls

1. **ID type mismatches** — HubSpot IDs are sometimes integers, sometimes strings. Use `SAFE_CAST` when unsure (especially contacts_to_companies). Engagement IDs are always integers → always CAST to STRING.
2. **JSON_VALUE_ARRAY vs JSON_QUERY_ARRAY** — use `JSON_VALUE_ARRAY` when the array contains scalar strings/ints (association IDs); use `JSON_QUERY_ARRAY` when the array contains JSON objects (deal_pipelines stages).
3. **deal_pipeline_stages is derived** — uses `sql:` not `sql_table:`. Cannot be used in `revos cubes preview` diff against Airbyte-generated cubes.
4. **engagements bridge refresh_key** — use the parent engagement table timestamp, not the contact/company/deal table.
5. **Prefix varies** — always confirm the actual prefix from BigQuery before writing cube files.
