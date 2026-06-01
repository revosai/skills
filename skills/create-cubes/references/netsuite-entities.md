# NetSuite Entities Reference

## Table naming

Airbyte syncs NetSuite tables with a configurable prefix (default: `netsuite_`).
Inspect the BigQuery dataset to confirm:

```sql
SELECT table_name FROM `<dataset>.INFORMATION_SCHEMA.TABLES`
WHERE table_name LIKE '%customer%' OR table_name LIKE '%salesorder%'
ORDER BY table_name LIMIT 20;
```

Throughout this document `<prefix>` is a placeholder for that prefix.

---

## Primary entities

| Cube name             | BigQuery table        | PK   | Notes                          |
| --------------------- | --------------------- | ---- | ------------------------------ |
| `<prefix>customer`    | `<prefix>customer`    | `id` | FK `subsidiary` is JSON object |
| `<prefix>contact`     | `<prefix>contact`     | `id` | FK `company` is JSON object    |
| `<prefix>opportunity` | `<prefix>opportunity` | `id` | FK `entity` is JSON object     |
| `<prefix>salesorder`  | `<prefix>salesorder`  | `id` | FK `entity` is JSON object     |
| `<prefix>employee`    | `<prefix>employee`    | `id` | —                              |

---

## FK extraction pattern

NetSuite stores foreign keys as **JSON objects** with an `id` field rather than
as flat FK columns. Use `JSON_VALUE` to extract the ID and expose it as a
computed dimension.

### contact → customer

`contact.company` is a JSON object: `{"id": "123", "refName": "Acme Corp"}`.

```yaml
name: <prefix>contact
sql_table: "`<dataset>.<prefix>contact`"
dimensions:
  id:
    sql: "id"
    type: string
    primary_key: true
  customer_id:
    sql: "JSON_VALUE(${CUBE}.company, '$.id')"
    type: string
joins:
  <prefix>customer:
    relationship: many_to_one
    sql: "${CUBE.customer_id} = ${<prefix>customer.id}"
```

### customer → subsidiary

`customer.subsidiary` is a JSON object: `{"id": "1", "refName": "Main Subsidiary"}`.

```yaml
name: <prefix>customer
sql_table: "`<dataset>.<prefix>customer`"
dimensions:
  subsidiary_id:
    sql: "JSON_VALUE(${CUBE}.subsidiary, '$.id')"
    type: string
joins:
  <prefix>contact:
    relationship: one_to_many
    sql: "${CUBE}.id = ${<prefix>contact.customer_id}"
  <prefix>salesorder:
    relationship: one_to_many
    sql: "${CUBE}.id = ${<prefix>salesorder.customer_id}"
  <prefix>opportunity:
    relationship: one_to_many
    sql: "${CUBE}.id = ${<prefix>opportunity.customer_id}"
```

### opportunity / salesorder → customer

Both `opportunity` and `salesorder` use `entity` (not `company`) as the FK column:

```yaml
name: <prefix>opportunity
sql_table: "`<dataset>.<prefix>opportunity`"
dimensions:
  id:
    sql: "id"
    type: string
    primary_key: true
  customer_id:
    sql: "JSON_VALUE(${CUBE}.entity, '$.id')"
    type: string
joins:
  <prefix>customer:
    relationship: many_to_one
    sql: "${CUBE.customer_id} = ${<prefix>customer.id}"
```

Same pattern for `<prefix>salesorder`.

---

## Relationship graph

```
customer ──< contact
customer ──< opportunity
customer ──< salesorder
```

---

## Common pitfalls

1. **FK columns are JSON objects** — `contact.company`, `opportunity.entity`, `salesorder.entity`, `customer.subsidiary` are all JSON objects. Never join directly; always extract with `JSON_VALUE(..., '$.id')` and expose as a computed dimension.
2. **`entity` vs `company`** — contacts use `company`, but opportunities and sales orders use `entity` as the customer FK column.
3. **PK column name is `id` (lowercase)** — not `internalId` or similar. Verify in INFORMATION_SCHEMA.
4. **Subsidiary** — `customer.subsidiary` holds the subsidiary FK. If the schema has multiple subsidiaries, you may need a `subsidiary` cube joined via `subsidiary_id`.
5. **No `_airbyte_extracted_at` guarantee** — some NetSuite streams use `lastModifiedDate` instead. Check actual column names before writing `refresh_key`.
